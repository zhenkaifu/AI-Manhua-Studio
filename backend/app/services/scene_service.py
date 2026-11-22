import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import Scene
from app.schemas.scene import SceneCreate, SceneUpdate


def _serialize(s: Scene) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "name": s.name,
        "aliases": json.loads(s.aliases or "[]"),
        "location_type": s.location_type,
        "environment": s.environment,
        "architecture": s.architecture,
        "lighting": s.lighting,
        "atmosphere": s.atmosphere,
        "visual_prompt": s.visual_prompt,
        "reference_asset_id": s.reference_asset_id,
        "status": s.status,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def list_scenes(db: Session, project_id: str) -> list[dict]:
    rows = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.created_at)
        .all()
    )
    return [_serialize(s) for s in rows]


def get_scene(db: Session, scene_id: str) -> Scene:
    s = db.get(Scene, scene_id)
    if not s:
        raise HTTPException(status_code=404, detail="场景不存在")
    return s


def get_scene_out(db: Session, scene_id: str) -> dict:
    return _serialize(get_scene(db, scene_id))


def create_scene(db: Session, project_id: str, data: SceneCreate) -> dict:
    s = Scene(
        project_id=project_id,
        name=data.name,
        aliases=json.dumps(data.aliases, ensure_ascii=False),
        location_type=data.location_type,
        environment=data.environment,
        architecture=data.architecture,
        lighting=data.lighting,
        atmosphere=data.atmosphere,
        visual_prompt=data.visual_prompt,
        status=data.status,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize(s)


def update_scene(db: Session, scene_id: str, data: SceneUpdate) -> dict:
    s = get_scene(db, scene_id)
    patch = data.model_dump(exclude_unset=True)
    if "aliases" in patch:
        patch["aliases"] = json.dumps(patch["aliases"], ensure_ascii=False)
    for key, value in patch.items():
        setattr(s, key, value)
    db.commit()
    db.refresh(s)
    return _serialize(s)


def delete_scene(db: Session, scene_id: str) -> dict:
    s = get_scene(db, scene_id)
    s.reference_asset_id = None
    db.delete(s)
    db.commit()
    return {"deleted": scene_id}
