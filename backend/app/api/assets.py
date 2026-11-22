from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.asset import AssetOut
from app.services import asset_service

router = APIRouter(tags=["assets"])


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
def list_assets(project_id: str, db: Session = Depends(get_db)):
    return asset_service.list_assets(db, project_id)


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    a = asset_service.get_asset(db, asset_id)
    return asset_service._serialize(a)


@router.get("/assets/{asset_id}/file")
def get_asset_file(asset_id: str, db: Session = Depends(get_db)):
    path, mime = asset_service.get_asset_file(db, asset_id)
    return FileResponse(path, media_type=mime)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    return asset_service.delete_asset(db, asset_id)
