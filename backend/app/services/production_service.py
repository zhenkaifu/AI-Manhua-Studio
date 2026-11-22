import json
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.paths import PROJECT_ROOT
from app.database.models import (
    Asset, Character, Episode, GenerationJob, ProductionState, Scene, Shot, ShotImage,
)
from app.providers.llm_provider import get_llm_provider
from app.services import entity_linker, episode_service, workflow_service

MAX_CONTEXT_CHARS = 28000


def parse_novel(text: str, name: str = "未命名小说") -> dict:
    text = text.replace("\r\n", "\r").replace("\r", "\n").strip()
    if not text:
        raise HTTPException(400, "小说内容不能为空")
    matches = list(re.finditer(r"(?m)^\s*(第[0-9零一二三四五六七八九十百千两]+[章节回卷][^\n]*)$", text))
    chapters = []
    if matches:
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end():end].strip()
            chapters.append({"id": f"chapter_{index + 1:03d}", "title": match.group(1).strip(), "content": body})
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        size = 20
        for index in range(0, len(paragraphs), size):
            chapters.append({
                "id": f"chapter_{index // size + 1:03d}",
                "title": f"原文片段 {index // size + 1}",
                "content": "\n\n".join(paragraphs[index:index + size]),
            })
    for chapter in chapters:
        chapter["paragraphs"] = [p.strip() for p in chapter["content"].splitlines() if p.strip()]
    return {"name": name, "text": text, "chapters": chapters, "character_count": len(text)}


async def analyze_story(db: Session, project_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 1)
    state = workflow_service.get_state(db, project_id, 1)
    data = workflow_service.content(state)
    novel = data.get("novel")
    if not novel:
        raise HTTPException(409, "请先导入小说原文")
    workflow_service.set_status(db, project_id, 1, "AI_GENERATING")
    system = """你是专业中文漫剧文学策划。根据小说建立可供后续改编使用的 Story Bible。
只输出合法 JSON，不要 Markdown。结构：
{"world_rules":[],"character_profiles":[{"name":"","role":"主角/配角","profile":"","personality":"","development":""}],"relationships":[],"locations":[],"factions":[],"main_storyline":"","secondary_storylines":[],"timeline":[],"important_events":[],"plot_points":[],"foreshadowing":[],"conflicts":[],"dramatic_turning_points":[],"narrative_constraints":[]}
必须忠于原著，区分主要与次要角色，保留因果、伏笔和人物行为约束；未知信息不要编造。"""
    try:
        bible = await get_llm_provider().generate_json(system, novel["text"][:MAX_CONTEXT_CHARS])
        payload = {**data, "story_bible": bible, "analysis_truncated": len(novel["text"]) > MAX_CONTEXT_CHARS}
        return workflow_service.save_content(db, project_id, 1, payload, note="AI Story Bible", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 1, "FAILED")
        raise HTTPException(502, f"小说分析失败：{exc}")


async def generate_episode_plan(db: Session, project_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 2)
    analysis = workflow_service.content(workflow_service.get_state(db, project_id, 1))
    system = """你是中文短剧总策划。依据 Story Bible 和原著规划 1-6 集漫剧，每集 60-180 秒。
只输出合法 JSON：{"episodes":[{"episode_number":1,"title":"","source_chapters":[],"main_plot":"","key_characters":[],"main_conflict":"","opening_hook":"","dramatic_highlights":[],"climax":"","cliffhanger":"","scene_requirements":[],"estimated_duration":90}]}
不得牺牲原著因果来制造悬念，重要事件不得遗漏。"""
    prompt = "以下是创作资料，仅供阅读：\n" + json.dumps({"story_bible": analysis.get("story_bible"), "chapters": analysis.get("novel", {}).get("chapters", [])}, ensure_ascii=False)[:MAX_CONTEXT_CHARS] + "\n\n现在执行创作任务：不要复制以上资料。只输出一个新 JSON 对象，根节点必须是 episodes，其值是剧集规划数组。不要输出 story_bible 或 chapters。"
    workflow_service.set_status(db, project_id, 2, "AI_GENERATING")
    try:
        result = await get_llm_provider().generate_json(system, prompt)
        episodes = result.get("episodes") or result.get("episode_plan")
        if not isinstance(episodes, list) or not episodes:
            raise ValueError("模型没有返回 episodes 剧集列表，请重试")
        result = {"episodes": episodes}
        sync_plan_episodes(db, project_id, result)
        return workflow_service.save_content(db, project_id, 2, result, note="AI 剧集规划", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 2, "FAILED")
        raise HTTPException(502, f"剧集规划失败：{exc}")


def sync_plan_episodes(db: Session, project_id: str, plan: dict):
    project = workflow_service.get_project(db, project_id)
    for item in plan.get("episodes", []):
        number = int(item.get("episode_number", 1))
        episode = db.query(Episode).filter(Episode.project_id == project_id, Episode.episode_number == number).first()
        if not episode:
            episode = Episode(project_id=project_id, episode_number=number, title=item.get("title") or f"第 {number} 集")
            db.add(episode)
        episode.title = item.get("title") or episode.title
        episode.summary = item.get("main_plot") or episode.summary
        episode.plan_json = json.dumps(item, ensure_ascii=False)
        item["id"] = item.get("id") or episode.id
        db.flush()
        item["id"] = episode.id
    project.updated_at = workflow_service.utcnow()
    db.commit()


async def generate_script(db: Session, project_id: str, episode_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 3)
    episode = episode_service.get_episode(db, episode_id)
    analysis = workflow_service.content(workflow_service.get_state(db, project_id, 1))
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    system = """你是专业中文漫剧编剧。根据原著、Story Bible、剧集规划写生产级剧本。
只输出合法 JSON：{"title":"","summary":"","scenes":[{"scene_number":1,"location":"","time_environment":"","characters":[],"action":"","dialogue":[{"character":"","line":"","emotion":""}],"internal_monologue":"","narration":"","transition":"","pacing":""}]}
保持人物性格、世界规则、原著事件和因果，不直接输出分镜或镜头。"""
    prompt = "以下是剧本创作资料，仅供阅读：\n" + json.dumps({
        "episode_plan": json.loads(episode.plan_json or "{}"),
        "story_bible": analysis.get("story_bible"),
        "characters": [{"name": c.name, "personality": c.personality, "appearance": c.appearance} for c in characters],
        "original_novel": analysis.get("novel", {}).get("text", "")[:16000],
    }, ensure_ascii=False)[:MAX_CONTEXT_CHARS] + "\n\n现在执行创作任务：不要复制以上资料。只输出新的剧本 JSON，必须包含 title、summary 和非空 scenes 场景列表。"
    workflow_service.set_status(db, project_id, 3, "AI_GENERATING", episode_id)
    try:
        script = await get_llm_provider().generate_json(system, prompt)
        if not isinstance(script.get("scenes"), list) or not script["scenes"]:
            raise ValueError("模型没有返回 scenes 场景列表，请重试")
        episode.title = script.get("title") or episode.title
        episode.summary = script.get("summary") or episode.summary
        db.commit()
        return workflow_service.save_content(db, project_id, 3, script, episode_id, "AI 剧本", True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 3, "FAILED", episode_id)
        raise HTTPException(502, f"剧本生成失败：{exc}")


async def review_content(db: Session, project_id: str, stage: int, episode_id: str | None = None) -> dict:
    state = workflow_service.get_state(db, project_id, stage, episode_id)
    labels = {3: "剧本", 5: "分镜"}
    if stage not in labels:
        raise HTTPException(400, "该阶段使用结构化质量检查")
    system = f"""你是{labels[stage]}质量审阅 Agent。检查剧情与人物一致性、遗漏事件、对白、节奏、逻辑、视觉呈现。
只输出 JSON：{{"score":0,"summary":"","issues":[{{"severity":"high/medium/low","location":"","issue":"","suggestion":""}}]}}。不要直接修改内容。"""
    result = await get_llm_provider().generate_json(system, json.dumps(workflow_service.content(state), ensure_ascii=False)[:MAX_CONTEXT_CHARS])
    data = workflow_service.content(state)
    data["quality_review"] = result
    return workflow_service.save_content(db, project_id, stage, data, episode_id, "AI 质量审阅", True)


async def generate_storyboard(db: Session, project_id: str, episode_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 5)
    script_state = workflow_service.get_state(db, project_id, 3, episode_id)
    if script_state.status != "APPROVED":
        raise HTTPException(409, "请先审批当前剧集剧本")
    episode = episode_service.get_episode(db, episode_id)
    system = """你是专业漫剧分镜导演。把已审批剧本转成 8-20 个可生图镜头。
只输出 JSON：{"shots":[{"id":1,"duration":6,"scene":"","camera":"wide shot/medium shot/close-up/low angle/high angle","characters":[],"action":"","dialogue":"","visual_prompt":"详细英文画面提示词","camera_movement":"","expression":"","narration":"","lighting":"","composition":""}]}
保留全部关键动作和对白，视觉提示词忠于剧本，不新编人物外观。"""
    workflow_service.set_status(db, project_id, 5, "AI_GENERATING", episode_id)
    script_data = workflow_service.content(script_state)
    script_lines = [f"标题：{script_data.get('title', episode.title)}", f"梗概：{script_data.get('summary', '')}"]
    for scene in script_data.get("scenes", []):
        script_lines.append(f"场景 {scene.get('scene_number', '')}，{scene.get('location', '')}，{scene.get('time_environment', '')}")
        script_lines.append(f"角色：{'、'.join(scene.get('characters', [])) if isinstance(scene.get('characters'), list) else scene.get('characters', '')}")
        script_lines.append(f"动作：{scene.get('action', '')}")
        for line in scene.get("dialogue", []):
            if isinstance(line, dict):
                script_lines.append(f"{line.get('character', '')}：{line.get('line', '')}")
            else:
                script_lines.append(str(line))
        if scene.get("narration"):
            script_lines.append(f"旁白：{scene['narration']}")
    prompt = "请把以下已审批剧本改编为 8-20 个连续分镜。保留关键动作和对白，不新编人物外观。\n输出根节点必须是 shots，每个元素包含 id、duration、scene、camera、characters、action、dialogue、visual_prompt。visual_prompt 使用详细英文。\n剧本：\n" + "\n".join(script_lines)[:MAX_CONTEXT_CHARS] + "\n现在输出分镜 JSON，不要复述剧本。"
    try:
        result = await get_llm_provider().generate_json(system, prompt)
        if not isinstance(result.get("shots"), list) or not result["shots"]:
            raise ValueError("模型没有返回 shots 分镜列表，请重试")
        existing = {s.shot_index: s for s in db.query(Shot).filter(Shot.episode_id == episode_id).all()}
        output_ids = []
        for index, item in enumerate(result.get("shots", []), 1):
            number_match = re.search(r"\d+", str(item.get("id", index)))
            number = int(number_match.group()) if number_match else index
            shot = existing.get(number)
            dialogue = item.get("dialogue", "")
            if isinstance(dialogue, list):
                dialogue = "\n".join(
                    f"{line.get('character', '')}：{line.get('line', '')}" if isinstance(line, dict) else str(line)
                    for line in dialogue
                )
            elif not isinstance(dialogue, str):
                dialogue = str(dialogue)
            duration_match = re.search(r"\d+(?:\.\d+)?", str(item.get("duration", 6)))
            duration = max(1, round(float(duration_match.group()))) if duration_match else 6
            values = {
                "duration": duration, "scene": item.get("scene", ""),
                "camera": item.get("camera", "medium shot"), "action": item.get("action", ""),
                "dialogue": dialogue, "visual_prompt": item.get("visual_prompt", ""),
                "characters_json": json.dumps(item.get("characters", []), ensure_ascii=False),
            }
            if shot:
                changed = any(getattr(shot, key) != value for key, value in values.items())
                for key, value in values.items():
                    setattr(shot, key, value)
                shot.production_outdated = changed
            else:
                shot = Shot(episode_id=episode_id, shot_index=number, **values)
                db.add(shot)
                db.flush()
            item["shot_id"] = shot.id
            output_ids.append(shot.id)
        db.commit()
        await entity_linker.link_episode(db, episode_id)
        result["episode_id"] = episode.id
        return workflow_service.save_content(db, project_id, 5, result, episode_id, "AI 分镜", True)
    except Exception as exc:
        db.rollback()
        workflow_service.set_status(db, project_id, 5, "FAILED", episode_id)
        raise HTTPException(502, f"分镜生成失败：{exc}")


def asset_quality(db: Session, project_id: str) -> dict:
    issues = []
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    scenes = db.query(Scene).filter(Scene.project_id == project_id).all()
    for entity, kind in [(c, "角色") for c in characters] + [(s, "场景") for s in scenes]:
        if not entity.reference_asset_id:
            issues.append({"severity": "high", "target_id": entity.id, "issue": f"{kind}「{entity.name}」缺少参考图", "suggestion": "上传或生成参考图"})
    for rows, kind in ((characters, "角色"), (scenes, "场景")):
        names = {}
        for entity in rows:
            names.setdefault(entity.name.strip().lower(), []).append(entity.name)
        for values in names.values():
            if len(values) > 1:
                issues.append({"severity": "medium", "issue": f"疑似重复{kind}：{'、'.join(values)}", "suggestion": "合并或更名"})
    return {"score": max(0, 100 - len(issues) * 10), "summary": f"发现 {len(issues)} 项资产问题", "issues": issues}


def storyboard_quality(db: Session, episode_id: str) -> dict:
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).order_by(Shot.shot_index).all()
    issues = []
    for shot in shots:
        links = entity_linker.list_shot_links(db, shot.id)
        unresolved = [l for l in links if l["status"] == "unresolved"]
        if unresolved:
            issues.append({"severity": "high", "location": f"镜头 {shot.shot_index}", "issue": "存在未识别角色或场景", "suggestion": "完成资产关联"})
        if not shot.visual_prompt:
            issues.append({"severity": "high", "location": f"镜头 {shot.shot_index}", "issue": "缺少视觉提示词", "suggestion": "补充 Prompt"})
    return {"score": max(0, 100 - len(issues) * 10), "summary": f"检查 {len(shots)} 个镜头，发现 {len(issues)} 项问题", "issues": issues}


def validate_approval(db: Session, project_id: str, stage: int, episode_id: str | None):
    if stage == 1:
        data = workflow_service.content(workflow_service.get_state(db, project_id, 1))
        if not data.get("story_bible"):
            raise HTTPException(409, "请先生成 Story Bible")
    elif stage == 2:
        plan = workflow_service.content(workflow_service.get_state(db, project_id, 2))
        if not plan.get("episodes"):
            raise HTTPException(409, "剧集规划不能为空")
        sync_plan_episodes(db, project_id, plan)
    elif stage == 3:
        state = workflow_service.get_state(db, project_id, 3, episode_id)
        if not workflow_service.content(state).get("scenes"):
            raise HTTPException(409, "剧本至少需要一个场景")
    elif stage == 4:
        quality = asset_quality(db, project_id)
        if any(i["severity"] == "high" for i in quality["issues"]):
            raise HTTPException(409, "仍有角色或场景缺少参考图")
        state = workflow_service.get_state(db, project_id, 4)
        existing = workflow_service.content(state)
        state.content_json = json.dumps({**existing, "quality": quality}, ensure_ascii=False)
        db.commit()
    elif stage == 5:
        if not db.query(Shot).filter(Shot.episode_id == episode_id).count():
            raise HTTPException(409, "请先生成分镜")
    elif stage == 6:
        shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
        missing = []
        for shot in shots:
            selected = db.query(ShotImage).filter(ShotImage.shot_id == shot.id, ShotImage.is_selected.is_(True)).first()
            if not selected or shot.production_outdated:
                missing.append(shot.shot_index)
        if not shots or missing:
            raise HTTPException(409, f"镜头 {missing} 尚未选择有效定稿图")
    elif stage == 7:
        package_validation(db, episode_id)


def package_validation(db: Session, episode_id: str) -> dict:
    episode = episode_service.get_episode(db, episode_id)
    project_id = episode.project_id
    states = db.query(ProductionState).filter(ProductionState.episode_id == episode_id).all()
    approved = {s.stage for s in states if s.status == "APPROVED"}
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
    missing_images = [s.shot_index for s in shots if not db.query(ShotImage).filter(ShotImage.shot_id == s.id, ShotImage.is_selected.is_(True)).first()]
    checks = {
        "script_approved": 3 in approved,
        "storyboard_approved": 5 in approved,
        "images_approved": 6 in approved,
        "all_shots_have_images": not missing_images,
        "character_assets_approved": workflow_service.get_state(db, project_id, 4).status == "APPROVED",
    }
    return {"ready": all(checks.values()), "checks": checks, "missing_images": missing_images}


def build_production_package(db: Session, episode_id: str) -> dict:
    validation = package_validation(db, episode_id)
    episode = episode_service.get_episode(db, episode_id)
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).order_by(Shot.shot_index).all()
    script = workflow_service.content(workflow_service.get_state(db, episode.project_id, 3, episode_id))
    characters = db.query(Character).filter(Character.project_id == episode.project_id).all()
    scenes = db.query(Scene).filter(Scene.project_id == episode.project_id).all()
    shot_rows = []
    for shot in shots:
        selected = db.query(ShotImage).filter(ShotImage.shot_id == shot.id, ShotImage.is_selected.is_(True)).first()
        jobs = db.query(GenerationJob).filter(GenerationJob.shot_id == shot.id).all()
        shot_rows.append({
            **episode_service.get_shot_out(db, shot.id),
            "entity_links": entity_linker.list_shot_links(db, shot.id),
            "approved_image": {"shot_image_id": selected.id, "asset_id": selected.asset_id, "version": selected.version} if selected else None,
            "generation_history": [{"job_id": j.id, "status": j.status, "model": j.workflow_name, "seed": j.seed, "created_at": j.created_at.isoformat()} for j in jobs],
        })
    package = {
        "schema_version": "1.0", "package_id": f"package_{uuid.uuid4().hex[:12]}",
        "episode": episode_service.get_episode_detail(db, episode_id), "approved_script": script,
        "characters": [{"id": c.id, "name": c.name, "visual_prompt": c.visual_prompt, "reference_asset_id": c.reference_asset_id} for c in characters],
        "scenes": [{"id": s.id, "name": s.name, "visual_prompt": s.visual_prompt, "reference_asset_id": s.reference_asset_id} for s in scenes],
        "props": workflow_service.content(workflow_service.get_state(db, episode.project_id, 4)).get("props", []), "shots": shot_rows,
        "asset_manifest": [{"asset_id": a.id, "type": a.asset_type, "path": a.file_path} for a in db.query(Asset).filter(Asset.project_id == episode.project_id).all()],
        "validation": validation,
    }
    directory = PROJECT_ROOT / "output" / "production_packages"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{episode_id}.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return package
