from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.episode import ResolveRequest, ShotLinksUpdate
from app.services import entity_linker

router = APIRouter(tags=["shots"])


@router.get("/shots/{shot_id}/entity-links")
def get_shot_links(shot_id: str, db: Session = Depends(get_db)):
    return entity_linker.list_shot_links(db, shot_id)


@router.put("/shots/{shot_id}/entity-links")
def update_shot_links(
    shot_id: str, data: ShotLinksUpdate, db: Session = Depends(get_db)
):
    """人工整体替换该分镜的关联关系。"""
    return entity_linker.set_shot_links(db, shot_id, data.links)


@router.post("/shots/{shot_id}/resolve-entity")
def resolve_entity(
    shot_id: str, data: ResolveRequest, db: Session = Depends(get_db)
):
    """处理未识别提及：link 关联已有 / create 新建草稿 / ignore 忽略。"""
    return entity_linker.resolve_entity(db, shot_id, data)


@router.get("/shots/{shot_id}/generation-context")
def generation_context(shot_id: str, db: Session = Depends(get_db)):
    """Phase 3 图片生成所需的完整数据（只读，不生成图片）。"""
    return entity_linker.generation_context(db, shot_id)
