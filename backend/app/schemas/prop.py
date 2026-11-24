from datetime import datetime
from pydantic import BaseModel


class PropBase(BaseModel):
    name: str
    description: str | None = None
    narrative_significance: str | None = None
    visual_prompt: str | None = None


class PropCreate(PropBase):
    pass


class PropUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    narrative_significance: str | None = None
    visual_prompt: str | None = None
    reference_asset_id: str | None = None


class PropOut(PropBase):
    id: str
    project_id: str
    reference_asset_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
