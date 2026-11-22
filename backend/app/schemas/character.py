from datetime import datetime
from pydantic import BaseModel


class CharacterBase(BaseModel):
    name: str
    aliases: list[str] = []
    age_description: str | None = None
    appearance: str | None = None
    hairstyle: str | None = None
    clothing: str | None = None
    personality: str | None = None
    voice_style: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    status: str = "draft"


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    age_description: str | None = None
    appearance: str | None = None
    hairstyle: str | None = None
    clothing: str | None = None
    personality: str | None = None
    voice_style: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    status: str | None = None


class CharacterOut(CharacterBase):
    id: str
    project_id: str
    reference_asset_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
