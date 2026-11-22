"""数据库迁移集合。所有迁移幂等：可重复执行，失败事务回滚。"""

from sqlalchemy import text

from app.database.connection import engine

# ---------- Sprint 6 Task 6.1：shot_images 版本管理 ----------

NEW_COLUMNS = {
    "version": "ALTER TABLE shot_images ADD COLUMN version INTEGER",
    "character_reference_asset_ids": (
        "ALTER TABLE shot_images ADD COLUMN character_reference_asset_ids "
        "TEXT NOT NULL DEFAULT '[]'"
    ),
    "scene_reference_asset_ids": (
        "ALTER TABLE shot_images ADD COLUMN scene_reference_asset_ids "
        "TEXT NOT NULL DEFAULT '[]'"
    ),
}


def migrate_shot_image_versions() -> dict:
    """执行迁移，返回统计信息。重复调用安全。"""
    with engine.begin() as conn:  # 事务：任何异常都会回滚
        existing = {
            r[1] for r in conn.execute(text("PRAGMA table_info(shot_images)"))
        }
        added = []
        for col, ddl in NEW_COLUMNS.items():
            if col not in existing:
                conn.execute(text(ddl))
                added.append(col)

        # 回填 version：按 created_at + id（稳定次级排序）在每个 shot 内顺序编号
        rows = conn.execute(
            text(
                "SELECT id, shot_id FROM shot_images WHERE version IS NULL "
                "ORDER BY shot_id, created_at, id"
            )
        ).all()
        next_version: dict[str, int] = {}
        for row_id, shot_id in rows:
            if shot_id not in next_version:
                cur = conn.execute(
                    text(
                        "SELECT MAX(version) FROM shot_images "
                        "WHERE shot_id = :sid AND version IS NOT NULL"
                    ),
                    {"sid": shot_id},
                ).scalar()
                next_version[shot_id] = (cur or 0) + 1
            conn.execute(
                text("UPDATE shot_images SET version = :v WHERE id = :rid"),
                {"v": next_version[shot_id], "rid": row_id},
            )
            next_version[shot_id] += 1

        # 校验：版本号必须在每个 shot 内唯一，否则回滚
        dups = conn.execute(
            text(
                "SELECT shot_id, version, COUNT(*) AS c FROM shot_images "
                "WHERE version IS NOT NULL "
                "GROUP BY shot_id, version HAVING c > 1"
            )
        ).all()
        if dups:
            raise RuntimeError(f"版本号重复，迁移回滚: {dups[:3]}")

        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_shot_images_shot_version "
                "ON shot_images(shot_id, version)"
            )
        )

    return {"columns_added": added, "versions_backfilled": len(rows)}


# ---------- Sprint 6.5：Prompt 编辑与重新生成 ----------

S65_COLUMNS = {
    "shots": {
        "custom_prompt": "ALTER TABLE shots ADD COLUMN custom_prompt TEXT",
        "custom_negative_prompt": (
            "ALTER TABLE shots ADD COLUMN custom_negative_prompt TEXT"
        ),
    },
    "generation_jobs": {
        "reference_override": (
            "ALTER TABLE generation_jobs ADD COLUMN reference_override TEXT"
        ),
    },
}


def migrate_prompt_editing() -> dict:
    """Sprint 6.5 迁移：shots 加自定义 Prompt 列，generation_jobs 加参考图覆盖列。幂等。"""
    added = []
    with engine.begin() as conn:
        for table, cols in S65_COLUMNS.items():
            existing = {
                r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(ddl))
                    added.append(f"{table}.{col}")
    return {"columns_added": added}


# ---------- 生成队列：真实进度 + 角色/场景任务 ----------

PROGRESS_COLUMNS = {
    "target_type": (
        "ALTER TABLE generation_jobs ADD COLUMN target_type VARCHAR(20) "
        "NOT NULL DEFAULT 'shot'"
    ),
    "target_id": "ALTER TABLE generation_jobs ADD COLUMN target_id VARCHAR(64)",
    "progress": (
        "ALTER TABLE generation_jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0"
    ),
    "progress_message": (
        "ALTER TABLE generation_jobs ADD COLUMN progress_message VARCHAR(255)"
    ),
    "current_variation": (
        "ALTER TABLE generation_jobs ADD COLUMN current_variation INTEGER NOT NULL DEFAULT 0"
    ),
    "result_asset_id": (
        "ALTER TABLE generation_jobs ADD COLUMN result_asset_id VARCHAR(64)"
    ),
}


def migrate_generation_progress() -> dict:
    """为现有数据库幂等添加通用任务与进度字段，并保留全部历史任务。"""
    added = []
    with engine.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(generation_jobs)")).all()
        existing = {r[1] for r in info}
        for col, ddl in PROGRESS_COLUMNS.items():
            if col not in existing:
                conn.execute(text(ddl))
                added.append(col)
        conn.execute(
            text(
                "UPDATE generation_jobs SET target_id = shot_id "
                "WHERE target_type = 'shot' AND target_id IS NULL"
            )
        )
        conn.execute(
            text(
                "UPDATE generation_jobs SET progress = 100 "
                "WHERE status = 'completed' AND progress < 100"
            )
        )
        needs_nullable_rebuild = any(
            r[1] in ("episode_id", "shot_id") and r[3] for r in info
        )

    rebuilt = False
    if needs_nullable_rebuild:
        # SQLite 不能直接 DROP NOT NULL。新建表→复制→替换，原表和索引可完整恢复。
        columns = [
            "id", "project_id", "episode_id", "shot_id", "provider", "status",
            "prompt", "negative_prompt", "workflow_name", "variations", "seed",
            "width", "height", "steps", "attempts", "error_message", "created_at",
            "completed_at", "upscale", "reference_override", "target_type",
            "target_id", "progress", "progress_message", "current_variation",
            "result_asset_id",
        ]
        raw = engine.raw_connection()
        try:
            raw.execute("PRAGMA foreign_keys=OFF")
            raw.execute("BEGIN")
            raw.execute("""
                CREATE TABLE generation_jobs_new (
                    id VARCHAR(64) NOT NULL PRIMARY KEY,
                    project_id VARCHAR(64) NOT NULL,
                    episode_id VARCHAR(64),
                    shot_id VARCHAR(64),
                    provider VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    prompt TEXT NOT NULL,
                    negative_prompt TEXT,
                    workflow_name VARCHAR(50) NOT NULL,
                    variations INTEGER NOT NULL,
                    seed INTEGER NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    steps INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    error_message TEXT,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    upscale INTEGER DEFAULT 2,
                    reference_override TEXT,
                    target_type VARCHAR(20) NOT NULL DEFAULT 'shot',
                    target_id VARCHAR(64),
                    progress INTEGER NOT NULL DEFAULT 0,
                    progress_message VARCHAR(255),
                    current_variation INTEGER NOT NULL DEFAULT 0,
                    result_asset_id VARCHAR(64),
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(episode_id) REFERENCES episodes(id),
                    FOREIGN KEY(shot_id) REFERENCES shots(id),
                    FOREIGN KEY(result_asset_id) REFERENCES assets(id)
                )
            """)
            column_sql = ", ".join(columns)
            raw.execute(
                f"INSERT INTO generation_jobs_new ({column_sql}) "
                f"SELECT {column_sql} FROM generation_jobs"
            )
            raw.execute("DROP TABLE generation_jobs")
            raw.execute("ALTER TABLE generation_jobs_new RENAME TO generation_jobs")
            for name, column in (
                ("project_id", "project_id"), ("episode_id", "episode_id"),
                ("shot_id", "shot_id"), ("target_type", "target_type"),
                ("target_id", "target_id"),
            ):
                raw.execute(
                    f"CREATE INDEX ix_generation_jobs_{name} "
                    f"ON generation_jobs({column})"
                )
            raw.commit()
            rebuilt = True
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.execute("PRAGMA foreign_keys=ON")
            raw.close()
    else:
        with engine.begin() as conn:
            for name in ("target_type", "target_id"):
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_generation_jobs_{name} "
                    f"ON generation_jobs({name})"
                ))
    return {"columns_added": added, "table_rebuilt": rebuilt}


# ---------- Production Management System ----------

def migrate_production_system() -> dict:
    """添加项目恢复、剧集规划与阶段状态表；不修改既有图片和业务记录。"""
    from app.database.connection import Base
    from app.database.models import ApprovalRecord, ProductionRevision, ProductionState

    added = []
    columns = {
        "projects": {
            "novel_name": "ALTER TABLE projects ADD COLUMN novel_name VARCHAR(255)",
            "current_stage": (
                "ALTER TABLE projects ADD COLUMN current_stage INTEGER NOT NULL DEFAULT 1"
            ),
            "last_active_episode_id": (
                "ALTER TABLE projects ADD COLUMN last_active_episode_id VARCHAR(64)"
            ),
        },
        "episodes": {
            "plan_json": "ALTER TABLE episodes ADD COLUMN plan_json TEXT",
        },
        "shots": {
            "production_outdated": (
                "ALTER TABLE shots ADD COLUMN production_outdated BOOLEAN NOT NULL DEFAULT 0"
            ),
        },
    }
    with engine.begin() as conn:
        for table, definitions in columns.items():
            existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in definitions.items():
                if name not in existing:
                    conn.execute(text(ddl))
                    added.append(f"{table}.{name}")
    Base.metadata.create_all(
        engine, tables=[ProductionState.__table__, ProductionRevision.__table__, ApprovalRecord.__table__]
    )
    return {"columns_added": added}
