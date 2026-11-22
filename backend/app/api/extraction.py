import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Extraction
from app.schemas.extraction import (
    ConfirmRequest,
    ConfirmResult,
    ExtractRequest,
    ExtractionOut,
)
from app.services import entity_extractor, entity_resolver, project_service

router = APIRouter(tags=["extraction"])


def _out(e: Extraction) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "status": e.status,
        "draft": json.loads(e.result_json),
        "created_at": e.created_at,
    }


@router.post("/projects/{project_id}/extract", response_model=ExtractionOut)
async def extract(
    project_id: str, data: ExtractRequest, db: Session = Depends(get_db)
):
    """AI 提取角色和场景 → 三级匹配 → 保存为草稿，等待人工确认。"""
    project_service.get_project(db, project_id)
    if not data.novel.strip():
        raise HTTPException(status_code=400, detail="小说内容不能为空")

    try:
        draft = await entity_extractor.extract_entities(data.novel)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 提取失败：{e}")

    draft = await entity_resolver.resolve_draft(db, project_id, draft)

    record = Extraction(
        project_id=project_id,
        novel_excerpt=data.novel[:500],
        result_json=json.dumps(draft, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _out(record)


@router.get("/extractions/{extraction_id}", response_model=ExtractionOut)
def get_extraction(extraction_id: str, db: Session = Depends(get_db)):
    record = db.get(Extraction, extraction_id)
    if not record:
        raise HTTPException(status_code=404, detail="提取记录不存在")
    return _out(record)


@router.post("/extractions/{extraction_id}/confirm", response_model=ConfirmResult)
def confirm_extraction(
    extraction_id: str, data: ConfirmRequest, db: Session = Depends(get_db)
):
    """用户审核后确认，草稿正式写入角色/场景表。"""
    record = db.get(Extraction, extraction_id)
    if not record:
        raise HTTPException(status_code=404, detail="提取记录不存在")
    if record.status == "confirmed":
        raise HTTPException(status_code=400, detail="该提取结果已确认过")

    result = entity_resolver.confirm_draft(
        db, record.project_id, data.draft.model_dump()
    )
    record.status = "confirmed"
    record.result_json = json.dumps(data.draft.model_dump(), ensure_ascii=False)
    db.commit()
    return result
