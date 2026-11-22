from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.asset import AssetOut
from app.schemas.scene import SceneCreate, SceneOut, SceneUpdate
from app.services import asset_service, project_service, scene_service

router = APIRouter(tags=["scenes"])


@router.post("/projects/{project_id}/scenes", response_model=SceneOut)
def create_scene(
    project_id: str, data: SceneCreate, db: Session = Depends(get_db)
):
    project_service.get_project(db, project_id)
    return scene_service.create_scene(db, project_id, data)


@router.get("/projects/{project_id}/scenes", response_model=list[SceneOut])
def list_scenes(project_id: str, db: Session = Depends(get_db)):
    return scene_service.list_scenes(db, project_id)


@router.get("/scenes/{scene_id}", response_model=SceneOut)
def get_scene(scene_id: str, db: Session = Depends(get_db)):
    return scene_service.get_scene_out(db, scene_id)


@router.put("/scenes/{scene_id}", response_model=SceneOut)
def update_scene(scene_id: str, data: SceneUpdate, db: Session = Depends(get_db)):
    return scene_service.update_scene(db, scene_id, data)


@router.delete("/scenes/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    return scene_service.delete_scene(db, scene_id)


@router.post("/scenes/{scene_id}/reference-image", response_model=AssetOut)
async def upload_reference_image(
    scene_id: str, file: UploadFile, db: Session = Depends(get_db)
):
    scene = scene_service.get_scene(db, scene_id)
    asset = await asset_service.save_upload(
        db,
        project_id=scene.project_id,
        file=file,
        asset_type="scene_reference",
        subdir=f"scenes/{scene_id}",
    )
    asset_service.link_reference(db, "scene", scene_id, asset["id"])
    return asset
