import json
from pathlib import Path

from app.providers.llm_provider import get_llm_provider

PROMPT_PATH = Path(__file__).parent / "prompts" / "script.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


async def generate_episode(novel: str) -> dict:
    """调用配置的 LLM，把小说改编成一集漫剧剧本（JSON dict）。"""
    user_prompt = (
        "请将以下小说改编成一集国漫短剧剧本，"
        "严格按系统要求的 JSON 结构输出。\n\n小说原文：\n" + novel
    )
    return await get_llm_provider().generate_json(SYSTEM_PROMPT, user_prompt)
