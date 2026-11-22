import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import (
    Asset,
    Character,
    Episode,
    Scene,
    Shot,
    ShotEntityLink,
)
from app.services.ollama_service import chat_json

SEMANTIC_PROMPT = """你是国漫制作中的{kind}比对专家。给你小说分镜中提到的一个称呼/描述，和已有{kind}档案列表，判断它指的是列表中的哪一个。

判断依据：名字、别名、描述是否指向同一对象。名字不同但明显指同一对象（例如「林公子」和「林枫」）也算匹配。都不像就返回 null。

只输出合法JSON：{{"match_id": "列表中某个id 或 null", "confidence": 0.0到1.0}}"""


# ---------- 内部工具 ----------

def _char_rows(db: Session, project_id: str) -> list[dict]:
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


def _scene_rows(db: Session, project_id: str) -> list[dict]:
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


def _exact(mention: str, rows: list[dict]) -> tuple[dict | None, str]:
    """先按正式名精确匹配，再按别名精确匹配。"""
    m = mention.strip()
    for row in rows:
        if row["name"].strip() == m:
            return row, "exact"
    for row in rows:
        if m in {a.strip() for a in row["aliases"]}:
            return row, "alias"
    return None, ""


async def _semantic(kind: str, mention: str, context: str, rows: list[dict]):
    """语义匹配，返回 (row, confidence)。失败或无匹配返回 (None, None)。"""
    if not rows:
        return None, None
    try:
        result = await chat_json(
            SEMANTIC_PROMPT.format(kind=kind),
            (
                f"分镜原文：{context}\n\n"
                f"待判断的称呼/描述：{mention}\n\n"
                f"已有{kind}档案：{json.dumps(rows, ensure_ascii=False)}"
            ),
            timeout=180.0,
        )
        match_id = result.get("match_id")
        confidence = result.get("confidence")
        for row in rows:
            if row["id"] == match_id:
                return row, confidence
    except Exception:
        pass
    return None, None


def _add_link(db: Session, shot_id: str, entity_type: str, entity_id,
              mention: str, method: str, confidence, status: str):
    db.add(
        ShotEntityLink(
            shot_id=shot_id,
            entity_type=entity_type,
            entity_id=entity_id,
            mention_text=mention[:255],
            match_method=method,
            confidence=confidence,
            status=status,
        )
    )


# ---------- 自动关联 ----------

async def link_episode(db: Session, episode_id: str) -> dict:
    """自动关联一集所有分镜。manual 关联会被保留，重复运行安全。"""
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="剧集不存在")

    shots = db.query(Shot).filter(Shot.episode_id == episode_id).all()
    shot_ids = [s.id for s in shots]

    # 清除旧的自动关联，保留人工修正
    db.query(ShotEntityLink).filter(
        ShotEntityLink.shot_id.in_(shot_ids),
        ShotEntityLink.match_method != "manual",
    ).delete(synchronize_session=False)

    chars = _char_rows(db, episode.project_id)
    scenes = _scene_rows(db, episode.project_id)
    stats = {"linked": 0, "pending": 0, "unresolved": 0}

    for shot in shots:
        context = f"{shot.scene or ''} {shot.action or ''}".strip()

        # ---- 角色 ----
        for mention in json.loads(shot.characters_json or "[]"):
            row, method = _exact(mention, chars)
            if row:
                _add_link(db, shot.id, "character", row["id"], mention,
                          method, 1.0 if method == "exact" else 0.95, "linked")
                stats["linked"] += 1
                continue
            row, conf = await _semantic("角色", mention, context, chars)
            if row:
                _add_link(db, shot.id, "character", row["id"], mention,
                          "semantic", conf, "pending")
                stats["pending"] += 1
            else:
                _add_link(db, shot.id, "character", None, mention,
                          "none", None, "unresolved")
                stats["unresolved"] += 1

        # ---- 场景：先看已知场景名/别名是否出现在分镜场景描述中 ----
        scene_text = shot.scene or ""
        matched_scene, scene_method, scene_conf, scene_status = None, "", None, ""
        if scene_text:
            for row in scenes:
                names = [row["name"], *row["aliases"]]
                for n in names:
                    if n and n.strip() and n.strip() in scene_text:
                        matched_scene = row
                        scene_method = "exact" if n == row["name"] else "alias"
                        break
                if matched_scene:
                    break
            if matched_scene:
                scene_conf = 1.0 if scene_method == "exact" else 0.95
                scene_status = "linked"
            else:
                matched_scene, scene_conf = await _semantic(
                    "场景", scene_text, context, scenes
                )
                if matched_scene:
                    scene_method = "semantic"
                    scene_status = "pending"
                else:
                    scene_method = "none"
                    scene_status = "unresolved"

            _add_link(
                db, shot.id, "scene",
                matched_scene["id"] if matched_scene else None,
                scene_text[:80], scene_method, scene_conf, scene_status,
            )
            stats[scene_status] += 1

    db.commit()
    return {"episode_id": episode_id, "shots": len(shots), **stats}


# ---------- 查询 ----------

def _link_out(db: Session, link: ShotEntityLink) -> dict:
    entity_name, ref = None, None
    if link.entity_id:
        if link.entity_type == "character":
            obj = db.get(Character, link.entity_id)
        else:
            obj = db.get(Scene, link.entity_id)
        if obj:
            entity_name = obj.name
            ref = obj.reference_asset_id
    return {
        "id": link.id,
        "shot_id": link.shot_id,
        "entity_type": link.entity_type,
        "entity_id": link.entity_id,
        "entity_name": entity_name,
        "reference_asset_id": ref,
        "mention_text": link.mention_text,
        "match_method": link.match_method,
        "confidence": link.confidence,
        "status": link.status,
    }


def list_shot_links(db: Session, shot_id: str) -> list[dict]:
    rows = (
        db.query(ShotEntityLink)
        .filter(ShotEntityLink.shot_id == shot_id)
        .order_by(ShotEntityLink.created_at)
        .all()
    )
    return [_link_out(db, r) for r in rows]


def list_episode_links(db: Session, episode_id: str) -> dict:
    shots = (
        db.query(Shot)
        .filter(Shot.episode_id == episode_id)
        .order_by(Shot.shot_index)
        .all()
    )
    result = []
    for s in shots:
        links = list_shot_links(db, s.id)
        result.append(
            {
                "shot_id": s.id,
                "shot_index": s.shot_index,
                "duration": s.duration,
                "scene": s.scene,
                "action": s.action,
                "camera": s.camera,
                "links": links,
            }
        )
    return {"episode_id": episode_id, "shots": result}


# ---------- 人工修正 ----------

def set_shot_links(db: Session, shot_id: str, links: list[dict]) -> list[dict]:
    """整体替换一个分镜的关联（人工操作，match_method 记为 manual）。"""
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")

    db.query(ShotEntityLink).filter(ShotEntityLink.shot_id == shot_id).delete()
    for item in links:
        entity_id = item.get("entity_id")
        status = item.get("status") or ("linked" if entity_id else "unresolved")
        if entity_id:
            _validate_entity(db, shot, item.get("entity_type"), entity_id)
        _add_link(
            db, shot_id,
            item.get("entity_type", "character"),
            entity_id,
            item.get("mention_text", ""),
            "manual", None, status,
        )
    db.commit()
    return list_shot_links(db, shot_id)


def _validate_entity(db: Session, shot: Shot, entity_type: str, entity_id: str):
    episode = db.get(Episode, shot.episode_id)
    model = Character if entity_type == "character" else Scene
    obj = db.get(model, entity_id)
    if not obj or obj.project_id != episode.project_id:
        raise HTTPException(status_code=400, detail="关联目标不存在或不属于本项目")


def resolve_entity(db: Session, shot_id: str, req) -> list[dict]:
    """处理未识别提及：关联已有 / 新建草稿 / 忽略。"""
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    episode = db.get(Episode, shot.episode_id)

    links = (
        db.query(ShotEntityLink)
        .filter(
            ShotEntityLink.shot_id == shot_id,
            ShotEntityLink.mention_text == req.mention_text,
            ShotEntityLink.entity_type == req.entity_type,
            ShotEntityLink.status == "unresolved",
        )
        .all()
    )
    if not links:
        raise HTTPException(status_code=404, detail="没有找到该未识别提及")

    if req.action == "ignore":
        for link in links:
            link.status = "ignored"
    elif req.action == "link":
        if not req.entity_id:
            raise HTTPException(status_code=400, detail="link 操作需要 entity_id")
        _validate_entity(db, shot, req.entity_type, req.entity_id)
        for link in links:
            link.entity_id = req.entity_id
            link.match_method = "manual"
            link.status = "linked"
    elif req.action == "create":
        # 走草稿状态新建，不直接创建 approved 档案
        if req.entity_type == "character":
            obj = Character(project_id=episode.project_id,
                            name=req.name or req.mention_text, status="draft")
        else:
            obj = Scene(project_id=episode.project_id,
                        name=req.name or req.mention_text, status="draft")
        db.add(obj)
        db.flush()
        for link in links:
            link.entity_id = obj.id
            link.match_method = "manual"
            link.status = "linked"
    else:
        raise HTTPException(status_code=400, detail="action 必须是 link / create / ignore")

    db.commit()
    return list_shot_links(db, shot_id)


# ---------- Phase 3 数据管道 ----------

def generation_context(db: Session, shot_id: str) -> dict:
    """组装 Phase 3 图片生成所需的完整数据。只读，不生成图片。"""
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")

    links = (
        db.query(ShotEntityLink)
        .filter(
            ShotEntityLink.shot_id == shot_id,
            ShotEntityLink.status == "linked",
        )
        .all()
    )

    characters, scene_data = [], None
    for link in links:
        if link.entity_type == "character" and link.entity_id:
            c = db.get(Character, link.entity_id)
            if c:
                characters.append(
                    {
                        "id": c.id,
                        "name": c.name,
                        "mention": link.mention_text,
                        "visual_prompt": c.visual_prompt,
                        "negative_prompt": c.negative_prompt,
                        "reference_asset_id": c.reference_asset_id,
                        "reference_image": _asset_path(db, c.reference_asset_id),
                    }
                )
        elif link.entity_type == "scene" and link.entity_id:
            s = db.get(Scene, link.entity_id)
            if s:
                scene_data = {
                    "id": s.id,
                    "name": s.name,
                    "visual_prompt": s.visual_prompt,
                    "environment": s.environment,
                    "lighting": s.lighting,
                    "atmosphere": s.atmosphere,
                    "reference_asset_id": s.reference_asset_id,
                    "reference_image": _asset_path(db, s.reference_asset_id),
                }

    unresolved = [
        l.mention_text
        for l in db.query(ShotEntityLink)
        .filter(
            ShotEntityLink.shot_id == shot_id,
            ShotEntityLink.status == "unresolved",
        )
        .all()
    ]

    return {
        "shot_id": shot.id,
        "shot_index": shot.shot_index,
        "duration": shot.duration,
        "description": shot.action,
        "scene_text": shot.scene,
        "camera": shot.camera,
        "dialogue": shot.dialogue,
        "emotion": None,  # 预留：Phase 3 由剧本分析补充
        "shot_visual_prompt": shot.visual_prompt,
        "characters": characters,
        "scene": scene_data,
        "unresolved_mentions": unresolved,
    }


def _asset_path(db: Session, asset_id: str | None) -> str | None:
    if not asset_id:
        return None
    asset = db.get(Asset, asset_id)
    return asset.file_path if asset else None
