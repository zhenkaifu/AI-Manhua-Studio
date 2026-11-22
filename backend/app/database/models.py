from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base
from app.utils.id_generator import generate_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("project")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_style: Mapped[str] = mapped_column(
        String(100), default="Chinese 2.5D Donghua"
    )
    novel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_stage: Mapped[int] = mapped_column(Integer, default=1)
    last_active_episode_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("character")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[str] = mapped_column(Text, default="[]")  # JSON 字符串
    age_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    hairstyle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clothing: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_style: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", use_alter=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("scene")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    location_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    environment: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lighting: Mapped[str | None] = mapped_column(String(255), nullable=True)
    atmosphere: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", use_alter=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("asset")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(50))  # character_reference / scene_reference
    file_path: Mapped[str] = mapped_column(String(500))  # 相对 data/ 的路径
    mime_type: Mapped[str] = mapped_column(String(50))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Extraction(Base):
    """AI 从小说提取的角色/场景草稿，确认后才写入正式表。"""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("extraction")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    novel_excerpt: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)  # 草稿 JSON（含匹配结果）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Episode(Base):
    """Phase 1 生成的一集剧本（入库版本，JSON 文件仍会保留）。"""

    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("episode")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    episode_number: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_novel: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("shot")
    )
    episode_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("episodes.id"), index=True
    )
    shot_index: Mapped[int] = mapped_column(Integer)  # 剧本中的镜头编号
    duration: Mapped[int] = mapped_column(Integer)
    scene: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera: Mapped[str | None] = mapped_column(String(100), nullable=True)
    characters_json: Mapped[str] = mapped_column(Text, default="[]")  # 名字列表
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    dialogue: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sprint 6.5：用户编辑保存的自定义 Prompt（不影响历史图片记录）
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_outdated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GenerationJob(Base):
    """一次图片生成任务，目标可以是分镜、角色或场景。"""

    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("job")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    episode_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("episodes.id"), index=True, nullable=True
    )
    shot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shots.id"), index=True, nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(20), default="shot", index=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(20), default="comfyui")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending / running / completed / failed / cancelled
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_variation: Mapped[int] = mapped_column(Integer, default=0)
    result_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id", use_alter=True), nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_name: Mapped[str] = mapped_column(String(50), default="z_image_turbo")
    variations: Mapped[int] = mapped_column(Integer, default=2)
    seed: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=576)
    steps: Mapped[int] = mapped_column(Integer, default=6)
    upscale: Mapped[int] = mapped_column(Integer, default=2)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Sprint 6.5：参考图覆盖（JSON {"character": [...], "scene": [...]}），空则自动从上下文取
    reference_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ShotImage(Base):
    """一个分镜的候选图片，重新生成只新增不覆盖。"""

    __tablename__ = "shot_images"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("img")
    )
    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id"), index=True
    )
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"))
    generation_job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_jobs.id")
    )
    variation_index: Mapped[int] = mapped_column(Integer)
    # Sprint 6 Task 6.1：每 Shot 内全局自增的版本号，(shot_id, version) 有唯一索引
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 实际提交给 ComfyUI 的参考图 asset_id 列表（JSON 数组字符串）
    character_reference_asset_ids: Mapped[str] = mapped_column(Text, default="[]")
    scene_reference_asset_ids: Mapped[str] = mapped_column(Text, default="[]")
    is_selected: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ShotEntityLink(Base):
    """分镜与角色/场景档案的关联。保存 ID 而非名字，角色改名后关联仍有效。"""

    __tablename__ = "shot_entity_links"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("link")
    )
    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20))  # character / scene
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mention_text: Mapped[str] = mapped_column(String(255))  # 原文称呼
    match_method: Mapped[str] = mapped_column(String(20))  # exact/alias/semantic/manual
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # linked / pending / unresolved / ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class ProductionState(Base):
    """项目或单集在一个制作阶段的可持久化内容与审批状态。"""

    __tablename__ = "production_states"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("state")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    episode_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("episodes.id"), index=True, nullable=True
    )
    stage: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(30), default="NOT_STARTED")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    outdated: Mapped[bool] = mapped_column(default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, index=True
    )


class ProductionRevision(Base):
    """阶段内容每次保存或重新生成的不可变版本。"""

    __tablename__ = "production_revisions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("revision")
    )
    state_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_states.id"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApprovalRecord(Base):
    """人工审批记录，AI 流程不会写入此表。"""

    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: generate_id("approval")
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    episode_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("episodes.id"), index=True, nullable=True
    )
    stage: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20), default="approved")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
