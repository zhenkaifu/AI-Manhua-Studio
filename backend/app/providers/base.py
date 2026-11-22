from abc import ABC, abstractmethod
from pathlib import Path


class ImageProvider(ABC):
    """图片生成 Provider 接口。未来换成云端模型时前端和后端都不用改。"""

    name: str

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        seed: int,
        width: int,
        height: int,
        steps: int,
        upscale: int = 1,
        reference_path: Path | None = None,
        reference_paths: list | None = None,
        progress_callback=None,
    ) -> bytes:
        """生成一张图片，返回 PNG 字节。reference_paths 为参考图列表（可选，最多 3 张）。"""
