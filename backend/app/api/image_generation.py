from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services import image_generation_service

router = APIRouter(tags=["image-generation"])


class GenerateRequest(BaseModel):
    variations: int = Field(default=2, ge=1, le=4)
    width: int = Field(default=1024, ge=512, le=1536)
    height: int = Field(default=576, ge=512, le=1536)
    steps: int = Field(default=6, ge=4, le=12)
    upscale: int = Field(default=2, ge=1, le=2)


@router.post("/shots/{shot_id}/generate")
def generate_shot(
    shot_id: str, data: GenerateRequest, db: Session = Depends(get_db)
):
    """为一个分镜创建生成任务（自动读取角色/场景档案构建 Prompt）。"""
    return image_generation_service.create_job_for_shot(
        db, shot_id, data.variations, data.width, data.height, data.steps, data.upscale
    )


@router.post("/characters/{character_id}/generate")
def generate_character(character_id: str, db: Session = Depends(get_db)):
    """根据角色档案生成设定图，成功后自动设为当前参考图。"""
    return image_generation_service.create_job_for_entity(
        db, "character", character_id
    )


@router.post("/scenes/{scene_id}/generate")
def generate_scene(scene_id: str, db: Session = Depends(get_db)):
    """根据场景档案生成场景图，成功后自动设为当前参考图。"""
    return image_generation_service.create_job_for_entity(db, "scene", scene_id)


@router.post("/episodes/{episode_id}/generate-all")
def generate_episode(
    episode_id: str, data: GenerateRequest, db: Session = Depends(get_db)
):
    """为整集所有分镜批量创建生成任务。已有进行中任务的分镜会跳过。"""
    return image_generation_service.create_jobs_for_episode(
        db, episode_id, data.variations, data.width, data.height, data.steps, data.upscale
    )


@router.get("/generation-jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return image_generation_service.get_job_out(db, job_id)


@router.get("/projects/{project_id}/generation-jobs")
def list_jobs(project_id: str, status: str | None = None, db: Session = Depends(get_db)):
    return image_generation_service.list_jobs(db, project_id, status)


@router.post("/generation-jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    return image_generation_service.cancel_job(db, job_id)


@router.post("/generation-jobs/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db)):
    """失败/已取消的任务重新排队。"""
    return image_generation_service.retry_job(db, job_id)


@router.get("/shots/{shot_id}/images")
def list_shot_images(shot_id: str, db: Session = Depends(get_db)):
    """某个分镜的所有图片版本，按 version 升序。"""
    return image_generation_service.list_shot_images(db, shot_id)


@router.get("/shot-images/{image_id}")
def get_image_detail(image_id: str, db: Session = Depends(get_db)):
    """单张图片详情：版本、参考素材、完整生成参数。"""
    return image_generation_service.get_image_detail(db, image_id)


@router.get("/shots/{shot_id}/selected-image")
def get_selected_image(shot_id: str, db: Session = Depends(get_db)):
    """某个 Shot 当前选中的最终图片，没有选中时返回 null。"""
    return image_generation_service.get_selected_image(db, shot_id)


# ---------- Sprint 6.5：Prompt 编辑与重新生成 ----------

class PromptEditRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None


class RegenerateRequest(BaseModel):
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    steps: int = Field(default=6, ge=4, le=12)
    width: int = Field(default=1024, ge=512, le=1536)
    height: int = Field(default=576, ge=512, le=1536)
    variations: int = Field(default=1, ge=1, le=4)
    upscale: int = Field(default=2, ge=1, le=2)
    character_reference_ids: list[str] | None = None
    scene_reference_ids: list[str] | None = None


@router.get("/shots/{shot_id}/prompt")
def get_shot_prompt(shot_id: str, db: Session = Depends(get_db)):
    """分镜当前生效的 Prompt（自定义优先），含档案构建的原始版本。"""
    return image_generation_service.get_shot_prompt(db, shot_id)


@router.put("/shots/{shot_id}/prompt")
def save_shot_prompt(
    shot_id: str, data: PromptEditRequest, db: Session = Depends(get_db)
):
    """保存自定义 Prompt。不影响历史图片，不创建新版本。"""
    return image_generation_service.save_shot_prompt(
        db, shot_id, data.prompt, data.negative_prompt
    )


@router.post("/shots/{shot_id}/regenerate")
def regenerate_shot(
    shot_id: str, data: RegenerateRequest, db: Session = Depends(get_db)
):
    """用自定义 Prompt / 参数 / 参考图重新生成，创建新版本不覆盖旧图。"""
    return image_generation_service.regenerate_shot(
        db, shot_id,
        prompt=data.prompt,
        negative_prompt=data.negative_prompt,
        seed=data.seed,
        steps=data.steps,
        width=data.width,
        height=data.height,
        variations=data.variations,
        upscale=data.upscale,
        character_reference_ids=data.character_reference_ids,
        scene_reference_ids=data.scene_reference_ids,
    )


@router.post("/shot-images/{image_id}/select")
def select_image(image_id: str, db: Session = Depends(get_db)):
    return image_generation_service.select_image(db, image_id)


@router.get("/episodes/{episode_id}/gallery")
def episode_gallery(episode_id: str, db: Session = Depends(get_db)):
    """分镜画廊：一集所有分镜的候选图和任务状态，一次查全。"""
    return image_generation_service.episode_gallery(db, episode_id)
