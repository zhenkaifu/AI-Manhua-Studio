"""把 generation-context 组合成最终的图片生成 Prompt。

结构：Global Style + Character + Scene + Shot + Camera，与 Stage 3 文档一致。
"""

GLOBAL_STYLE = (
    "Chinese 2.5D donghua style, cinematic fantasy animation, "
    "3D-rendered anime aesthetic, masterpiece, best quality, highly detailed"
)

NEGATIVE_BASE = (
    "lowres, bad anatomy, bad hands, bad eyes, deformed face, asymmetrical eyes, "
    "text, watermark, signature, worst quality, low quality, blurry, cropped"
)

CAMERA_EN = {
    "wide shot": "wide shot, cinematic composition",
    "medium shot": "medium shot",
    "close-up": "close-up shot, detailed face",
    "low angle": "low angle shot",
    "high angle": "high angle shot",
}


def build_prompt(context: dict) -> tuple[str, str]:
    """输入 entity_linker.generation_context 的输出，返回 (prompt, negative)。"""
    parts = [GLOBAL_STYLE]

    for c in context.get("characters", []):
        if c.get("visual_prompt"):
            parts.append(c["visual_prompt"])

    scene = context.get("scene")
    if scene:
        scene_text = scene.get("visual_prompt") or ", ".join(
            filter(None, [
                scene.get("environment"),
                scene.get("lighting"),
                scene.get("atmosphere"),
            ])
        )
        if scene_text:
            parts.append(scene_text)
    elif context.get("scene_text"):
        parts.append(context["scene_text"])

    # Shot-specific：优先用 Phase 1 生成的英文视觉描述，退回中文动作描述
    shot_desc = context.get("shot_visual_prompt") or context.get("description")
    if shot_desc:
        parts.append(shot_desc)

    camera = (context.get("camera") or "").strip().lower()
    if camera:
        parts.append(CAMERA_EN.get(camera, camera))

    prompt = ",\n".join(p for p in parts if p)

    negatives = [NEGATIVE_BASE]
    for c in context.get("characters", []):
        if c.get("negative_prompt"):
            negatives.append(c["negative_prompt"])

    return prompt, ", ".join(negatives)
