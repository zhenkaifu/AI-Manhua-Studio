import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from ai import generate_episode
from schemas import Episode
from app.api import (
    assets,
    characters,
    episodes,
    extraction,
    image_generation,
    production,
    projects,
    props,
    scenes,
    shots,
)
from app.core.config import settings
from app.workers import generation_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database.migrations import (
        migrate_generation_progress,
        migrate_production_system,
        migrate_prompt_editing,
        migrate_shot_image_versions,
        migrate_story_first_workflow,
    )
    result = migrate_shot_image_versions()
    if result["columns_added"] or result["versions_backfilled"]:
        print(f"[migrations] shot_images 版本管理迁移完成: {result}")
    result65 = migrate_prompt_editing()
    if result65["columns_added"]:
        print(f"[migrations] Prompt 编辑迁移完成: {result65}")
    progress_result = migrate_generation_progress()
    if progress_result["columns_added"]:
        print(f"[migrations] 生成进度迁移完成: {progress_result}")
    production_result = migrate_production_system()
    if production_result["columns_added"]:
        print(f"[migrations] 制作工作流迁移完成: {production_result}")
    story_first_result = migrate_story_first_workflow()
    if not story_first_result["already_applied"]:
        print(f"[migrations] Story Bible 优先流程迁移完成: {story_first_result}")
    generation_worker.start()
    yield


app = FastAPI(
    title="AI Manhua Studio",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:7100",
        "http://127.0.0.1:7100",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Phase 2：角色与场景资产系统 API
for router in (
    projects.router,
    characters.router,
    scenes.router,
    props.router,
    assets.router,
    extraction.router,
    episodes.router,
    shots.router,
    image_generation.router,
    production.router,
):
    app.include_router(router, prefix=settings.api_prefix)


class NovelRequest(BaseModel):
    novel: str


@app.get("/")
def home():
    return {"message": "AI Manhua Studio is running"}


@app.post("/generate")
async def generate(request: NovelRequest):
    if not request.novel.strip():
        raise HTTPException(status_code=400, detail="Novel cannot be empty")

    try:
        raw = await generate_episode(request.novel)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="AI 返回的内容不是合法 JSON，请重试",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"调用配置的 AI 模型失败：{e}")

    try:
        episode = Episode(**raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"AI 输出不符合剧本数据结构：{e.errors()}",
        )

    total_duration = sum(shot.duration for shot in episode.shots)

    file_id = uuid.uuid4().hex[:8]
    out_path = OUTPUT_DIR / f"episode_{episode.episode:03d}_{file_id}.json"
    out_path.write_text(
        json.dumps(episode.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "episode": episode.model_dump(),
        "shots": len(episode.shots),
        "duration": total_duration,
        "file": str(out_path),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
