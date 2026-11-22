import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from fastapi import APIRouter, Body, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.paths import PROJECT_ROOT
from app.database.connection import get_db
from app.database.models import Episode, Shot
from app.services import episode_service, production_service, project_service, workflow_service

router = APIRouter(tags=["production-workflow"])


class NovelTextRequest(BaseModel):
    name: str = "未命名小说"
    text: str


class ResumeRequest(BaseModel):
    stage: int
    episode_id: str | None = None


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def read_novel_upload(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    data = file.file.read()
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("小说文件不能超过 30 MB")
    if suffix == ".txt":
        for encoding in ("utf-8-sig", "gb18030", "utf-16"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("TXT 编码无法识别")
    if suffix == ".docx":
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        return "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    if suffix == ".epub":
        parts = []
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            for name in archive.namelist():
                if name.lower().endswith((".xhtml", ".html", ".htm")):
                    parser = _HTMLText()
                    parser.feed(archive.read(name).decode("utf-8", errors="ignore"))
                    parts.extend(parser.parts)
        return "\n\n".join(parts)
    raise ValueError("仅支持 TXT、DOCX、EPUB")


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return workflow_service.dashboard(db)


@router.get("/projects/{project_id}/workflow")
def get_workflow(project_id: str, db: Session = Depends(get_db)):
    return workflow_service.project_workflow(db, project_id)


@router.post("/projects/{project_id}/resume")
def resume_project(project_id: str, data: ResumeRequest, db: Session = Depends(get_db)):
    workflow_service.require_unlocked(db, project_id, data.stage)
    project = workflow_service.get_project(db, project_id)
    project.current_stage = data.stage
    project.last_active_episode_id = data.episode_id
    db.commit()
    return workflow_service.project_workflow(db, project_id)


@router.get("/projects/{project_id}/workflow/{stage}")
def get_stage(project_id: str, stage: int, episode_id: str | None = None, db: Session = Depends(get_db)):
    global_state = workflow_service.get_state(db, project_id, stage)
    result = workflow_service.state_out(global_state, workflow_service.is_unlocked(db, project_id, stage))
    if episode_id:
        episode_state = workflow_service.get_state(db, project_id, stage, episode_id)
        result["episode_state"] = workflow_service.state_out(episode_state, result["unlocked"])
    return result


@router.put("/projects/{project_id}/workflow/{stage}")
def save_stage(project_id: str, stage: int, content: dict = Body(...), episode_id: str | None = None, db: Session = Depends(get_db)):
    workflow_service.require_unlocked(db, project_id, stage)
    if stage == 2:
        production_service.sync_plan_episodes(db, project_id, content)
    return workflow_service.save_content(db, project_id, stage, content, episode_id)


@router.post("/projects/{project_id}/workflow/{stage}/reject")
def reject_stage(project_id: str, stage: int, episode_id: str | None = None, note: str | None = Body(None), db: Session = Depends(get_db)):
    return workflow_service.reject(db, project_id, stage, episode_id, note)


@router.post("/projects/{project_id}/workflow/{stage}/approve")
def approve_stage(project_id: str, stage: int, episode_id: str | None = None, note: str | None = Body(None), db: Session = Depends(get_db)):
    production_service.validate_approval(db, project_id, stage, episode_id)
    return workflow_service.approve(db, project_id, stage, episode_id, note)


@router.get("/production-states/{state_id}/revisions")
def get_revisions(state_id: str, db: Session = Depends(get_db)):
    return workflow_service.revisions(db, state_id)


@router.post("/projects/{project_id}/novel")
def import_novel_text(project_id: str, data: NovelTextRequest, db: Session = Depends(get_db)):
    novel = production_service.parse_novel(data.text, data.name)
    project = project_service.get_project(db, project_id)
    project.novel_name = data.name
    db.commit()
    return workflow_service.save_content(db, project_id, 1, {"novel": novel}, note="导入小说")


@router.post("/projects/{project_id}/novel/import")
async def import_novel_file(project_id: str, file: UploadFile, db: Session = Depends(get_db)):
    try:
        text = read_novel_upload(file)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(422, str(exc))
    name = Path(file.filename or "未命名小说").stem
    novel = production_service.parse_novel(text, name)
    project = project_service.get_project(db, project_id)
    project.novel_name = name
    db.commit()
    return workflow_service.save_content(db, project_id, 1, {"novel": novel}, note="上传小说文件")


@router.post("/projects/{project_id}/workflow/{stage}/generate")
async def generate_stage(project_id: str, stage: int, episode_id: str | None = None, db: Session = Depends(get_db)):
    if stage == 1:
        return await production_service.analyze_story(db, project_id)
    if stage == 2:
        return await production_service.generate_episode_plan(db, project_id)
    if stage == 3:
        if not episode_id:
            from fastapi import HTTPException
            raise HTTPException(400, "请选择剧集")
        return await production_service.generate_script(db, project_id, episode_id)
    if stage == 5:
        if not episode_id:
            from fastapi import HTTPException
            raise HTTPException(400, "请选择剧集")
        return await production_service.generate_storyboard(db, project_id, episode_id)
    from fastapi import HTTPException
    raise HTTPException(400, "该阶段没有 AI 生成操作")


@router.post("/projects/{project_id}/workflow/{stage}/review")
async def review_stage(project_id: str, stage: int, episode_id: str | None = None, db: Session = Depends(get_db)):
    if stage in (3, 5):
        return await production_service.review_content(db, project_id, stage, episode_id)
    if stage == 4:
        return production_service.asset_quality(db, project_id)
    if stage == 5:
        return production_service.storyboard_quality(db, episode_id)
    from fastapi import HTTPException
    raise HTTPException(400, "该阶段没有 AI 审阅操作")


@router.get("/episodes/{episode_id}/storyboard-quality")
def storyboard_quality(episode_id: str, db: Session = Depends(get_db)):
    return production_service.storyboard_quality(db, episode_id)


@router.put("/shots/{shot_id}/production")
def update_shot(shot_id: str, values: dict = Body(...), db: Session = Depends(get_db)):
    shot = episode_service.get_shot(db, shot_id)
    allowed = {"shot_index", "duration", "scene", "camera", "action", "dialogue", "visual_prompt", "custom_prompt", "custom_negative_prompt"}
    for key, value in values.items():
        if key in allowed:
            setattr(shot, key, value)
    if "characters" in values:
        shot.characters_json = json.dumps(values["characters"], ensure_ascii=False)
    shot.production_outdated = True
    db.commit()
    return episode_service.get_shot_out(db, shot_id)


@router.post("/shots/{shot_id}/duplicate")
def duplicate_shot(shot_id: str, db: Session = Depends(get_db)):
    source = episode_service.get_shot(db, shot_id)
    shots = db.query(Shot).filter(Shot.episode_id == source.episode_id).order_by(Shot.shot_index).all()
    for shot in reversed(shots):
        if shot.shot_index > source.shot_index:
            shot.shot_index += 1
    copy = Shot(
        episode_id=source.episode_id, shot_index=source.shot_index + 1,
        duration=source.duration, scene=source.scene, camera=source.camera,
        characters_json=source.characters_json, action=source.action,
        dialogue=source.dialogue, visual_prompt=source.visual_prompt,
        production_outdated=True,
    )
    db.add(copy)
    db.commit()
    return episode_service.get_shot_out(db, copy.id)


@router.put("/episodes/{episode_id}/shots/reorder")
def reorder_shots(episode_id: str, shot_ids: list[str] = Body(...), db: Session = Depends(get_db)):
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
    by_id = {s.id: s for s in shots}
    if set(shot_ids) != set(by_id):
        from fastapi import HTTPException
        raise HTTPException(400, "镜头排序列表不完整")
    for index, shot_id in enumerate(shot_ids, 1):
        by_id[shot_id].shot_index = index
        by_id[shot_id].production_outdated = True
    db.commit()
    return episode_service.get_episode_detail(db, episode_id)


@router.get("/episodes/{episode_id}/readiness")
def readiness(episode_id: str, db: Session = Depends(get_db)):
    return production_service.package_validation(db, episode_id)


@router.get("/episodes/{episode_id}/production-package")
def production_package(episode_id: str, db: Session = Depends(get_db)):
    return production_service.build_production_package(db, episode_id)


@router.get("/episodes/{episode_id}/production-package/download")
def download_production_package(episode_id: str, db: Session = Depends(get_db)):
    production_service.build_production_package(db, episode_id)
    path = PROJECT_ROOT / "output" / "production_packages" / f"{episode_id}.json"
    return FileResponse(path, media_type="application/json", filename=f"production_{episode_id}.json")
