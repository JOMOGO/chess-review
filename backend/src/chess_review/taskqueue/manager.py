"""In-process async task queue replacing Redis+ARQ."""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class JobState:
    status: str = "pending"
    total_items: int = 0
    completed_items: int = 0
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class _Job:
    id: uuid.UUID
    func: Callable[..., Coroutine[Any, Any, None]]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class TaskManager:
    """In-process async task queue. Created at app startup."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self._jobs: dict[uuid.UUID, JobState] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._run_loop())
        logger.info("TaskManager started (max_concurrent=%d)", self._semaphore._value)

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("TaskManager stopped")

    async def enqueue(
        self,
        func: Callable[..., Coroutine[Any, Any, None]],
        *args: Any,
        **kwargs: Any,
    ) -> uuid.UUID:
        job_id = uuid.uuid4()
        self._jobs[job_id] = JobState()
        await self._queue.put(_Job(job_id, func, args, kwargs))
        logger.info("Enqueued job %s -> %s", job_id, func.__name__)
        return job_id

    def get_status(self, job_id: uuid.UUID) -> JobState | None:
        return self._jobs.get(job_id)

    async def _run_loop(self) -> None:
        while True:
            job = await self._queue.get()
            asyncio.create_task(self._execute(job))

    async def _execute(self, job: _Job) -> None:
        async with self._semaphore:
            state = self._jobs[job.id]
            state.status = "running"
            state.started_at = datetime.now(timezone.utc)
            logger.info("Starting job %s", job.id)
            try:
                await job.func(*job.args, progress=state, **job.kwargs)
                state.status = "done"
                state.completed_at = datetime.now(timezone.utc)
                logger.info("Job %s completed", job.id)
            except Exception:
                state.status = "failed"
                state.completed_at = datetime.now(timezone.utc)
                logger.exception("Job %s failed", job.id)
