"""把 generation-context 组合成最终的图片生成 Prompt。

结构：Global Style + Character + Scene + Shot + Camera，与 Stage 3 文档一致。
"""

VISUAL_STYLES = {
    "Chinese 2.5D Donghua": {
        "label": "2.5D 国漫",
        "prompt": "Chinese 2.5D donghua style, cinematic fantasy animation, refined 3D-rendered anime aesthetic, consistent character design, masterpiece, highly detailed",
        "negative": "flat 2D cartoon, western comic style, chibi",
    },
    "Chinese 2D Anime": {
        "label": "2D 国漫",
        "prompt": "Chinese 2D donghua, hand-drawn anime illustration, clean expressive line art, cel shading, consistent character design, cinematic composition, highly detailed",
        "negative": "3d render, 2.5d, photorealistic, western cartoon, chibi",
    },
    "Cinematic Fantasy Animation": {
        "label": "电影感幻想动画",
        "prompt": "cinematic fantasy animation, consistent production design, atmospheric depth, dramatic film lighting, detailed painterly animation still",
        "negative": "flat children's cartoon, chibi, live action photography",
    },
    "Modern Manhua Flat Color": {
        "label": "现代平涂漫画",
        "prompt": "modern Chinese manhua illustration, clean ink contours, flat colors, crisp cel shadows, graphic comic composition, consistent character design",
        "negative": "3d render, 2.5d, photorealistic, painterly oil texture",
    },
    "Chinese Ink Wash": {
        "label": "东方水墨",
        "prompt": "Chinese ink wash animation, elegant brushwork, mineral pigments, atmospheric rice paper texture, poetic negative space, consistent character design",
        "negative": "3d render, glossy plastic, western cartoon, neon colors",
    },
}

DEFAULT_STYLE = "Chinese 2.5D Donghua"
GLOBAL_STYLE = VISUAL_STYLES[DEFAULT_STYLE]["prompt"]


def style_settings(value: str | None) -> dict:
    return VISUAL_STYLES.get(value or DEFAULT_STYLE, VISUAL_STYLES[DEFAULT_STYLE])


def with_style(prompt: str, visual_style: str | None) -> str:
    style = style_settings(visual_style)["prompt"]
    return prompt if style in prompt else f"{style},\n{prompt}"

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


def build_prompt(context: dict, visual_style: str | None = None) -> tuple[str, str]:
    """输入 generation-context，使用当前项目风格构建 (prompt, negative)。"""
    style = style_settings(visual_style)
    parts = [style["prompt"]]

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

    negatives = [NEGATIVE_BASE, style["negative"]]
    for c in context.get("characters", []):
        if c.get("negative_prompt"):
            negatives.append(c["negative_prompt"])

    return prompt, ", ".join(negatives)
