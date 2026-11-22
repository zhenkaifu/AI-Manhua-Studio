"""统一 LLM Provider 入口。生产业务只依赖此接口，不直接调用 Ollama API。"""
from abc import ABC, abstractmethod

from app.services.ollama_service import chat_json


class LLMProvider(ABC):
    @abstractmethod
    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        pass


class OllamaProvider(LLMProvider):
    name = "ollama"

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return await chat_json(system_prompt, user_prompt)


_provider = OllamaProvider()


def get_llm_provider() -> LLMProvider:
    return _provider
