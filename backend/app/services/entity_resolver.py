import json

from sqlalchemy.orm import Session

from app.database.models import Character, Scene
from app.services.ollama_service import chat_json

SEMANTIC_PROMPT = """你是国漫制作中的角色/场景比对专家。给你一个新提取的{kind}信息和已有{kind}列表，判断新{kind}是否就是列表中的某一个。

判断依据：名字、别名、外貌/环境描述是否指向同一个对象。名字不同但描述高度一致（例如「林公子」和「林枫」）也算同一个。

只输出合法JSON：{{"match_id": "列表中某个id 或 null", "reason": "一句话原因"}}"""


def _names(text: str) -> set[str]:
    return {t.strip() for t in text.split("|") if t.strip()}


def _exact_match(name: str, aliases: list[str], existing: list[dict]) -> dict | None:
    """Level 1：名字或别名完全一致。"""
    candidates = {name.strip(), *(a.strip() for a in aliases)}
    for row in existing:
        known = {row["name"].strip(), *(a.strip() for a in row["aliases"])}
        if candidates & known:
            return row
    return None


async def _semantic_match(kind: str, item: dict, existing: list[dict]) -> dict | None:
    """Level 2：让配置的 LLM 做语义判断。失败时返回 None（视为新实体）。"""
    if not existing:
        return None
    try:
        result = await chat_json(
            SEMANTIC_PROMPT.format(kind=kind),
            (
                f"新{kind}：{json.dumps(item, ensure_ascii=False)}\n\n"
                f"已有{kind}列表：{json.dumps(existing, ensure_ascii=False)}"
            ),
            timeout=180.0,
        )
        match_id = result.get("match_id")
        for row in existing:
            if row["id"] == match_id:
                return row
    except Exception:
        pass
    return None


def _existing_characters(db: Session, project_id: str) -> list[dict]:
    rows = db.query(Character).filter(Character.project_id == project_id).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "aliases": json.loads(c.aliases or "[]"),
            "appearance": c.appearance or "",
        }
        for c in rows
    ]


def _existing_scenes(db: Session, project_id: str) -> list[dict]:
    rows = db.query(Scene).filter(Scene.project_id == project_id).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "aliases": json.loads(s.aliases or "[]"),
            "environment": s.environment or "",
        }
        for s in rows
    ]


async def resolve_draft(db: Session, project_id: str, draft: dict) -> dict:
    """三级匹配：精确匹配自动关联；语义匹配标记待确认；否则视为新实体。"""
    existing_chars = _existing_characters(db, project_id)
    existing_scenes = _existing_scenes(db, project_id)

    for c in draft.get("characters", []):
        hit = _exact_match(c.get("name", ""), c.get("aliases", []), existing_chars)
        level = "exact"
        if not hit:
            hit = await _semantic_match("角色", c, existing_chars)
            level = "semantic"
        if hit:
            c["match_level"] = level
            c["target_id"] = hit["id"]
            c["target_name"] = hit["name"]
            c["decision"] = "merge" if level == "exact" else "create"
        else:
            c["match_level"] = "new"
            c["target_id"] = None
            c["target_name"] = None
            c["decision"] = "create"

    for s in draft.get("scenes", []):
        hit = _exact_match(s.get("name", ""), s.get("aliases", []), existing_scenes)
        level = "exact"
        if not hit:
            hit = await _semantic_match("场景", s, existing_scenes)
            level = "semantic"
        if hit:
            s["match_level"] = level
            s["target_id"] = hit["id"]
            s["target_name"] = hit["name"]
            s["decision"] = "merge" if level == "exact" else "create"
        else:
            s["match_level"] = "new"
            s["target_id"] = None
            s["target_name"] = None
            s["decision"] = "create"

    return draft


def confirm_draft(db: Session, project_id: str, draft: dict) -> dict:
    """把审核后的草稿写入正式表。decision: create / merge / skip。"""
    result = {
        "created_characters": [],
        "merged_characters": [],
        "created_scenes": [],
        "merged_scenes": [],
    }

    for c in draft.get("characters", []):
        decision = c.get("decision", "create")
        if decision == "skip":
            continue
        if decision == "merge" and c.get("target_id"):
            target = db.get(Character, c["target_id"])
            if target:
                aliases = set(json.loads(target.aliases or "[]"))
                aliases.add(c["name"])
                aliases.update(c.get("aliases", []))
                aliases.discard(target.name)
                target.aliases = json.dumps(sorted(aliases), ensure_ascii=False)
                result["merged_characters"].append(target.id)
            continue
        new_c = Character(
            project_id=project_id,
            name=c.get("name", "未命名角色"),
            aliases=json.dumps(c.get("aliases", []), ensure_ascii=False),
            age_description=c.get("age_description") or None,
            appearance=c.get("appearance") or None,
            hairstyle=c.get("hairstyle") or None,
            clothing=c.get("clothing") or None,
            personality=c.get("personality") or None,
            visual_prompt=c.get("visual_prompt") or None,
            status="approved",
        )
        db.add(new_c)
        db.flush()
        result["created_characters"].append(new_c.id)

    for s in draft.get("scenes", []):
        decision = s.get("decision", "create")
        if decision == "skip":
            continue
        if decision == "merge" and s.get("target_id"):
            target = db.get(Scene, s["target_id"])
            if target:
                aliases = set(json.loads(target.aliases or "[]"))
                aliases.add(s["name"])
                aliases.update(s.get("aliases", []))
                aliases.discard(target.name)
                target.aliases = json.dumps(sorted(aliases), ensure_ascii=False)
                result["merged_scenes"].append(target.id)
            continue
        new_s = Scene(
            project_id=project_id,
            name=s.get("name", "未命名场景"),
            aliases=json.dumps(s.get("aliases", []), ensure_ascii=False),
            location_type=s.get("location_type") or None,
            environment=s.get("environment") or None,
            architecture=s.get("architecture") or None,
            lighting=s.get("lighting") or None,
            atmosphere=s.get("atmosphere") or None,
            visual_prompt=s.get("visual_prompt") or None,
            status="approved",
        )
        db.add(new_s)
        db.flush()
        result["created_scenes"].append(new_s.id)

    db.commit()
    return result
