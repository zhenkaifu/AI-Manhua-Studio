from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.schemas.prop import PropCreate, PropOut, PropUpdate
from app.services import asset_service, image_generation_service, project_service, prop_service

router = APIRouter(tags=["props"])


@router.get("/projects/{project_id}/props", response_model=list[PropOut])
def list_props(project_id: str, db: Session = Depends(get_db)):
    return prop_service.list_props(db, project_id)


@router.post("/projects/{project_id}/props", response_model=PropOut)
def create_prop(project_id: str, data: PropCreate, db: Session = Depends(get_db)):
    project_service.get_project(db, project_id)
    return prop_service.create_prop(db, project_id, data)


@router.put("/props/{prop_id}", response_model=PropOut)
def update_prop(prop_id: str, data: PropUpdate, db: Session = Depends(get_db)):
    return prop_service.update_prop(db, prop_id, data)


@router.delete("/props/{prop_id}")
def delete_prop(prop_id: str, db: Session = Depends(get_db)):
    return prop_service.delete_prop(db, prop_id)


@router.post("/props/{prop_id}/generate")
def generate_prop(prop_id: str, db: Session = Depends(get_db)):
    return image_generation_service.create_job_for_entity(db, "prop", prop_id)


@router.post("/props/{prop_id}/reference-image")
async def upload_reference(prop_id: str, file: UploadFile, db: Session = Depends(get_db)):
    prop = prop_service.get_prop(db, prop_id)
    asset = await asset_service.save_upload(db, prop.project_id, file, "prop_reference", f"props/{prop_id}")
    prop.reference_asset_id = asset["id"]
    db.commit()
    return asset
