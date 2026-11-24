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
    from app.database.models import ApprovalRecord, ProductionRevision, ProductionState, Prop

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
        engine, tables=[ProductionState.__table__, ProductionRevision.__table__, ApprovalRecord.__table__, Prop.__table__]
    )
    # 旧版本道具保存在阶段 JSON 中；首次升级时复制为可持续生成图片的资产档案。
    import json
    import uuid
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT project_id, content_json FROM production_states "
            "WHERE stage = 5 AND episode_id IS NULL"
        )).all()
        for project_id, content_json in rows:
            exists = conn.execute(text("SELECT 1 FROM props WHERE project_id = :pid LIMIT 1"), {"pid": project_id}).first()
            if exists:
                continue
            try:
                props = (json.loads(content_json or "{}").get("props") or [])
            except json.JSONDecodeError:
                props = []
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for item in props:
                conn.execute(text(
                    "INSERT INTO props (id, project_id, name, description, narrative_significance, "
                    "visual_prompt, reference_asset_id, status, created_at, updated_at) "
                    "VALUES (:id, :pid, :name, :description, :significance, '', NULL, 'draft', :now, :now)"
                ), {"id": f"prop_{uuid.uuid4().hex[:12]}", "pid": project_id, "name": item.get("name", "未命名道具"), "description": item.get("description"), "significance": item.get("narrative_significance"), "now": now})
    return {"columns_added": added}


def migrate_story_first_workflow() -> dict:
    """一次性把七阶段数据映射为 Story Bible 优先的八阶段流程。"""
    import json
    import uuid
    from datetime import datetime, timezone

    migration_name = "story_first_workflow_v1"
    moved_states = 0
    moved_approvals = 0
    created_chapter_states = 0
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name VARCHAR(100) PRIMARY KEY, applied_at DATETIME NOT NULL)"
        ))
        if conn.execute(
            text("SELECT 1 FROM schema_migrations WHERE name = :name"),
            {"name": migration_name},
        ).first():
            return {"already_applied": True}

        for old_stage in range(7, 2, -1):
            result = conn.execute(
                text("UPDATE production_states SET stage = :new WHERE stage = :old"),
                {"old": old_stage, "new": old_stage + 1},
            )
            moved_states += result.rowcount
            result = conn.execute(
                text("UPDATE approval_records SET stage = :new WHERE stage = :old"),
                {"old": old_stage, "new": old_stage + 1},
            )
            moved_approvals += result.rowcount

        rows = conn.execute(text(
            "SELECT id, project_id, content_json, status, version, outdated, "
            "approved_at, created_at, updated_at FROM production_states "
            "WHERE stage = 1 AND episode_id IS NULL"
        )).all()
        now = datetime.now(timezone.utc)
        for row in rows:
            try:
                data = json.loads(row.content_json or "{}")
            except json.JSONDecodeError:
                data = {}
            novel = data.pop("novel", None)
            data.pop("analysis_truncated", None)
            conn.execute(
                text("UPDATE production_states SET content_json = :content WHERE id = :id"),
                {"id": row.id, "content": json.dumps(data, ensure_ascii=False)},
            )
            if novel:
                conn.execute(text(
                    "INSERT INTO production_states (id, project_id, episode_id, stage, "
                    "status, content_json, version, outdated, approved_at, created_at, updated_at) "
                    "VALUES (:id, :project_id, NULL, 3, :status, :content, :version, "
                    ":outdated, :approved_at, :created_at, :updated_at)"
                ), {
                    "id": f"state_{uuid.uuid4().hex[:12]}",
                    "project_id": row.project_id,
                    "status": row.status,
                    "content": json.dumps({"novel": novel}, ensure_ascii=False),
                    "version": row.version,
                    "outdated": row.outdated,
                    "approved_at": row.approved_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                })
                created_chapter_states += 1

        conn.execute(text(
            "UPDATE projects SET current_stage = current_stage + 1 WHERE current_stage >= 3"
        ))
        conn.execute(
            text("INSERT INTO schema_migrations (name, applied_at) VALUES (:name, :now)"),
            {"name": migration_name, "now": now},
        )
    return {
        "already_applied": False,
        "states_shifted": moved_states,
        "approvals_shifted": moved_approvals,
        "chapter_states_created": created_chapter_states,
    }
