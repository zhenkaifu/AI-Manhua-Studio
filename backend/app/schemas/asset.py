from datetime import datetime
from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    project_id: str
    asset_type: str
    file_path: str
    mime_type: str
    width: int | None
    height: int | None
    generation_model: str | None
    prompt: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
