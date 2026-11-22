import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.paths import PROJECT_ROOT
from app.database.models import Episode, Shot
from app.schemas.episode import EpisodeImport

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _shot_out(s: Shot) -> dict:
    return {
        "id": s.id,
        "episode_id": s.episode_id,
        "shot_index": s.shot_index,
        "duration": s.duration,
        "scene": s.scene,
        "camera": s.camera,
        "characters": json.loads(s.characters_json or "[]"),
        "action": s.action,
        "dialogue": s.dialogue,
        "visual_prompt": s.visual_prompt,
        "custom_prompt": s.custom_prompt,
        "custom_negative_prompt": s.custom_negative_prompt,
        "production_outdated": s.production_outdated,
    }


def _episode_out(db: Session, e: Episode) -> dict:
    shots = db.query(Shot).filter(Shot.episode_id == e.id).all()
    return {
        "id": e.id,
        "project_id": e.project_id,
        "episode_number": e.episode_number,
        "title": e.title,
        "summary": e.summary,
        "plan": json.loads(e.plan_json or "{}"),
        "shot_count": len(shots),
        "total_duration": sum(s.duration for s in shots),
        "created_at": e.created_at,
    }


def list_episodes(db: Session, project_id: str) -> list[dict]:
    rows = (
        db.query(Episode)
        .filter(Episode.project_id == project_id)
        .order_by(Episode.created_at)
        .all()
    )
    return [_episode_out(db, e) for e in rows]


def get_episode(db: Session, episode_id: str) -> Episode:
    e = db.get(Episode, episode_id)
    if not e:
        raise HTTPException(status_code=404, detail="剧集不存在")
    return e


def get_episode_detail(db: Session, episode_id: str) -> dict:
    e = get_episode(db, episode_id)
    shots = (
        db.query(Shot)
        .filter(Shot.episode_id == e.id)
        .order_by(Shot.shot_index)
        .all()
    )
    return {**_episode_out(db, e), "shots": [_shot_out(s) for s in shots]}


def save_episode(
    db: Session,
    project_id: str,
    data: EpisodeImport,
    json_payload: dict | None = None,
) -> dict:
    """把一集剧本（含分镜）写入数据库，同时保留 Phase 1 的 JSON 文件。"""
    e = Episode(
        project_id=project_id,
        episode_number=data.episode,
        title=data.title,
        summary=data.summary,
        source_novel=(data.source_novel or "")[:500] or None,
    )
    db.add(e)
    db.flush()

    for shot in data.shots:
        db.add(
            Shot(
                episode_id=e.id,
                shot_index=shot.id,
                duration=shot.duration,
                scene=shot.scene,
                camera=shot.camera,
                characters_json=json.dumps(shot.characters, ensure_ascii=False),
                action=shot.action,
                dialogue=shot.dialogue,
                visual_prompt=shot.visual_prompt,
            )
        )

    # 保留原始 JSON 文件（Phase 1 的既有行为）
    file_id = uuid.uuid4().hex[:8]
    out_path = OUTPUT_DIR / f"episode_{data.episode:03d}_{file_id}.json"
    payload = json_payload if json_payload is not None else data.model_dump()
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    e.json_path = str(out_path)

    db.commit()
    db.refresh(e)
    return _episode_out(db, e)


def get_shot(db: Session, shot_id: str) -> Shot:
    s = db.get(Shot, shot_id)
    if not s:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return s


def get_shot_out(db: Session, shot_id: str) -> dict:
    return _shot_out(get_shot(db, shot_id))
