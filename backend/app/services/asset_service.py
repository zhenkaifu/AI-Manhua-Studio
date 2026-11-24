import struct
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.paths import DATA_DIR, PROJECTS_DIR
from app.database.models import Asset, Character, Prop, Scene

EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _image_size(data: bytes, mime: str) -> tuple[int | None, int | None]:
    """从文件头读取宽高，不依赖第三方图库。"""
    try:
        if mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if mime == "image/jpeg":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return w, h
                length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return None, None


def _serialize(a: Asset) -> dict:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "asset_type": a.asset_type,
        "file_path": a.file_path,
        "mime_type": a.mime_type,
        "width": a.width,
        "height": a.height,
        "generation_model": a.generation_model,
        "prompt": a.prompt,
        "created_at": a.created_at,
    }


async def save_upload(
    db: Session,
    project_id: str,
    file: UploadFile,
    asset_type: str,
    subdir: str,
) -> dict:
    """校验并保存上传图片，返回资产 dict。"""
    if file.content_type not in settings.allowed_image_types:
        raise HTTPException(status_code=400, detail="仅支持 PNG / JPEG / WebP 图片")

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="图片不能超过 10 MB")

    ext = EXT_BY_MIME[file.content_type]
    # 不使用用户原始文件名，生成安全的唯一名称
    rel_dir = Path("projects") / project_id / subdir
    abs_dir = DATA_DIR / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    rel_path = rel_dir / f"{uuid.uuid4().hex[:12]}{ext}"
    (DATA_DIR / rel_path).write_bytes(data)

    w, h = _image_size(data, file.content_type)

    asset = Asset(
        project_id=project_id,
        asset_type=asset_type,
        file_path=str(rel_path),
        mime_type=file.content_type,
        width=w,
        height=h,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _serialize(asset)


def list_assets(db: Session, project_id: str) -> list[dict]:
    rows = (
        db.query(Asset)
        .filter(Asset.project_id == project_id)
        .order_by(Asset.created_at.desc())
        .all()
    )
    return [_serialize(a) for a in rows]


def get_asset(db: Session, asset_id: str) -> Asset:
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="资产不存在")
    return a


def get_asset_file(db: Session, asset_id: str) -> tuple[Path, str]:
    a = get_asset(db, asset_id)
    path = DATA_DIR / a.file_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片文件已丢失")
    return path, a.mime_type


def delete_asset(db: Session, asset_id: str) -> dict:
    a = get_asset(db, asset_id)
    # 先解除角色和场景的引用，避免悬空外键
    db.query(Character).filter(Character.reference_asset_id == asset_id).update(
        {"reference_asset_id": None}
    )
    db.query(Scene).filter(Scene.reference_asset_id == asset_id).update(
        {"reference_asset_id": None}
    )
    db.query(Prop).filter(Prop.reference_asset_id == asset_id).update(
        {"reference_asset_id": None}
    )
    path = DATA_DIR / a.file_path
    db.delete(a)
    db.commit()
    if path.exists():
        path.unlink()
    return {"deleted": asset_id}


def link_reference(db: Session, entity: str, entity_id: str, asset_id: str) -> dict:
    """把资产设为角色或场景的参考图。"""
    asset = get_asset(db, asset_id)
    if entity == "character":
        obj = db.get(Character, entity_id)
        if not obj:
            raise HTTPException(status_code=404, detail="角色不存在")
    else:
        obj = db.get(Scene, entity_id)
        if not obj:
            raise HTTPException(status_code=404, detail="场景不存在")
    obj.reference_asset_id = asset.id
    db.commit()
    return {"linked": asset_id, "to": entity_id}
