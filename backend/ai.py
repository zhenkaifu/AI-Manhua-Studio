import json
from pathlib import Path

import httpx

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"

PROMPT_PATH = Path(__file__).parent / "prompts" / "script.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


async def generate_episode(novel: str) -> dict:
    """调用本地 Ollama 模型，把小说改编成一集漫剧剧本（JSON dict）。"""
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "think": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请将以下小说改编成一集国漫短剧剧本，"
                    "严格按系统要求的 JSON 结构输出。\n\n小说原文：\n" + novel
                ),
            },
        ],
    }

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["message"]["content"]
    return json.loads(content)
