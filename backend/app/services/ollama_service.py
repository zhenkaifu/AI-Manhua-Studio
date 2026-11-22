import httpx
import os

from app.core.config import settings
from app.utils.json_parser import parse_ai_json


async def deepseek_chat_json(system_prompt: str, user_prompt: str, timeout: float = 600.0) -> dict:
    """调用 DeepSeek OpenAI-compatible API，并解析结构化 JSON。"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or settings.deepseek_api_key
    if not api_key:
        raise RuntimeError(
            "未配置 DeepSeek API Key，请设置 DEEPSEEK_API_KEY 或 MANHUA_DEEPSEEK_API_KEY"
        )

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    return parse_ai_json(content)


async def chat_json(system_prompt: str, user_prompt: str, timeout: float = 600.0) -> dict:
    """根据配置调用 DeepSeek 或 Ollama，统一返回 JSON dict。"""
    if settings.llm_provider.lower() == "deepseek":
        return await deepseek_chat_json(system_prompt, user_prompt, timeout)

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
