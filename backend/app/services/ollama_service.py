import httpx

from app.core.config import settings
from app.utils.json_parser import parse_ai_json


async def chat_json(system_prompt: str, user_prompt: str, timeout: float = 600.0) -> dict:
    """调用本地 Ollama，强制 JSON 输出并解析为 dict。"""
    payload = {
        "model": settings.model,
        "stream": False,
        "format": "json",
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(settings.ollama_url, json=payload)
        response.raise_for_status()
        data = response.json()
    return parse_ai_json(data["message"]["content"])
