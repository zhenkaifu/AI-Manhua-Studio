import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.paths import DATA_DIR
from app.database.models import (
    Asset,
    Character,
    Episode,
    GenerationJob,
    Prop,
    Project,
    Scene,
    Shot,
    ShotImage,
)
from app.services import entity_linker, prompt_builder
from app.services.episode_service import get_shot

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576  # 16:9 横版分镜
DEFAULT_STEPS = 6
DEFAULT_VARIATIONS = 2


class GenerationCancelled(Exception):
    """用户主动停止，不作为失败任务自动重试。"""


def _project_style(db: Session, project_id: str) -> str:
    project = db.get(Project, project_id)
    return project.visual_style if project else prompt_builder.DEFAULT_STYLE


def _job_out(j: GenerationJob, db: Session | None = None) -> dict:
    target_name = None
    if db:
        if j.target_type == "character":
            target = db.get(Character, j.target_id)
            target_name = target.name if target else "已删除角色"
        elif j.target_type == "scene":
            target = db.get(Scene, j.target_id)
            target_name = target.name if target else "已删除场景"
        elif j.target_type == "prop":
            target = db.get(Prop, j.target_id)
            target_name = target.name if target else "已删除道具"
        else:
            target = db.get(Shot, j.shot_id)
            target_name = f"镜头 {target.shot_index}" if target else "分镜"
    return {
        "id": j.id,
        "project_id": j.project_id,
        "episode_id": j.episode_id,
        "shot_id": j.shot_id,
        "target_type": j.target_type,
        "target_id": j.target_id or j.shot_id,
        "target_name": target_name,
        "provider": j.provider,
        "status": j.status,
        "progress": max(0, min(100, j.progress or 0)),
        "progress_message": j.progress_message,
        "current_variation": j.current_variation or 0,
        "result_asset_id": j.result_asset_id,
        "prompt": j.prompt,
        "negative_prompt": j.negative_prompt,
        "workflow_name": j.workflow_name,
        "variations": j.variations,
        "seed": j.seed,
        "width": j.width,
        "height": j.height,
        "steps": j.steps,
        "upscale": j.upscale,
        "attempts": j.attempts,
        "error_message": j.error_message,
        "created_at": j.created_at,
        "completed_at": j.completed_at,
    }


def get_job(db: Session, job_id: str) -> GenerationJob:
    j = db.get(GenerationJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="生成任务不存在")
    return j


def get_job_out(db: Session, job_id: str) -> dict:
    return _job_out(get_job(db, job_id), db)


def list_jobs(db: Session, project_id: str, status: str | None = None) -> list[dict]:
    q = db.query(GenerationJob).filter(GenerationJob.project_id == project_id)
    if status:
        q = q.filter(GenerationJob.status == status)
    jobs = q.order_by(GenerationJob.created_at.desc()).all()
    waiting = sorted(
        (j for j in jobs if j.status == "pending"), key=lambda j: j.created_at
    )
    positions = {j.id: i + 1 for i, j in enumerate(waiting)}
    result = []
    for job in jobs:
        item = _job_out(job, db)
        item["queue_position"] = positions.get(job.id)
        result.append(item)
    return result


def create_job_for_shot(
    db: Session,
    shot_id: str,
    variations: int = DEFAULT_VARIATIONS,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    upscale: int = 2,
) -> dict:
    """读取 Phase 2.5 的 generation-context，构建 Prompt，创建生成任务。"""
    shot = get_shot(db, shot_id)
    episode = db.get(Episode, shot.episode_id)

    # 同一分镜已有排队/运行中的任务时不重复创建
    existing = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.shot_id == shot_id,
            GenerationJob.status.in_(["pending", "running"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该分镜已有进行中的生成任务")

    context = entity_linker.generation_context(db, shot_id)
    visual_style = _project_style(db, episode.project_id)
    prompt, negative = prompt_builder.build_prompt(context, visual_style)

    job = GenerationJob(
        project_id=episode.project_id,
        episode_id=episode.id,
        shot_id=shot_id,
        target_type="shot",
        target_id=shot_id,
        progress_message="等待生成",
        prompt=prompt,
        negative_prompt=negative,
        variations=max(1, min(variations, 4)),
        seed=random.randint(0, 2**31 - 1),
        width=width,
        height=height,
        steps=steps,
        upscale=upscale,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    from app.workers import generation_worker
    generation_worker.enqueue(job.id)
    return _job_out(job)


def create_job_for_entity(
    db: Session, entity_type: str, entity_id: str
) -> dict:
    """从角色、场景或道具档案创建参考图任务，完成后自动回填参考图。"""
    if entity_type not in ("character", "scene", "prop"):
        raise HTTPException(status_code=400, detail="不支持的生成类型")
    model = {"character": Character, "scene": Scene, "prop": Prop}[entity_type]
    entity = db.get(model, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="资产档案不存在")
    existing = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.target_type == entity_type,
            GenerationJob.target_id == entity_id,
            GenerationJob.status.in_(["pending", "running"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该档案已有进行中的生成任务")

    visual_style = _project_style(db, entity.project_id)
    style = prompt_builder.style_settings(visual_style)
    if entity_type == "character":
        details = [
            entity.visual_prompt, entity.age_description, entity.appearance,
            entity.hairstyle, entity.clothing,
        ]
        subject = (
            "character reference sheet, single character, full body, clean neutral "
            "studio background, front view, expressive face, highly detailed character design"
        )
        negative = entity.negative_prompt or (
            "multiple characters, cropped head, cropped feet, blurry, low quality, "
            "text, watermark, busy background"
        )
    elif entity_type == "scene":
        details = [
            entity.visual_prompt, entity.environment, entity.architecture,
            entity.lighting, entity.atmosphere,
        ]
        subject = (
            "environment concept art, wide establishing shot, no people, coherent "
            "architecture, cinematic lighting, highly detailed"
        )
        negative = "people, character, blurry, low quality, text, watermark, distorted architecture"
    else:
        details = [entity.visual_prompt, entity.description, entity.narrative_significance]
        subject = (
            "prop design reference, single object, centered, full object visible, "
            "clean neutral studio background, highly detailed materials"
        )
        negative = "people, character, multiple objects, cropped object, blurry, text, watermark, busy background"
    prompt = style["prompt"] + ",\n" + subject + ". " + ". ".join(
        x.strip() for x in details if x and x.strip()
    )
    negative = negative + ", " + style["negative"]

    job = GenerationJob(
        project_id=entity.project_id,
        episode_id=None,
        shot_id=None,
        target_type=entity_type,
        target_id=entity_id,
        progress_message="等待生成",
        prompt=prompt,
        negative_prompt=negative,
        variations=1,
        seed=random.randint(0, 2**31 - 1),
        width=1024,
        height=1024,
        steps=DEFAULT_STEPS,
        upscale=2,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    from app.workers import generation_worker
    generation_worker.enqueue(job.id)
    return _job_out(job, db)


def create_jobs_for_episode(
    db: Session,
    episode_id: str,
    variations: int = DEFAULT_VARIATIONS,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    upscale: int = 2,
) -> dict:
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="剧集不存在")
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
    created, skipped = [], 0
    for shot in shots:
        try:
            job = create_job_for_shot(db, shot.id, variations, width, height, steps, upscale)
            created.append(job["id"])
        except HTTPException:
            skipped += 1
    return {"episode_id": episode_id, "created": created, "skipped": skipped}


def cancel_job(db: Session, job_id: str) -> dict:
    job = get_job(db, job_id)
    if job.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="该任务已结束，无法取消")
    was_running = job.status == "running"
    job.status = "cancelled"
    job.progress_message = "正在停止 ComfyUI 生成" if was_running else "已取消排队"
    job.error_message = None
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return _job_out(job, db)


def retry_job(db: Session, job_id: str) -> dict:
    """失败的任务重新排队。参数不变，生成结果只新增版本不覆盖。"""
    job = get_job(db, job_id)
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail="只有失败或已取消的任务可以重试")
    existing = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.target_type == job.target_type,
            GenerationJob.target_id == (job.target_id or job.shot_id),
            GenerationJob.status.in_(["pending", "running"]),
            GenerationJob.id != job.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该目标已有进行中的生成任务")
    job.status = "pending"
    job.progress = 0
    job.progress_message = "等待重试"
    job.current_variation = 0
    job.error_message = None
    job.completed_at = None
    db.commit()
    from app.workers import generation_worker
    generation_worker.enqueue(job.id)
    return _job_out(job, db)


# ---------- 候选图 ----------

def _image_out(db: Session, img: ShotImage) -> dict:
    asset = db.get(Asset, img.asset_id)
    job = db.get(GenerationJob, img.generation_job_id)
    return {
        "id": img.id,
        "shot_id": img.shot_id,
        "asset_id": img.asset_id,
        "generation_job_id": img.generation_job_id,
        "variation_index": img.variation_index,
        "version": img.version,
        "is_selected": img.is_selected,
        "character_reference_asset_ids": json.loads(
            img.character_reference_asset_ids or "[]"
        ),
        "scene_reference_asset_ids": json.loads(
            img.scene_reference_asset_ids or "[]"
        ),
        "width": asset.width if asset else None,
        "height": asset.height if asset else None,
        "generation_model": asset.generation_model if asset else None,
        "seed": job.seed + img.variation_index - 1 if job else None,
        "steps": job.steps if job else None,
        "prompt": job.prompt if job else None,
        "created_at": img.created_at,
    }


def get_image_detail(db: Session, image_id: str) -> dict:
    """单张图片详情：版本、参考素材、完整生成参数。"""
    img = db.get(ShotImage, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="图片不存在")
    out = _image_out(db, img)
    job = db.get(GenerationJob, img.generation_job_id)
    asset = db.get(Asset, img.asset_id)
    out["prompt"] = job.prompt if job else None
    out["negative_prompt"] = job.negative_prompt if job else None
    out["generation_params"] = (
        {
            "provider": job.provider,
            "seed": job.seed + img.variation_index - 1,
            "width": job.width,
            "height": job.height,
            "steps": job.steps,
            "upscale": job.upscale,
            "workflow_name": job.workflow_name,
        }
        if job
        else None
    )
    out["generation_model"] = asset.generation_model if asset else None
    return out


def get_selected_image(db: Session, shot_id: str) -> dict | None:
    """某个 Shot 当前选中的最终图片，没有则返回 None。"""
    img = (
        db.query(ShotImage)
        .filter(ShotImage.shot_id == shot_id, ShotImage.is_selected.is_(True))
        .first()
    )
    return get_image_detail(db, img.id) if img else None


def list_shot_images(db: Session, shot_id: str) -> list[dict]:
    rows = (
        db.query(ShotImage)
        .filter(ShotImage.shot_id == shot_id)
        .order_by(ShotImage.version, ShotImage.created_at)
        .all()
    )
    return [_image_out(db, r) for r in rows]


def select_image(db: Session, image_id: str) -> dict:
    img = db.get(ShotImage, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="图片不存在")
    db.query(ShotImage).filter(ShotImage.shot_id == img.shot_id).update(
        {"is_selected": False}
    )
    img.is_selected = True
    db.commit()
    db.refresh(img)
    return _image_out(db, img)


# ---------- Sprint 6：分镜画廊 ----------

def episode_gallery(db: Session, episode_id: str) -> dict:
    """一集所有分镜 + 候选图 + 任务状态，一次查全，供画廊页使用。"""
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="剧集不存在")
    shots = (
        db.query(Shot)
        .filter(Shot.episode_id == episode_id)
        .order_by(Shot.shot_index)
        .all()
    )
    result = []
    for shot in shots:
        active = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.shot_id == shot.id,
                GenerationJob.status.in_(["pending", "running"]),
            )
            .first()
        )
        last = (
            db.query(GenerationJob)
            .filter(GenerationJob.shot_id == shot.id)
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        result.append(
            {
                "shot_id": shot.id,
                "shot_index": shot.shot_index,
                "description": shot.action,
                "scene": shot.scene,
                "camera": shot.camera,
                "dialogue": shot.dialogue,
                "images": list_shot_images(db, shot.id),
                "active_job": _job_out(active) if active else None,
                "last_job_status": last.status if last else None,
                "last_job_id": last.id if last else None,
                "last_job_error": (
                    last.error_message if last and last.status == "failed" else None
                ),
            }
        )
    return {
        "episode_id": episode.id,
        "title": episode.title,
        "shots": result,
    }


# ---------- Sprint 6.5：Prompt 编辑与重新生成 ----------

def get_shot_prompt(db: Session, shot_id: str) -> dict:
    """返回分镜当前生效的 Prompt（自定义优先）和由档案构建的原始 Prompt。"""
    shot = get_shot(db, shot_id)
    episode = db.get(Episode, shot.episode_id)
    visual_style = _project_style(db, episode.project_id)
    style = prompt_builder.style_settings(visual_style)
    context = entity_linker.generation_context(db, shot_id)
    built_prompt, built_negative = prompt_builder.build_prompt(context, visual_style)
    return {
        "shot_id": shot_id,
        "prompt": prompt_builder.with_style(shot.custom_prompt, visual_style) if shot.custom_prompt else built_prompt,
        "negative_prompt": (shot.custom_negative_prompt + ", " + style["negative"]) if shot.custom_negative_prompt else built_negative,
        "built_prompt": built_prompt,
        "built_negative_prompt": built_negative,
        "is_custom": bool(shot.custom_prompt),
    }


def save_shot_prompt(
    db: Session, shot_id: str, prompt: str, negative_prompt: str | None
) -> dict:
    """保存自定义 Prompt。只更新 shots 表，不创建图片版本，不动历史记录。"""
    shot = get_shot(db, shot_id)
    if not (prompt or "").strip():
        raise HTTPException(status_code=400, detail="Prompt 不能为空")
    shot.custom_prompt = prompt.strip()
    shot.custom_negative_prompt = (negative_prompt or "").strip() or None
    db.commit()
    return get_shot_prompt(db, shot_id)


def regenerate_shot(
    db: Session,
    shot_id: str,
    prompt: str | None = None,
    negative_prompt: str | None = None,
    seed: int | None = None,
    steps: int = DEFAULT_STEPS,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    variations: int = 1,
    upscale: int = 2,
    character_reference_ids: list[str] | None = None,
    scene_reference_ids: list[str] | None = None,
) -> dict:
    """用自定义 Prompt / 参数 / 参考图重新生成。创建新任务，只新增不覆盖。"""
    shot = get_shot(db, shot_id)
    episode = db.get(Episode, shot.episode_id)

    # 防止重复提交：同一分镜有进行中的任务时拒绝
    existing = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.shot_id == shot_id,
            GenerationJob.status.in_(["pending", "running"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该分镜已有进行中的生成任务")

    # Prompt 优先级：显式传入 > 已保存的自定义 > 档案构建
    prompts = get_shot_prompt(db, shot_id)
    visual_style = _project_style(db, episode.project_id)
    style = prompt_builder.style_settings(visual_style)
    final_prompt = prompt_builder.with_style((prompt or "").strip() or prompts["prompt"], visual_style)
    final_negative = (negative_prompt or "").strip() or prompts["negative_prompt"]
    if style["negative"] not in final_negative:
        final_negative += ", " + style["negative"]

    # 参考图覆盖：验证每个 ID 存在且文件未丢失
    ref_override = None
    if character_reference_ids is not None or scene_reference_ids is not None:
        for aid in (character_reference_ids or []) + (scene_reference_ids or []):
            asset = db.get(Asset, aid)
            if not asset:
                raise HTTPException(status_code=400, detail=f"参考素材不存在: {aid}")
            if not (DATA_DIR / asset.file_path).exists():
                raise HTTPException(status_code=400, detail=f"参考素材文件已丢失: {aid}")
        ref_override = json.dumps(
            {
                "character": character_reference_ids or [],
                "scene": scene_reference_ids or [],
            }
        )

    job = GenerationJob(
        project_id=episode.project_id,
        episode_id=episode.id,
        shot_id=shot_id,
        target_type="shot",
        target_id=shot_id,
        progress_message="等待生成",
        prompt=final_prompt,
        negative_prompt=final_negative,
        variations=max(1, min(variations, 4)),
        seed=seed if seed is not None else random.randint(0, 2**31 - 1),
        width=width,
        height=height,
        steps=max(4, min(steps, 12)),
        upscale=upscale,
        reference_override=ref_override,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    from app.workers import generation_worker
    generation_worker.enqueue(job.id)
    return _job_out(job)


# ----------  Worker 执行入口 ----------

def _save_candidate(
    db: Session,
    job: GenerationJob,
    out_dir: Path,
    filename: str,
    data: bytes,
    variation_index: int,
    char_ref_ids: list[str],
    scene_ref_ids: list[str],
    max_retries: int = 5,
) -> ShotImage:
    """保存一张候选图：版本号分配 + 写文件 + 入库在同一事务，冲突自动重试。

    唯一索引 (shot_id, version) 兜底并发；即使重试失败也先把 PNG 写入磁盘，
    绝不丢失已成功生成的图片。
    """
    (out_dir / filename).write_bytes(data)  # 先落盘，图片永远不丢

    for attempt in range(max_retries):
        try:
            with db.begin_nested():  # SAVEPOINT：版本分配与写入同一事务
                version = (
                    db.query(func.max(ShotImage.version))
                    .filter(ShotImage.shot_id == job.shot_id)
                    .scalar()
                    or 0
                ) + 1
                asset = Asset(
                    project_id=job.project_id,
                    asset_type="shot_image",
                    file_path=str(
                        Path("projects") / job.project_id / "generated"
                        / job.episode_id / job.shot_id / filename
                    ),
                    mime_type="image/png",
                    width=job.width * job.upscale,
                    height=job.height * job.upscale,
                    generation_model="z-image-turbo-bf16",
                    prompt=job.prompt,
                )
                db.add(asset)
                db.flush()
                img = ShotImage(
                    shot_id=job.shot_id,
                    asset_id=asset.id,
                    generation_job_id=job.id,
                    variation_index=variation_index,
                    version=version,
                    character_reference_asset_ids=json.dumps(char_ref_ids),
                    scene_reference_asset_ids=json.dumps(scene_ref_ids),
                )
                db.add(img)
                db.flush()
            db.commit()
            return img
        except (IntegrityError, OperationalError):
            # 版本唯一冲突或 SQLite 写锁竞争：回滚后重试，图片已在磁盘不会丢
            db.rollback()
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"版本号分配重试 {max_retries} 次仍冲突（图片已保存在磁盘: {filename}）"
                )
            import time
            time.sleep(0.1 * (attempt + 1))
    raise RuntimeError("unreachable")


def _save_entity_reference(
    db: Session, job: GenerationJob, data: bytes, filename: str
) -> Asset:
    """保存档案生成图并设为当前参考图，旧资产仍保留在资产库。"""
    folder = {"character": "characters", "scene": "scenes", "prop": "props"}[job.target_type]
    rel_dir = Path("projects") / job.project_id / folder / job.target_id / "generated"
    out_dir = DATA_DIR / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_bytes(data)
    asset = Asset(
        project_id=job.project_id,
        asset_type=f"{job.target_type}_reference",
        file_path=str(rel_dir / filename),
        mime_type="image/png",
        width=job.width * job.upscale,
        height=job.height * job.upscale,
        generation_model="z-image-turbo-bf16",
        prompt=job.prompt,
    )
    db.add(asset)
    db.flush()
    model = {"character": Character, "scene": Scene, "prop": Prop}[job.target_type]
    entity = db.get(model, job.target_id)
    if not entity:
        raise RuntimeError("生成期间档案已被删除，图片已保留但无法回填")
    entity.reference_asset_id = asset.id
    job.result_asset_id = asset.id
    db.commit()
    return asset


async def run_job(job_id: str, provider) -> None:
    """执行分镜或档案图片任务，并把 ComfyUI 的真实采样进度写入数据库。"""
    from app.database.connection import SessionLocal

    COOLDOWN_SECONDS = 45  # 给 M2 降温的间隔

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job or job.status != "pending":
            return
        job.status = "running"
        job.progress = 1
        job.progress_message = "准备模型与生成参数"
        job.attempts += 1
        db.commit()

        if job.target_type == "shot":
            out_dir = (
                DATA_DIR / "projects" / job.project_id / "generated"
                / job.episode_id / job.shot_id
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            ref_paths, char_ref_ids, scene_ref_ids = [], [], []
            try:
                if job.reference_override:
                    override = json.loads(job.reference_override)
                    for aid in override.get("character", []):
                        a = db.get(Asset, aid)
                        if a and (DATA_DIR / a.file_path).exists():
                            ref_paths.append(DATA_DIR / a.file_path)
                            char_ref_ids.append(aid)
                    for aid in override.get("scene", []):
                        a = db.get(Asset, aid)
                        if a and (DATA_DIR / a.file_path).exists():
                            ref_paths.append(DATA_DIR / a.file_path)
                            scene_ref_ids.append(aid)
                else:
                    ctx = entity_linker.generation_context(db, job.shot_id)
                    for c in ctx.get("characters", []):
                        if c.get("reference_image"):
                            p = DATA_DIR / c["reference_image"]
                            if p.exists():
                                ref_paths.append(p)
                                char_ref_ids.append(c["reference_asset_id"])
                    scene = ctx.get("scene")
                    if scene and scene.get("reference_image"):
                        p = DATA_DIR / scene["reference_image"]
                        if p.exists():
                            ref_paths.append(p)
                            scene_ref_ids.append(scene["reference_asset_id"])
            except Exception:
                pass
            if len(ref_paths) > 1:
                keep = ref_paths[0]
                kept_char = char_ref_ids[:1]
                kept_scene = [] if char_ref_ids else scene_ref_ids[:1]
                ref_paths, char_ref_ids, scene_ref_ids = [keep], kept_char, kept_scene
        else:
            out_dir = None
            ref_paths, char_ref_ids, scene_ref_ids = [], [], []

        def is_cancelled():
            db.expire_all()
            current = db.get(GenerationJob, job_id)
            return not current or current.status == "cancelled"

        for i in range(job.variations):
            if is_cancelled():
                raise GenerationCancelled()
            if i > 0:
                job.progress = round(i / job.variations * 95)
                job.progress_message = f"设备冷却中，准备第 {i + 1}/{job.variations} 张"
                db.commit()
                for _ in range(COOLDOWN_SECONDS):
                    await asyncio.sleep(1)
                    if is_cancelled():
                        raise GenerationCancelled()
                db.expire_all()
                job = db.get(GenerationJob, job_id)
            job.current_variation = i + 1
            job.progress_message = f"第 {i + 1}/{job.variations} 张 · 等待 ComfyUI"
            db.commit()

            async def on_progress(percent: int, message: str):
                db.expire_all()
                current = db.get(GenerationJob, job_id)
                if not current or current.status == "cancelled":
                    return
                current.progress = max(
                    current.progress or 0,
                    min(95, round((i + percent / 100) / job.variations * 95)),
                )
                current.progress_message = f"第 {i + 1}/{job.variations} 张 · {message}"
                db.commit()

            seed = job.seed + i
            data = await provider.generate(
                job.prompt, job.negative_prompt or "",
                seed, job.width, job.height, job.steps, job.upscale,
                reference_paths=ref_paths,
                progress_callback=on_progress,
                cancel_callback=is_cancelled,
            )
            if is_cancelled():
                raise GenerationCancelled()
            db.expire_all()
            job = db.get(GenerationJob, job_id)
            filename = f"{'candidate' if job.target_type == 'shot' else job.target_type}_{i + 1:03d}_{seed}.png"
            if job.target_type == "shot":
                _save_candidate(
                    db, job, out_dir, filename, data, i + 1,
                    char_ref_ids, scene_ref_ids,
                )
            else:
                _save_entity_reference(db, job, data, filename)
            job.progress = round((i + 1) / job.variations * 95)
            job.progress_message = f"第 {i + 1}/{job.variations} 张已保存"
            db.commit()

        job.status = "completed"
        job.progress = 100
        job.progress_message = "生成完成"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        db.expire_all()
        job = db.get(GenerationJob, job_id)
        cancelled = isinstance(e, GenerationCancelled) or str(e) == "GENERATION_CANCELLED_BY_USER" or (job and job.status == "cancelled")
        if job and cancelled:
            job.status = "cancelled"
            job.progress_message = "已由用户停止"
            job.error_message = None
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        if job:
            job.progress_message = str(e)[:240]
            job.error_message = str(e)[:500]
            if job.attempts < 2:
                job.status = "pending"
                job.progress = 0
                job.current_variation = 0
                db.commit()
                from app.workers import generation_worker
                generation_worker.enqueue(job_id)
            else:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        raise
    finally:
        db.close()
