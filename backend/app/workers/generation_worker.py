import asyncio

from app.providers.comfyui_provider import ComfyUIProvider
from app.services import image_generation_service

_queue: asyncio.Queue[str] | None = None
_task: asyncio.Task | None = None
_provider = ComfyUIProvider()


def enqueue(job_id: str) -> None:
    if _queue is not None:
        _queue.put_nowait(job_id)


async def _loop() -> None:
    while True:
        job_id = await _queue.get()
        try:
            await image_generation_service.run_job(job_id, _provider)
        except Exception as e:
            print(f"[generation_worker] job {job_id} 最终失败: {e}")
        finally:
            _queue.task_done()


def start() -> None:
    """FastAPI 启动时调用：创建队列并恢复未完成的任务。"""
    global _queue, _task
    _queue = asyncio.Queue()

    from app.database.connection import SessionLocal
    from app.database.models import GenerationJob

    db = SessionLocal()
    try:
        stuck = (
            db.query(GenerationJob.id)
            .filter(GenerationJob.status.in_(["pending", "running"]))
            .all()
        )
        for (job_id,) in stuck:
            db.query(GenerationJob).filter(GenerationJob.id == job_id).update(
                {"status": "pending", "progress": 0, "current_variation": 0,
                 "progress_message": "服务重启后重新排队"}
            )
            _queue.put_nowait(job_id)
        db.commit()
        if stuck:
            print(f"[generation_worker] 恢复 {len(stuck)} 个未完成任务")
    finally:
        db.close()

    _task = asyncio.create_task(_loop())
