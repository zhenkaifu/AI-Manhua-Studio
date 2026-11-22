from datetime import datetime
from pydantic import BaseModel


class ExtractRequest(BaseModel):
    novel: str


class ExtractedCharacter(BaseModel):
    """AI 提取的角色草稿。decision: create 新建 / merge 合并进 target_id / skip 忽略。"""

    name: str
    aliases: list[str] = []
    age_description: str | None = None
    appearance: str | None = None
    hairstyle: str | None = None
    clothing: str | None = None
    personality: str | None = None
    visual_prompt: str | None = None
    confidence: float | None = None
    evidence: str | None = None
    match_level: str = "new"  # exact / semantic / new
    target_id: str | None = None
    target_name: str | None = None
    decision: str = "create"  # create / merge / skip


class ExtractedScene(BaseModel):
    name: str
    aliases: list[str] = []
    location_type: str | None = None
    environment: str | None = None
    architecture: str | None = None
    lighting: str | None = None
    atmosphere: str | None = None
    visual_prompt: str | None = None
    confidence: float | None = None
    evidence: str | None = None
    match_level: str = "new"
    target_id: str | None = None
    target_name: str | None = None
    decision: str = "create"


class ExtractionDraft(BaseModel):
    characters: list[ExtractedCharacter] = []
    scenes: list[ExtractedScene] = []


class ExtractionOut(BaseModel):
    id: str
    project_id: str
    status: str
    draft: ExtractionDraft
    created_at: datetime


class ConfirmRequest(BaseModel):
    draft: ExtractionDraft


class ConfirmResult(BaseModel):
    created_characters: list[str] = []
    merged_characters: list[str] = []
    created_scenes: list[str] = []
    merged_scenes: list[str] = []
