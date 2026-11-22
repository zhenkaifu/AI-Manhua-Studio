from datetime import datetime
from pydantic import BaseModel


class SceneBase(BaseModel):
    name: str
    aliases: list[str] = []
    location_type: str | None = None  # indoor / outdoor
    environment: str | None = None
    architecture: str | None = None
    lighting: str | None = None
    atmosphere: str | None = None
    visual_prompt: str | None = None
    status: str = "draft"


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    location_type: str | None = None
    environment: str | None = None
    architecture: str | None = None
    lighting: str | None = None
    atmosphere: str | None = None
    visual_prompt: str | None = None
    status: str | None = None


class SceneOut(SceneBase):
    id: str
    project_id: str
    reference_asset_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
