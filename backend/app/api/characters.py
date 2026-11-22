from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.asset import AssetOut
from app.schemas.character import CharacterCreate, CharacterOut, CharacterUpdate
from app.services import asset_service, character_service, project_service

router = APIRouter(tags=["characters"])


@router.post("/projects/{project_id}/characters", response_model=CharacterOut)
def create_character(
    project_id: str, data: CharacterCreate, db: Session = Depends(get_db)
):
    project_service.get_project(db, project_id)
    return character_service.create_character(db, project_id, data)


@router.get("/projects/{project_id}/characters", response_model=list[CharacterOut])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    return character_service.list_characters(db, project_id)


@router.get("/characters/{character_id}", response_model=CharacterOut)
def get_character(character_id: str, db: Session = Depends(get_db)):
    return character_service.get_character_out(db, character_id)


@router.put("/characters/{character_id}", response_model=CharacterOut)
def update_character(
    character_id: str, data: CharacterUpdate, db: Session = Depends(get_db)
):
    return character_service.update_character(db, character_id, data)


@router.delete("/characters/{character_id}")
def delete_character(character_id: str, db: Session = Depends(get_db)):
    return character_service.delete_character(db, character_id)


@router.post("/characters/{character_id}/reference-image", response_model=AssetOut)
async def upload_reference_image(
    character_id: str, file: UploadFile, db: Session = Depends(get_db)
):
    character = character_service.get_character(db, character_id)
    asset = await asset_service.save_upload(
        db,
        project_id=character.project_id,
        file=file,
        asset_type="character_reference",
        subdir=f"characters/{character_id}",
    )
    asset_service.link_reference(db, "character", character_id, asset["id"])
    return asset
