from datetime import datetime
from pydantic import BaseModel


class ShotIn(BaseModel):
    """与 Phase 1 剧本 JSON 中的镜头结构一致。"""

    id: int
    duration: int
    scene: str = ""
    camera: str = ""
    characters: list[str] = []
    action: str = ""
    dialogue: str = ""
    visual_prompt: str = ""


class EpisodeImport(BaseModel):
    episode: int = 1
    title: str
    summary: str = ""
    shots: list[ShotIn]
    source_novel: str | None = None


class EpisodeGenerateRequest(BaseModel):
    novel: str


class ShotOut(BaseModel):
    id: str
    episode_id: str
    shot_index: int
    duration: int
    scene: str | None
    camera: str | None
    characters: list[str]
    action: str | None
    dialogue: str | None
    visual_prompt: str | None


class EpisodeOut(BaseModel):
    id: str
    project_id: str
    episode_number: int
    title: str
    summary: str | None
    shot_count: int
    total_duration: int
    created_at: datetime


class EntityLinkOut(BaseModel):
    id: str
    shot_id: str
    entity_type: str
    entity_id: str | None
    entity_name: str | None  # 关联到的角色/场景当前名字
    reference_asset_id: str | None
    mention_text: str
    match_method: str
    confidence: float | None
    status: str


class ShotLinksUpdate(BaseModel):
    """手动整体替换一个分镜的关联（保留 mention_text）。"""

    links: list[dict]  # [{entity_type, entity_id|null, mention_text, status}]


class ResolveRequest(BaseModel):
    mention_text: str
    entity_type: str  # character / scene
    action: str  # link / create / ignore
    entity_id: str | None = None  # action=link 时必填
    name: str | None = None  # action=create 时使用，默认用 mention_text
