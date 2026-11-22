from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.paths import DATA_DIR
from app.database.models import (
    ApprovalRecord, Asset, Character, Episode, Extraction, GenerationJob,
    ProductionRevision, ProductionState, Project, Scene, Shot, ShotEntityLink, ShotImage,
)
from app.schemas.project import ProjectCreate, ProjectUpdate


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.created_at).all()


def get_project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return p


def create_project(db: Session, data: ProjectCreate) -> Project:
    p = Project(
        name=data.name,
        description=data.description,
        visual_style=data.visual_style,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_project(db: Session, project_id: str, data: ProjectUpdate) -> Project:
    p = get_project(db, project_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return p


def delete_project(db: Session, project_id: str) -> dict:
    """确认删除后清理项目域数据，不影响其他项目。"""
    p = get_project(db, project_id)
    episode_ids = [r[0] for r in db.query(Episode.id).filter(Episode.project_id == project_id).all()]
    state_ids = [r[0] for r in db.query(ProductionState.id).filter(ProductionState.project_id == project_id).all()]
    if state_ids:
        db.query(ProductionRevision).filter(ProductionRevision.state_id.in_(state_ids)).delete(synchronize_session=False)
    db.query(ApprovalRecord).filter(ApprovalRecord.project_id == project_id).delete(synchronize_session=False)
    db.query(ProductionState).filter(ProductionState.project_id == project_id).delete(synchronize_session=False)
    if episode_ids:
        shot_ids = [r[0] for r in db.query(Shot.id).filter(Shot.episode_id.in_(episode_ids)).all()]
        if shot_ids:
            db.query(ShotImage).filter(ShotImage.shot_id.in_(shot_ids)).delete(synchronize_session=False)
            db.query(ShotEntityLink).filter(ShotEntityLink.shot_id.in_(shot_ids)).delete(synchronize_session=False)
            db.query(GenerationJob).filter(GenerationJob.shot_id.in_(shot_ids)).delete(synchronize_session=False)
            db.query(Shot).filter(Shot.id.in_(shot_ids)).delete(synchronize_session=False)
        db.query(Episode).filter(Episode.id.in_(episode_ids)).delete(synchronize_session=False)
    db.query(GenerationJob).filter(GenerationJob.project_id == project_id).delete(synchronize_session=False)
    db.query(Extraction).filter(Extraction.project_id == project_id).delete(synchronize_session=False)
    db.query(Character).filter(Character.project_id == project_id).update({"reference_asset_id": None})
    db.query(Scene).filter(Scene.project_id == project_id).update({"reference_asset_id": None})
    db.query(Character).filter(Character.project_id == project_id).delete(synchronize_session=False)
    db.query(Scene).filter(Scene.project_id == project_id).delete(synchronize_session=False)
    db.query(Asset).filter(Asset.project_id == project_id).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    return {"deleted": project_id}
