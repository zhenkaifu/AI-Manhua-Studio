from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import Prop
from app.schemas.prop import PropCreate, PropUpdate


def list_props(db: Session, project_id: str):
    return db.query(Prop).filter(Prop.project_id == project_id).order_by(Prop.created_at).all()


def get_prop(db: Session, prop_id: str):
    prop = db.get(Prop, prop_id)
    if not prop:
        raise HTTPException(404, "道具不存在")
    return prop


def create_prop(db: Session, project_id: str, data: PropCreate):
    prop = Prop(project_id=project_id, **data.model_dump())
    db.add(prop); db.commit(); db.refresh(prop)
    return prop


def update_prop(db: Session, prop_id: str, data: PropUpdate):
    prop = get_prop(db, prop_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(prop, key, value)
    db.commit(); db.refresh(prop)
    return prop


def delete_prop(db: Session, prop_id: str):
    prop = get_prop(db, prop_id)
    prop.reference_asset_id = None
    db.delete(prop); db.commit()
    return {"deleted": prop_id}
