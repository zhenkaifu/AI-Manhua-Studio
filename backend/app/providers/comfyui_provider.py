import asyncio
import contextlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
import websockets

from app.core.paths import PROJECT_ROOT
from app.providers.base import ImageProvider

COMFYUI_DIR = PROJECT_ROOT / "ComfyUI"
BASE_URL = "http://127.0.0.1:8188"

UNET_MODEL = "z_image_turbo_bf16.safetensors"
CLIP_MODEL = "qwen_3_4b_fp8_mixed.safetensors"
VAE_MODEL = "z_image_ae.safetensors"
UPSCALE_MODEL = "RealESRGAN_x4plus_anime_6B.pth"

MAX_WAIT_SECONDS = 30 * 60


class ComfyUIProvider(ImageProvider):
    """本地 ComfyUI + Z-Image-Turbo int8。服务没启动时自动拉起。"""

    name = "comfyui"

    def __init__(self):
        self._process: subprocess.Popen | None = None

    async def _reachable(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(BASE_URL + "/", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def ensure_running(self, client: httpx.AsyncClient):
        if await self._reachable(client):
            return
        if self._process is None or self._process.poll() is not None:
            self._process = subprocess.Popen(
                [str(COMFYUI_DIR / ".venv/bin/python"), "main.py"],
                cwd=COMFYUI_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        for _ in range(60):
            if await self._reachable(client):
                return
            await asyncio.sleep(2)
        raise RuntimeError("ComfyUI 启动超时（120 秒）")

    def _build_workflow(
        self, prompt: str, negative: str, seed: int,
        width: int, height: int, steps: int, upscale: int = 1,
        reference_filenames: list[str] | None = None,
    ) -> dict:
        workflow = {
            "1": {"class_type": "UNETLoader",
                  "inputs": {"unet_name": UNET_MODEL, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader",
                  "inputs": {"clip_name": CLIP_MODEL, "type": "lumina2",
                             "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_MODEL}},
            "4": {"class_type": "ModelSamplingAuraFlow",
                  "inputs": {"shift": 3.0, "model": ["1", 0]}},
            "6": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": negative, "clip": ["2", 0]}},
            "7": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": width, "height": height, "batch_size": 1}},
        }
        if reference_filenames:
            # Sprint 5/6：Z-Image 原生 Omni 参考图节点（最多 3 张），锁定角色/场景一致性
            omni_inputs = {"clip": ["2", 0], "vae": ["3", 0], "prompt": prompt,
                           "auto_resize_images": True}
            for i, fname in enumerate(reference_filenames[:3]):
                load_id = str(14 + i)
                workflow[load_id] = {"class_type": "LoadImage",
                                     "inputs": {"image": fname}}
                omni_inputs[f"image{i + 1}"] = [load_id, 0]
            workflow["5"] = {"class_type": "TextEncodeZImageOmni",
                             "inputs": omni_inputs}
        else:
            workflow["5"] = {"class_type": "CLIPTextEncode",
                             "inputs": {"text": prompt, "clip": ["2", 0]}}
        workflow["8"] = {"class_type": "KSampler",
                         "inputs": {"seed": seed, "steps": steps, "cfg": 1.0,
                                    "sampler_name": "euler", "scheduler": "simple",
                                    "denoise": 1.0, "model": ["4", 0],
                                    "positive": ["5", 0], "negative": ["6", 0],
                                    "latent_image": ["7", 0]}}
        workflow["9"] = {"class_type": "VAEDecode",
                         "inputs": {"samples": ["8", 0], "vae": ["3", 0]}}
        if upscale > 1:
            # 先 4x AI 放大再缩到目标尺寸，比直接生成大图快且更省内存
            workflow["11"] = {"class_type": "UpscaleModelLoader",
                              "inputs": {"model_name": UPSCALE_MODEL}}
            workflow["12"] = {"class_type": "ImageUpscaleWithModel",
                              "inputs": {"upscale_model": ["11", 0],
                                         "image": ["9", 0]}}
            workflow["13"] = {"class_type": "ImageScale",
                              "inputs": {"width": width * upscale,
                                         "height": height * upscale,
                                         "upscale_method": "lanczos",
                                         "crop": "disabled",
                                         "image": ["12", 0]}}
            save_from = "13"
        else:
            save_from = "9"
        workflow["10"] = {"class_type": "SaveImage",
                          "inputs": {"filename_prefix": "manhua_job",
                                     "images": [save_from, 0]}}
        return workflow

    async def generate(
        self, prompt: str, negative_prompt: str, seed: int,
        width: int, height: int, steps: int, upscale: int = 1,
        reference_path=None, reference_paths=None, progress_callback=None,
        cancel_callback=None,
    ) -> bytes:
        # 兼容旧的单张 reference_path 用法
        paths = list(reference_paths or [])
        if reference_path and not paths:
            paths = [reference_path]
        reference_filenames = []
        paths = [Path(p) for p in paths[:3] if Path(p).exists()]  # Omni 最多 3 张
        for i, src in enumerate(paths):
            if len(paths) > 1:
                # 多参考图时 Z-Image 会把各参考 latent 堆叠，尺寸必须一致，
                # 否则 KSampler 报 shape mismatch。统一缩放成 1024x1024。
                from PIL import Image
                name = f"ref_norm_{i}_{src.stem}.png"
                dst = COMFYUI_DIR / "input" / name
                with Image.open(src) as im:
                    if im.size != (1024, 1024) or not dst.exists():
                        im.convert("RGB").resize((1024, 1024), Image.LANCZOS).save(dst)
                reference_filenames.append(name)
            else:
                dst = COMFYUI_DIR / "input" / src.name
                if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                    shutil.copy2(src, dst)
                reference_filenames.append(src.name)
        workflow = self._build_workflow(
            prompt, negative_prompt, seed, width, height, steps, upscale,
            reference_filenames or None,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            await self.ensure_running(client)
            client_id = uuid.uuid4().hex
            listener = None
            socket = None

            async def listen_progress():
                nonlocal socket
                socket = await websockets.connect(
                    f"ws://127.0.0.1:8188/ws?clientId={client_id}",
                    max_size=2**20,
                )
                async for raw in socket:
                    if not isinstance(raw, str):
                        continue
                    message = json.loads(raw)
                    if message.get("type") != "progress":
                        continue
                    data = message.get("data", {})
                    value = int(data.get("value", 0))
                    maximum = max(1, int(data.get("max", steps)))
                    if progress_callback:
                        await progress_callback(
                            round(value / maximum * 100),
                            f"采样 {value}/{maximum} 步",
                        )

            if progress_callback:
                listener = asyncio.create_task(listen_progress())
                await progress_callback(0, "已提交到 ComfyUI")
            try:
                r = await client.post(
                    BASE_URL + "/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
                r.raise_for_status()
                prompt_id = r.json()["prompt_id"]

                waited = 0
                while waited < MAX_WAIT_SECONDS:
                    await asyncio.sleep(3)
                    waited += 3
                    if cancel_callback and cancel_callback():
                        # 同时处理正在采样和仍在 ComfyUI 内部排队的情况。
                        await client.post(BASE_URL + "/interrupt")
                        await client.post(BASE_URL + "/queue", json={"delete": [prompt_id]})
                        raise RuntimeError("GENERATION_CANCELLED_BY_USER")
                    h = await client.get(BASE_URL + f"/history/{prompt_id}")
                    history = h.json()
                    if prompt_id not in history:
                        continue
                    entry = history[prompt_id]
                    if entry.get("status", {}).get("status_str") == "error":
                        raise RuntimeError(
                            "ComfyUI 生成失败：" + json.dumps(entry["status"], ensure_ascii=False)[:300]
                        )
                    if progress_callback:
                        await progress_callback(100, "解码与放大图片")
                    img = entry["outputs"]["10"]["images"][0]
                    r = await client.get(
                        BASE_URL + "/view",
                        params={
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": img["type"],
                        },
                    )
                    r.raise_for_status()
                    return r.content
            finally:
                if listener:
                    listener.cancel()
                    with contextlib.suppress(
                        asyncio.CancelledError,
                        websockets.WebSocketException,
                        ConnectionError,
                    ):
                        await listener
                if socket:
                    with contextlib.suppress(websockets.WebSocketException, ConnectionError):
                        await socket.close()

        raise TimeoutError("ComfyUI 生成超时")
