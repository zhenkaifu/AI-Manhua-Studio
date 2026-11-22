import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import (
    ApprovalRecord,
    Asset,
    Character,
    Episode,
    ProductionRevision,
    ProductionState,
    Project,
    Scene,
    Shot,
    ShotImage,
)

STAGES = {
    1: "小说分析",
    2: "剧集规划",
    3: "剧本制作",
    4: "资产管理",
    5: "分镜制作",
    6: "图像生成与审核",
    7: "视频制作就绪",
}
ACTIVE_STATES = {"IN_PROGRESS", "AI_GENERATING", "REVIEW_REQUIRED", "NEEDS_REVISION", "FAILED"}


def utcnow():
    return datetime.now(timezone.utc)


def content(state: ProductionState) -> dict:
    return json.loads(state.content_json or "{}")


def state_out(state: ProductionState, unlocked: bool = True) -> dict:
    return {
        "id": state.id,
        "project_id": state.project_id,
        "episode_id": state.episode_id,
        "stage": state.stage,
        "stage_name": STAGES[state.stage],
        "status": state.status,
        "content": content(state),
        "version": state.version,
        "outdated": state.outdated,
        "approved_at": state.approved_at,
        "updated_at": state.updated_at,
        "unlocked": unlocked,
    }


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


def get_state(
    db: Session, project_id: str, stage: int, episode_id: str | None = None,
    create: bool = True,
) -> ProductionState | None:
    if stage not in STAGES:
        raise HTTPException(404, "制作阶段不存在")
    query = db.query(ProductionState).filter(
        ProductionState.project_id == project_id,
        ProductionState.stage == stage,
    )
    query = query.filter(ProductionState.episode_id == episode_id) if episode_id else query.filter(ProductionState.episode_id.is_(None))
    state = query.order_by(ProductionState.created_at).first()
    if not state and create:
        get_project(db, project_id)
        state = ProductionState(project_id=project_id, stage=stage, episode_id=episode_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def is_unlocked(db: Session, project_id: str, stage: int) -> bool:
    if stage == 1:
        return True
    previous = get_state(db, project_id, stage - 1)
    return previous.status == "APPROVED"


def require_unlocked(db: Session, project_id: str, stage: int):
    if not is_unlocked(db, project_id, stage):
        raise HTTPException(409, f"请先审批「{STAGES[stage - 1]}」")


def touch_project(db: Session, project_id: str, stage: int | None = None):
    project = get_project(db, project_id)
    project.updated_at = utcnow()
    if stage is not None:
        project.current_stage = stage
    db.commit()


def invalidate_downstream(db: Session, project_id: str, stage: int, episode_id: str | None):
    query = db.query(ProductionState).filter(
        ProductionState.project_id == project_id,
        ProductionState.stage > stage,
    )
    if episode_id:
        query = query.filter((ProductionState.episode_id == episode_id) | (ProductionState.episode_id.is_(None)))
    for downstream in query.all():
        if downstream.status != "NOT_STARTED":
            downstream.status = "NEEDS_REVISION"
        downstream.outdated = True
        downstream.approved_at = None
    if stage in (3, 5) and episode_id:
        for shot in db.query(Shot).filter(Shot.episode_id == episode_id).all():
            shot.production_outdated = True


def save_content(
    db: Session, project_id: str, stage: int, data: dict,
    episode_id: str | None = None, note: str = "手动保存",
    review_required: bool = False,
) -> dict:
    state = get_state(db, project_id, stage, episode_id)
    was_approved = state.status == "APPROVED"
    if state.content_json and state.content_json != "{}":
        db.add(ProductionRevision(
            state_id=state.id,
            revision_number=state.version,
            content_json=state.content_json,
            note=note,
        ))
        state.version += 1
    state.content_json = json.dumps(data, ensure_ascii=False)
    state.outdated = False
    state.approved_at = None
    state.status = "REVIEW_REQUIRED" if review_required else ("NEEDS_REVISION" if was_approved else "IN_PROGRESS")
    if was_approved:
        invalidate_downstream(db, project_id, stage, episode_id)
    project = get_project(db, project_id)
    project.current_stage = stage
    project.updated_at = utcnow()
    if episode_id:
        project.last_active_episode_id = episode_id
    db.commit()
    db.refresh(state)
    if stage > 3:
        global_state = get_state(db, project_id, stage)
        if global_state.status == "APPROVED":
            global_state.status = "NEEDS_REVISION"
            global_state.approved_at = None
            global_state.outdated = True
            db.commit()
    return state_out(state, is_unlocked(db, project_id, stage))


def set_status(db: Session, project_id: str, stage: int, status: str, episode_id: str | None = None):
    state = get_state(db, project_id, stage, episode_id)
    state.status = status
    state.updated_at = utcnow()
    db.commit()


def approve(db: Session, project_id: str, stage: int, episode_id: str | None = None, note: str | None = None) -> dict:
    require_unlocked(db, project_id, stage)
    state = get_state(db, project_id, stage, episode_id)
    if not content(state):
        raise HTTPException(409, "当前阶段还没有可审批的内容")
    if episode_id:
        state.status = "APPROVED"
        state.outdated = False
        state.approved_at = utcnow()
    global_state = get_state(db, project_id, stage)
    global_state.status = "APPROVED"
    global_state.content_json = state.content_json if not episode_id else json.dumps({"last_approved_episode_id": episode_id})
    global_state.outdated = False
    global_state.approved_at = utcnow()
    for item in {state, global_state}:
        db.add(ApprovalRecord(
            project_id=project_id, episode_id=item.episode_id, stage=stage,
            version=item.version, note=note,
        ))
    next_state = get_state(db, project_id, min(7, stage + 1)) if stage < 7 else None
    if next_state and next_state.status == "NOT_STARTED":
        next_state.status = "IN_PROGRESS"
    project = get_project(db, project_id)
    project.current_stage = min(7, stage + 1)
    project.updated_at = utcnow()
    if episode_id:
        project.last_active_episode_id = episode_id
    db.commit()
    return state_out(state, True)


def reject(db: Session, project_id: str, stage: int, episode_id: str | None = None, note: str | None = None):
    state = get_state(db, project_id, stage, episode_id)
    state.status = "NEEDS_REVISION"
    state.approved_at = None
    db.add(ApprovalRecord(project_id=project_id, episode_id=episode_id, stage=stage, version=state.version, action="rejected", note=note))
    db.commit()
    return state_out(state, is_unlocked(db, project_id, stage))


def project_workflow(db: Session, project_id: str) -> dict:
    project = get_project(db, project_id)
    states = [state_out(get_state(db, project_id, stage), is_unlocked(db, project_id, stage)) for stage in STAGES]
    return {"project_id": project_id, "current_stage": project.current_stage, "last_active_episode_id": project.last_active_episode_id, "stages": states}


def project_summary(db: Session, project: Project) -> dict:
    states = db.query(ProductionState).filter(ProductionState.project_id == project.id, ProductionState.episode_id.is_(None)).all()
    approved = [s.stage for s in states if s.status == "APPROVED"]
    current = next((s for s in states if s.status in ACTIVE_STATES), None)
    cover = (
        db.query(ShotImage).join(Shot, Shot.id == ShotImage.shot_id)
        .join(Episode, Episode.id == Shot.episode_id)
        .filter(Episode.project_id == project.id, ShotImage.is_selected.is_(True))
        .order_by(ShotImage.created_at.desc()).first()
    )
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "novel_name": project.novel_name,
        "visual_style": project.visual_style,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "current_stage": project.current_stage,
        "current_stage_name": STAGES[project.current_stage],
        "last_completed_stage": max(approved) if approved else 0,
        "status": "已完成制作准备" if 7 in approved else ("制作中" if states else "尚未开始"),
        "progress": round(len(set(approved)) / 7 * 100),
        "episode_count": db.query(Episode).filter(Episode.project_id == project.id).count(),
        "character_count": db.query(Character).filter(Character.project_id == project.id).count(),
        "scene_count": db.query(Scene).filter(Scene.project_id == project.id).count(),
        "cover_asset_id": cover.asset_id if cover else None,
        "last_active_episode_id": project.last_active_episode_id,
    }


def dashboard(db: Session) -> list[dict]:
    rows = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [project_summary(db, p) for p in rows]


def revisions(db: Session, state_id: str) -> list[dict]:
    rows = db.query(ProductionRevision).filter(ProductionRevision.state_id == state_id).order_by(ProductionRevision.revision_number.desc()).all()
    return [{"id": r.id, "revision_number": r.revision_number, "content": json.loads(r.content_json), "note": r.note, "created_at": r.created_at} for r in rows]
