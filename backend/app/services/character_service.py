import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import Character
from app.schemas.character import CharacterCreate, CharacterUpdate


def _serialize(c: Character) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "name": c.name,
        "aliases": json.loads(c.aliases or "[]"),
        "age_description": c.age_description,
        "appearance": c.appearance,
        "hairstyle": c.hairstyle,
        "clothing": c.clothing,
        "personality": c.personality,
        "voice_style": c.voice_style,
        "visual_prompt": c.visual_prompt,
        "negative_prompt": c.negative_prompt,
        "reference_asset_id": c.reference_asset_id,
        "status": c.status,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def list_characters(db: Session, project_id: str) -> list[dict]:
    rows = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
        .all()
    )
    return [_serialize(c) for c in rows]


def get_character(db: Session, character_id: str) -> Character:
    c = db.get(Character, character_id)
    if not c:
        raise HTTPException(status_code=404, detail="角色不存在")
    return c


def get_character_out(db: Session, character_id: str) -> dict:
    return _serialize(get_character(db, character_id))


def create_character(db: Session, project_id: str, data: CharacterCreate) -> dict:
    c = Character(
        project_id=project_id,
        name=data.name,
        aliases=json.dumps(data.aliases, ensure_ascii=False),
        age_description=data.age_description,
        appearance=data.appearance,
        hairstyle=data.hairstyle,
        clothing=data.clothing,
        personality=data.personality,
        voice_style=data.voice_style,
        visual_prompt=data.visual_prompt,
        negative_prompt=data.negative_prompt,
        status=data.status,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize(c)


def update_character(db: Session, character_id: str, data: CharacterUpdate) -> dict:
    c = get_character(db, character_id)
    patch = data.model_dump(exclude_unset=True)
    if "aliases" in patch:
        patch["aliases"] = json.dumps(patch["aliases"], ensure_ascii=False)
    for key, value in patch.items():
        setattr(c, key, value)
    db.commit()
    db.refresh(c)
    return _serialize(c)


def delete_character(db: Session, character_id: str) -> dict:
    c = get_character(db, character_id)
    # 不删除引用图片本身，只解除关联，避免其他内容失去资产
    c.reference_asset_id = None
    db.delete(c)
    db.commit()
    return {"deleted": character_id}
