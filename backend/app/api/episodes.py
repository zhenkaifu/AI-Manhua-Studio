import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai import generate_episode as ai_generate_episode
from app.database.connection import get_db
from app.schemas.episode import (
    EpisodeGenerateRequest,
    EpisodeImport,
    EpisodeOut,
)
from app.services import episode_service, project_service
from app.services import entity_linker

router = APIRouter(tags=["episodes"])


@router.post("/projects/{project_id}/episodes/generate", response_model=EpisodeOut)
async def generate_episode(
    project_id: str, data: EpisodeGenerateRequest, db: Session = Depends(get_db)
):
    """AI 生成一集剧本并直接入库（同时保留 output/ 下的 JSON 文件）。"""
    project_service.get_project(db, project_id)
    if not data.novel.strip():
        raise HTTPException(status_code=400, detail="小说内容不能为空")

    try:
        raw = await ai_generate_episode(data.novel)
        episode_data = EpisodeImport(
            episode=raw.get("episode", 1),
            title=raw.get("title", "未命名"),
            summary=raw.get("summary", ""),
            shots=raw.get("shots", []),
            source_novel=data.novel,
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI 返回的内容不是合法 JSON，请重试")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"AI 输出不符合剧本结构：{e.errors()}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"调用本地模型失败：{e}")

    return episode_service.save_episode(db, project_id, episode_data, json_payload=raw)


@router.post("/projects/{project_id}/episodes/import", response_model=EpisodeOut)
def import_episode(
    project_id: str, data: EpisodeImport, db: Session = Depends(get_db)
):
    """导入已有的剧本 JSON（例如 Phase 1 /generate 的产物）。"""
    project_service.get_project(db, project_id)
    return episode_service.save_episode(db, project_id, data)


@router.get("/projects/{project_id}/episodes")
def list_episodes(project_id: str, db: Session = Depends(get_db)):
    return episode_service.list_episodes(db, project_id)


@router.get("/episodes/{episode_id}")
def get_episode(episode_id: str, db: Session = Depends(get_db)):
    return episode_service.get_episode_detail(db, episode_id)


@router.post("/episodes/{episode_id}/link-entities")
async def link_entities(episode_id: str, db: Session = Depends(get_db)):
    """自动把整集分镜关联到角色/场景档案。人工修正过的关联会被保留。"""
    return await entity_linker.link_episode(db, episode_id)


@router.get("/episodes/{episode_id}/entity-links")
def episode_entity_links(episode_id: str, db: Session = Depends(get_db)):
    return entity_linker.list_episode_links(db, episode_id)
