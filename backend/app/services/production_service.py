import json
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.paths import PROJECT_ROOT
from app.database.models import (
    Asset, Character, Episode, GenerationJob, ProductionState, Prop, Scene, Shot, ShotImage,
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
    """尊重用户创作方向，为 Story Bible 草稿提供可编辑的补全与建议。"""
    workflow_service.require_unlocked(db, project_id, 1)
    state = workflow_service.get_state(db, project_id, 1)
    data = workflow_service.content(state)
    draft = data.get("story_bible")
    if not isinstance(draft, dict) or not any(
        str(value).strip() for value in draft.values() if isinstance(value, str)
    ):
        raise HTTPException(409, "请先填写故事设定草稿，再获取 AI 建议")
    workflow_service.set_status(db, project_id, 1, "AI_GENERATING")
    system = """你是专业中文爽文与漫剧策划。用户是故事设定的最终决策者。
根据用户 Story Bible 草稿，补全漏洞、人物动机、核心爽点、节奏和长线冲突，给出可执行建议。
尊重用户确定的题材、主角、世界观和故事走向，不擅自推翻或替换核心设定，不虚构用户未要求的复杂设定。
只输出合法 JSON，不要 Markdown。结构：
{"story_bible":{"title":"","genre":"","target_audience":"","world_rules":[],"character_profiles":[{"name":"","role":"主角/配角","profile":"","personality":"","development":""}],"relationships":[],"locations":[],"factions":[],"main_storyline":"","secondary_storylines":[],"core_satisfactions":[],"important_events":[],"conflicts":[],"dramatic_turning_points":[],"narrative_constraints":[]},"suggestions":[{"category":"世界观/人物/爽点/剧情/节奏","issue":"","suggestion":""}]}
story_bible 是保留用户方向后的可编辑建议稿，suggestions 必须指出具体问题和修改理由。"""
    try:
        result = await get_llm_provider().generate_json(
            system,
            "请审阅并提出建议，不要复述任务。完整设定原文优先于结构化摘要：\n" + json.dumps({"story_bible": draft, "original_text": data.get("original_text", "")}, ensure_ascii=False)[:MAX_CONTEXT_CHARS],
        )
        bible = result.get("story_bible")
        suggestions = result.get("suggestions")
        if not isinstance(bible, dict) or not isinstance(suggestions, list):
            raise ValueError("模型没有返回 story_bible 和 suggestions，请重试")
        # 原文、来源文档和用户补充永远保留；结构化字段只是创作索引。
        payload = {**data, "story_bible": bible, "suggestions": suggestions}
        return workflow_service.save_content(db, project_id, 1, payload, note="AI 设定建议", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 1, "FAILED")
        raise HTTPException(502, f"设定建议生成失败：{exc}")


async def structure_story_document(db: Session, project_id: str, filename: str, text: str) -> dict:
    """把用户已有设定文档整理为可编辑 Story Bible，不自动审批。"""
    workflow_service.require_unlocked(db, project_id, 1)
    if not text.strip():
        raise HTTPException(422, "文档中没有可读取的文字；扫描版 PDF 请先进行 OCR")
    workflow_service.set_status(db, project_id, 1, "AI_GENERATING")
    system = """你是中文故事策划资料整理助手。把用户上传的设定文档整理为 Story Bible。
忠于文档，不把人物草稿改成小说正文，不擅自改变故事方向；文档没有的信息可以留空，不要编造。
只输出合法 JSON：{"story_bible":{"title":"","genre":"","target_audience":"","world_rules":[],"character_profiles":[{"name":"","role":"主角/配角","profile":"","personality":"","development":""}],"relationships":[],"main_storyline":"","core_satisfactions":[],"dramatic_turning_points":[],"narrative_constraints":[]},"suggestions":[{"category":"文档整理","issue":"","suggestion":""}]}
main_storyline 必须汇总文档中已有的故事走向。suggestions 只指出需要用户确认或补充的事项。"""
    try:
        # 全文始终原样保存。长文档分段理解后再合并，避免只读前段而遗漏作者设定。
        chunks = [text[i:i + 18000] for i in range(0, len(text), 18000)]
        partials = []
        unread_sections = []
        for index, chunk in enumerate(chunks, 1):
            try:
                partial = await get_llm_provider().generate_json(
                    system,
                    f"这是完整文档的第 {index}/{len(chunks)} 段。完整原文已单独原样保存，请只提取关键创作索引，不要逐条复制细则或复述原文：\n{chunk}",
                )
                if isinstance(partial.get("story_bible"), dict):
                    partials.append(partial)
                else:
                    unread_sections.append(index)
            except Exception:
                # 某段索引失败不能导致全文丢失或上传失败，用户仍可编辑完整原文。
                unread_sections.append(index)
        result = {"story_bible": {}, "suggestions": []}
        for partial in partials:
            for key, value in partial.get("story_bible", {}).items():
                target = result["story_bible"]
                if isinstance(value, list):
                    existing = target.setdefault(key, [])
                    seen = {json.dumps(v, ensure_ascii=False, sort_keys=True) for v in existing}
                    for entry in value:
                        marker = json.dumps(entry, ensure_ascii=False, sort_keys=True)
                        if marker not in seen:
                            existing.append(entry); seen.add(marker)
                elif value and key not in target:
                    target[key] = value
                elif value and isinstance(value, str) and value not in str(target.get(key, "")):
                    target[key] = str(target.get(key, "")) + "\n" + value
            result["suggestions"].extend(partial.get("suggestions", []))
        if not partials:
            result["story_bible"] = {"title": Path(filename).stem, "genre": "", "main_storyline": "", "character_profiles": [{"name": "", "role": "主角"}]}
        if unread_sections:
            result["suggestions"].append({"category": "文档整理", "issue": f"第 {unread_sections} 段 AI 索引未完成", "suggestion": "完整原文已保留，请直接在原文中核对；可稍后重新获取 AI 建议。"})
        result["original_text"] = text
        result["source_document"] = {"name": filename, "character_count": len(text), "sections_read": len(chunks)}
        result.setdefault("suggestions", [])
        return workflow_service.save_content(db, project_id, 1, result, note="上传设定文档（全文保留）", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 1, "FAILED")
        raise HTTPException(502, f"设定文档整理失败：{exc}")


async def generate_episode_plan(db: Session, project_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 2)
    analysis = workflow_service.content(workflow_service.get_state(db, project_id, 1))
    system = """你是中文短剧总策划。先从 Story Bible 提取贯穿全书的大事件与时间线，再据此规划 1-6 集漫剧，每集 60-180 秒。
大事件是改变故事阶段、人物目标或世界局势的关键节点，不是每集的小冲突。
只输出合法 JSON：{"major_events":[{"id":"event_1","time_order":1,"time_label":"故事开端/三个月后","title":"","description":"","cause":"","consequence":""}],"episodes":[{"episode_number":1,"title":"", "major_event_ids":["event_1"],"timeline_position":"","source_chapters":[],"main_plot":"","key_characters":[],"main_conflict":"","opening_hook":"","dramatic_highlights":[],"climax":"","cliffhanger":"","scene_requirements":[],"estimated_duration":90}]}
每集必须关联大事件并明确所处时间线。此时小说章节可能尚未导入，source_chapters 保留为空数组。"""
    prompt = "以下是用户已审批的创作资料，完整设定原文优先：\n" + json.dumps({"story_bible": analysis.get("story_bible"), "original_text": analysis.get("original_text", "")}, ensure_ascii=False)[:MAX_CONTEXT_CHARS] + "\n\n只输出 major_events 和 episodes，不要输出小事件流水账，不要虚构章节映射。"
    workflow_service.set_status(db, project_id, 2, "AI_GENERATING")
    try:
        result = await get_llm_provider().generate_json(system, prompt)
        episodes = result.get("episodes") or result.get("episode_plan")
        if not isinstance(episodes, list) or not episodes:
            raise ValueError("模型没有返回 episodes 剧集列表，请重试")
        major_events = result.get("major_events") or []
        if not isinstance(major_events, list) or not major_events:
            raise ValueError("模型没有返回 major_events 大事件时间线，请重试")
        for index, event in enumerate(major_events, 1):
            event["id"] = event.get("id") or f"event_{index}"
            event["time_order"] = index
        result = {"major_events": major_events, "episodes": episodes}
        sync_plan_episodes(db, project_id, result)
        return workflow_service.save_content(db, project_id, 2, result, note="AI 剧集规划", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 2, "FAILED")
        raise HTTPException(502, f"剧集规划失败：{exc}")


async def import_major_events_document(db: Session, project_id: str, filename: str, text: str) -> dict:
    """用用户文档补充或修改大事件时间线，并完整保留文档原文。"""
    workflow_service.require_unlocked(db, project_id, 2)
    if not text.strip():
        raise HTTPException(422, "文档中没有可读取的文字")
    state = workflow_service.get_state(db, project_id, 2)
    current = workflow_service.content(state)
    workflow_service.set_status(db, project_id, 2, "AI_GENERATING")
    system = """你是故事总策划。根据用户新文档，补充或明确修改已有大事件时间线。
只保留改变故事阶段、主角目标或世界局势的大事件，不拆成每集小事件。新文档的明确修改优先，未提及的旧事件不得无故删除。
只输出 JSON：{"major_events":[{"id":"event_1","time_order":1,"time_label":"","title":"","description":"","cause":"","consequence":""}]}"""
    try:
        result = await get_llm_provider().generate_json(system, json.dumps({
            "existing_events": current.get("major_events", []), "new_document": text,
        }, ensure_ascii=False)[:MAX_CONTEXT_CHARS])
        events = result.get("major_events")
        if not isinstance(events, list) or not events:
            raise ValueError("没有提取到大事件")
        for index, event in enumerate(events, 1):
            event["id"] = event.get("id") or f"event_{uuid.uuid4().hex[:10]}"
            event["time_order"] = index
        documents = current.get("event_source_documents", [])
        documents.append({"name": filename, "text": text})
        payload = {**current, "major_events": events, "event_source_documents": documents}
        return workflow_service.save_content(db, project_id, 2, payload, note="上传大事件文档", review_required=True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 2, "FAILED")
        raise HTTPException(502, f"大事件文档整理失败：{exc}")


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


def _split_source_text(text: str, limit: int = 15000) -> list[str]:
    """按段落完整切分长章节，不在句子中间截断原著。"""
    paragraphs = text.split("\n")
    chunks, current = [], ""
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            if current:
                chunks.append(current); current = ""
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        candidate = current + ("\n" if current else "") + paragraph
        if current and len(candidate) > limit:
            chunks.append(current); current = paragraph
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return chunks or [text]


async def _script_source(db: Session, project_id: str, plan: dict, novel: dict) -> tuple[list[dict], list[str]]:
    """优先使用用户章节映射；长小说未映射时先选章，再完整分段读取。"""
    chapters = novel.get("chapters", [])
    if not chapters:
        raise HTTPException(409, "请先在小说章节阶段导入原著")
    refs = [str(v).strip().lower() for v in plan.get("source_chapters", [])]
    selected = [c for c in chapters if any(
        ref in {str(c.get("id", "")).lower(), str(c.get("title", "")).lower()}
        or ref == str(c.get("title", "")).split()[0].lower()
        for ref in refs
    )]
    if not selected and len(chapters) > 1:
        catalogue = [{"id": c["id"], "title": c["title"], "excerpt": c.get("content", "")[:500]} for c in chapters]
        choice = await get_llm_provider().generate_json(
            "你是小说改编责任编辑。根据本集规划选择必须完整阅读的原著章节，只输出 JSON：{\"chapter_ids\":[\"chapter_001\"]}。不要选择无关章节。",
            json.dumps({"episode_plan": plan, "chapters": catalogue}, ensure_ascii=False)[:MAX_CONTEXT_CHARS],
        )
        ids = set(choice.get("chapter_ids", []))
        selected = [c for c in chapters if c.get("id") in ids]
    if not selected:
        selected = chapters
    parts = []
    for chapter in selected:
        for index, chunk in enumerate(_split_source_text(chapter.get("content", "")), 1):
            parts.append(f"【{chapter.get('title', '原著章节')} · 第 {index} 段】\n{chunk}")
    return selected, parts


async def generate_script(db: Session, project_id: str, episode_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 4)
    episode = episode_service.get_episode(db, episode_id)
    analysis = workflow_service.content(workflow_service.get_state(db, project_id, 1))
    plan = json.loads(episode.plan_json or "{}")
    novel = workflow_service.content(workflow_service.get_state(db, project_id, 3)).get("novel", {})
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    system = """你是专业中文小说改编编剧，不是图片提示词生成器。任务是把本集对应的小说内容尽可能完整地保留并转换成可表演、可审核的场景剧本。
只输出合法 JSON：{"title":"","summary":"","adaptation_notes":"保留了哪些情节、哪些内容因时长做了压缩","scenes":[{"scene_number":1,"duration_seconds":30,"location":"","time_environment":"","characters":[],"narrative":"本场完整叙事：起因、经过、人物行为、心理变化、信息揭示和结果","plot_beats":["按顺序发生的事件"],"character_change":"人物在本场前后的状态与情绪变化","scene_outcome":"本场结束时局面的变化及与下一场的衔接","action":"供后续分镜使用的可见环境、表情、动作和道具描述","dialogue":[{"character":"","line":"","emotion":""}],"internal_monologue":"","narration":"","transition":"","pacing":""}]}
narrative 是主体，必须具体讲完每个场景发生什么，不能只写画面气氛或视觉关键词；plot_beats 不遗漏原著中的关键事件、伏笔、信息揭示和反应。
保留原著事件顺序、因果、人物动机和重要细节。原著台词尽量逐字保留，必须压缩时在 adaptation_notes 说明，不得无说明地大段删除。
action 只补充可见执行细节，不替代 narrative。不要直接输出镜头、景别、运镜或英文生图提示词。
每句台词单独放入 dialogue，包含说话人、原文台词和情绪；为每场给出合理时长。"""
    header = json.dumps({
        "episode_plan": plan,
        "story_bible": analysis.get("story_bible"),
        "story_original_text": analysis.get("original_text", "")[:6000],
        "characters": [{"name": c.name, "personality": c.personality} for c in characters],
    }, ensure_ascii=False)
    workflow_service.set_status(db, project_id, 4, "AI_GENERATING", episode_id)
    try:
        selected_chapters, source_parts = await _script_source(db, project_id, plan, novel)
        scenes, notes = [], []
        title, summary = episode.title, episode.summary
        for index, source in enumerate(source_parts, 1):
            result = await get_llm_provider().generate_json(
                system,
                header + f"\n\n这是本集原著的第 {index}/{len(source_parts)} 段，请完整改编这一段，不要复述创作资料：\n{source}",
            )
            if not isinstance(result.get("scenes"), list) or not result["scenes"]:
                raise ValueError(f"第 {index} 段没有返回 scenes 场景列表，请重试")
            scenes.extend(result["scenes"])
            if result.get("adaptation_notes"):
                notes.append(result["adaptation_notes"])
            if index == 1:
                title = result.get("title") or title
                summary = result.get("summary") or summary
        for index, scene in enumerate(scenes, 1):
            scene["scene_number"] = index
            scene["narrative"] = str(scene.get("narrative") or scene.get("action") or "").strip()
            scene.setdefault("plot_beats", [])
            scene.setdefault("character_change", "")
            scene.setdefault("scene_outcome", "")
            try:
                duration = int(float(scene.get("duration_seconds", 0)))
            except (TypeError, ValueError):
                duration = 0
            if duration <= 0:
                dialogue_chars = sum(len(str(line.get("line", ""))) for line in scene.get("dialogue", []) if isinstance(line, dict))
                duration = max(8, round(dialogue_chars / 4 + len(scene["narrative"]) / 18))
            scene["duration_seconds"] = duration
        script = {
            "title": title, "summary": summary,
            "source_chapters": [{"id": c.get("id"), "title": c.get("title"), "content": c.get("content", "")} for c in selected_chapters],
            "adaptation_notes": "\n".join(notes), "scenes": scenes,
            "total_duration": sum(scene["duration_seconds"] for scene in scenes),
        }
        episode.title = title
        episode.summary = summary
        db.commit()
        return workflow_service.save_content(db, project_id, 4, script, episode_id, "AI 小说改编剧本（完整分段读取）", True)
    except Exception as exc:
        workflow_service.set_status(db, project_id, 4, "FAILED", episode_id)
        raise HTTPException(502, f"剧本生成失败：{exc}")


async def review_content(db: Session, project_id: str, stage: int, episode_id: str | None = None) -> dict:
    state = workflow_service.get_state(db, project_id, stage, episode_id)
    labels = {4: "剧本", 6: "分镜"}
    if stage not in labels:
        raise HTTPException(400, "该阶段使用结构化质量检查")
    focus = "对照 source_chapters 中的原著逐场检查情节、伏笔、动机、重要信息和台词是否遗漏，人物变化与场景结果是否完整；不要把画面美观当作剧本主体" if stage == 4 else "检查镜头是否完整继承已审批剧本的事件、动作与对白，以及构图、景别和视觉连续性"
    system = f"""你是{labels[stage]}质量审阅 Agent。{focus}。
只输出 JSON：{{"score":0,"summary":"","issues":[{{"severity":"high/medium/low","location":"","issue":"","suggestion":""}}]}}。不要直接修改内容。"""
    result = await get_llm_provider().generate_json(system, json.dumps(workflow_service.content(state), ensure_ascii=False)[:MAX_CONTEXT_CHARS])
    data = workflow_service.content(state)
    data["quality_review"] = result
    return workflow_service.save_content(db, project_id, stage, data, episode_id, "AI 质量审阅", True)


async def generate_storyboard(db: Session, project_id: str, episode_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 6)
    script_state = workflow_service.get_state(db, project_id, 4, episode_id)
    if script_state.status != "APPROVED":
        raise HTTPException(409, "请先审批当前剧集剧本")
    episode = episode_service.get_episode(db, episode_id)
    system = """你是专业漫剧分镜导演。把已审批剧本转成 8-20 个可生图镜头。
只输出 JSON：{"shots":[{"id":1,"duration":6,"scene":"","camera":"wide shot/medium shot/close-up/low angle/high angle","characters":[],"action":"","dialogue":"","visual_prompt":"详细英文画面提示词","camera_movement":"","expression":"","narration":"","lighting":"","composition":""}]}
保留全部关键动作和对白，视觉提示词忠于剧本，不新编人物外观。"""
    workflow_service.set_status(db, project_id, 6, "AI_GENERATING", episode_id)
    script_data = workflow_service.content(script_state)
    script_lines = [f"标题：{script_data.get('title', episode.title)}", f"梗概：{script_data.get('summary', '')}"]
    for scene in script_data.get("scenes", []):
        script_lines.append(f"场景 {scene.get('scene_number', '')}，{scene.get('location', '')}，{scene.get('time_environment', '')}")
        script_lines.append(f"角色：{'、'.join(scene.get('characters', [])) if isinstance(scene.get('characters'), list) else scene.get('characters', '')}")
        script_lines.append(f"本场完整叙事：{scene.get('narrative', '')}")
        script_lines.append(f"事件顺序：{json.dumps(scene.get('plot_beats', []), ensure_ascii=False)}")
        script_lines.append(f"人物变化：{scene.get('character_change', '')}")
        script_lines.append(f"场景结果：{scene.get('scene_outcome', '')}")
        script_lines.append(f"可见动作与环境：{scene.get('action', '')}")
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
        return workflow_service.save_content(db, project_id, 6, result, episode_id, "AI 分镜", True)
    except Exception as exc:
        db.rollback()
        workflow_service.set_status(db, project_id, 6, "FAILED", episode_id)
        raise HTTPException(502, f"分镜生成失败：{exc}")


async def extract_assets_from_scripts(db: Session, project_id: str) -> dict:
    """从所有已审批单集剧本提取资产；已有档案保留用户编辑，不覆盖。"""
    workflow_service.require_unlocked(db, project_id, 5)
    states = db.query(ProductionState).filter(
        ProductionState.project_id == project_id,
        ProductionState.stage == 4,
        ProductionState.episode_id.is_not(None),
        ProductionState.status == "APPROVED",
    ).all()
    scripts = [workflow_service.content(state) for state in states]
    if not scripts:
        raise HTTPException(409, "请先在剧本制作阶段审批至少一集剧本")
    system = """你是漫剧资产总监。只提取必须建立独立参考图、需要跨镜头或跨剧集保持视觉一致性的资产。
重要度规则：主要角色、反复出现且有辨识特征的角色必须提取；反复出现的核心地点、世界观标志性地点必须提取；推动剧情、反复使用或有独特外观的关键道具必须提取。
一次性街道、普通房间、路人、泛化人群、桌椅草木等临时背景或普通陈设不要建立资产，放入 deferred_backgrounds，之后在分镜画面 Prompt 中直接描述，避免浪费生成资源。即使剧本提到了，也不要为了凑数创建。
只输出 JSON：{"characters":[{"name":"","aliases":[],"age_description":"","appearance":"","hairstyle":"","clothing":"","personality":"","visual_prompt":"详细英文角色外观提示词"}],"scenes":[{"name":"","aliases":[],"location_type":"室内/室外","environment":"","architecture":"","lighting":"","atmosphere":"","visual_prompt":"详细英文场景提示词"}],"props":[{"name":"","description":"外观、材质、尺寸、细节","narrative_significance":"","visual_prompt":"详细英文道具提示词"}],"deferred_backgrounds":[{"name":"","reason":"只出现一次/普通环境，无需统一参考图"}]}
忠实于剧本，合并同一资产的不同出场。角色和场景不要混入道具列表，deferred_backgrounds 不要写入正式资产。"""
    result = await get_llm_provider().generate_json(system, json.dumps(scripts, ensure_ascii=False)[:MAX_CONTEXT_CHARS])
    created = {"characters": 0, "scenes": 0, "props": 0}
    existing_characters = {c.name.strip().lower(): c for c in db.query(Character).filter(Character.project_id == project_id).all()}
    for item in result.get("characters", []):
        name = str(item.get("name", "")).strip()
        if name and name.lower() not in existing_characters:
            entity = Character(project_id=project_id, name=name, aliases=json.dumps(item.get("aliases", []), ensure_ascii=False), age_description=item.get("age_description"), appearance=item.get("appearance"), hairstyle=item.get("hairstyle"), clothing=item.get("clothing"), personality=item.get("personality"), visual_prompt=item.get("visual_prompt"))
            db.add(entity); existing_characters[name.lower()] = entity; created["characters"] += 1
    existing_scenes = {s.name.strip().lower(): s for s in db.query(Scene).filter(Scene.project_id == project_id).all()}
    for item in result.get("scenes", []):
        name = str(item.get("name", "")).strip()
        if name and name.lower() not in existing_scenes:
            entity = Scene(project_id=project_id, name=name, aliases=json.dumps(item.get("aliases", []), ensure_ascii=False), location_type=item.get("location_type"), environment=item.get("environment"), architecture=item.get("architecture"), lighting=item.get("lighting"), atmosphere=item.get("atmosphere"), visual_prompt=item.get("visual_prompt"))
            db.add(entity); existing_scenes[name.lower()] = entity; created["scenes"] += 1
    existing_props = {p.name.strip().lower(): p for p in db.query(Prop).filter(Prop.project_id == project_id).all()}
    for item in result.get("props", []):
        name = str(item.get("name", "")).strip()
        if name and name.lower() not in existing_props:
            entity = Prop(project_id=project_id, name=name, description=item.get("description"), narrative_significance=item.get("narrative_significance"), visual_prompt=item.get("visual_prompt"))
            db.add(entity); existing_props[name.lower()] = entity; created["props"] += 1
    db.commit()
    state = workflow_service.get_state(db, project_id, 5)
    deferred = [
        {"name": str(item.get("name", "")).strip(), "reason": str(item.get("reason", "")).strip()}
        for item in result.get("deferred_backgrounds", [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    payload = {**workflow_service.content(state), "last_extraction": {
        "episodes": len(scripts), "created": created, "deferred_backgrounds": deferred,
        "note": "仅建立需要跨镜头统一的关键资产；临时背景留给分镜生成，已有资产未覆盖",
    }}
    return workflow_service.save_content(db, project_id, 5, payload, note="从已审批剧本提取资产", review_required=True)


def generate_missing_asset_images(db: Session, project_id: str) -> dict:
    workflow_service.require_unlocked(db, project_id, 5)
    from app.services import image_generation_service
    targets = [("character", c) for c in db.query(Character).filter(Character.project_id == project_id, Character.reference_asset_id.is_(None)).all()]
    targets += [("scene", s) for s in db.query(Scene).filter(Scene.project_id == project_id, Scene.reference_asset_id.is_(None)).all()]
    targets += [("prop", p) for p in db.query(Prop).filter(Prop.project_id == project_id, Prop.reference_asset_id.is_(None)).all()]
    jobs = []
    for kind, entity in targets:
        try:
            jobs.append(image_generation_service.create_job_for_entity(db, kind, entity.id))
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    return {"created": len(jobs), "jobs": jobs, "message": f"已把 {len(jobs)} 个缺失参考图加入生成队列" if jobs else "所有资产已有参考图或正在生成"}


def asset_quality(db: Session, project_id: str) -> dict:
    issues = []
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    scenes = db.query(Scene).filter(Scene.project_id == project_id).all()
    props = db.query(Prop).filter(Prop.project_id == project_id).all()
    for entity, kind in [(c, "角色") for c in characters] + [(s, "场景") for s in scenes] + [(p, "道具") for p in props]:
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
        bible = data.get("story_bible") or {}
        if not all(str(bible.get(key, "")).strip() for key in ("title", "genre", "main_storyline")):
            raise HTTPException(409, "请填写故事名称、题材类型和故事大致走向")
    elif stage == 2:
        plan = workflow_service.content(workflow_service.get_state(db, project_id, 2))
        if not plan.get("major_events"):
            raise HTTPException(409, "请先提取并确认故事大事件时间线")
        if not plan.get("episodes"):
            raise HTTPException(409, "剧集规划不能为空")
        sync_plan_episodes(db, project_id, plan)
    elif stage == 3:
        data = workflow_service.content(workflow_service.get_state(db, project_id, 3))
        chapters = data.get("novel", {}).get("chapters", [])
        if not chapters or any(not str(c.get("title", "")).strip() or not str(c.get("content", "")).strip() for c in chapters):
            raise HTTPException(409, "请至少保留一个标题和正文均非空的章节")
    elif stage == 4:
        state = workflow_service.get_state(db, project_id, 4, episode_id)
        script = workflow_service.content(state)
        if not script.get("scenes"):
            raise HTTPException(409, "剧本至少需要一个场景")
        if any(not str(scene.get("narrative") or scene.get("action") or "").strip() for scene in script["scenes"]):
            raise HTTPException(409, "每个场景都需要写清楚完整叙事，不能只保留画面关键词")
        if any(int(scene.get("duration_seconds", 0) or 0) <= 0 for scene in script["scenes"]):
            raise HTTPException(409, "每个场景都需要填写有效时长")
    elif stage == 5:
        quality = asset_quality(db, project_id)
        if any(i["severity"] == "high" for i in quality["issues"]):
            raise HTTPException(409, "仍有角色或场景缺少参考图")
        state = workflow_service.get_state(db, project_id, 5)
        existing = workflow_service.content(state)
        state.content_json = json.dumps({**existing, "quality": quality}, ensure_ascii=False)
        db.commit()
    elif stage == 6:
        if not db.query(Shot).filter(Shot.episode_id == episode_id).count():
            raise HTTPException(409, "请先生成分镜")
    elif stage == 7:
        shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
        missing = []
        for shot in shots:
            selected = db.query(ShotImage).filter(ShotImage.shot_id == shot.id, ShotImage.is_selected.is_(True)).first()
            if not selected or shot.production_outdated:
                missing.append(shot.shot_index)
        if not shots or missing:
            raise HTTPException(409, f"镜头 {missing} 尚未选择有效定稿图")
    elif stage == 8:
        package_validation(db, episode_id)


def package_validation(db: Session, episode_id: str) -> dict:
    episode = episode_service.get_episode(db, episode_id)
    project_id = episode.project_id
    states = db.query(ProductionState).filter(ProductionState.episode_id == episode_id).all()
    approved = {s.stage for s in states if s.status == "APPROVED"}
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
    missing_images = [s.shot_index for s in shots if not db.query(ShotImage).filter(ShotImage.shot_id == s.id, ShotImage.is_selected.is_(True)).first()]
    checks = {
        "script_approved": 4 in approved,
        "storyboard_approved": 6 in approved,
        "images_approved": 7 in approved,
        "all_shots_have_images": not missing_images,
        "character_assets_approved": workflow_service.get_state(db, project_id, 5).status == "APPROVED",
    }
    return {"ready": all(checks.values()), "checks": checks, "missing_images": missing_images}


def build_production_package(db: Session, episode_id: str) -> dict:
    validation = package_validation(db, episode_id)
    episode = episode_service.get_episode(db, episode_id)
    shots = db.query(Shot).filter(Shot.episode_id == episode_id).order_by(Shot.shot_index).all()
    script = workflow_service.content(workflow_service.get_state(db, episode.project_id, 4, episode_id))
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
        "props": [{"id": p.id, "name": p.name, "description": p.description, "visual_prompt": p.visual_prompt, "reference_asset_id": p.reference_asset_id} for p in db.query(Prop).filter(Prop.project_id == episode.project_id).all()], "shots": shot_rows,
        "asset_manifest": [{"asset_id": a.id, "type": a.asset_type, "path": a.file_path} for a in db.query(Asset).filter(Asset.project_id == episode.project_id).all()],
        "validation": validation,
    }
    directory = PROJECT_ROOT / "output" / "production_packages"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{episode_id}.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return package
