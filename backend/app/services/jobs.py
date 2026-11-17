"""Background job queue.

`JobQueue` is the interface the API talks to. `LocalJobQueue` is the MVP
implementation: one worker thread that processes jobs sequentially (the GPU
can only do one thing at a time on a 4 GB card anyway). A Redis/RQ or Celery
backend can implement the same three methods later."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional, Protocol

from ..errors import AppError, JobCancelled, JobTimeout
from .db import Database

log = logging.getLogger("enhancer.jobs")
Processor = Callable[[dict, Callable[[float, str], None]], dict]


class JobQueue(Protocol):
    def submit(self, job_id: str) -> None: ...
    def cancel(self, job_id: str) -> bool: ...
    def live(self, job_id: str) -> Optional[dict]: ...


class LocalJobQueue:
    def __init__(self, db: Database, processor: Processor, timeout_s: int = 1800,
                 idle_task: Optional[Callable[[], None]] = None, idle_every_s: int = 1800):
        self.db = db
        self.processor = processor
        self.timeout_s = timeout_s
        self.idle_task = idle_task
        self.idle_every_s = idle_every_s
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._live: dict = {}
        self._cancelled: set = set()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        for job in self.db.unfinished_jobs():
            self.db.update_job(job["id"], status="failed", finished_at=time.time(), error={
                "code": "interrupted", "retryable": True, "details": {},
                "message": "Processing was interrupted by a restart. Retry to run it again."})
        self._thread = threading.Thread(target=self._run, name="enhance-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)

    def submit(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.discard(job_id)
            self._live[job_id] = {"progress": 0.0, "stage": "Queued"}
        self._queue.put(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job or job["status"] not in ("queued", "processing"):
            return False
        with self._lock:
            self._cancelled.add(job_id)
        if job["status"] == "queued":
            self.db.update_job(job_id, status="cancelled", finished_at=time.time())
        return True

    def live(self, job_id: str) -> Optional[dict]:
        with self._lock:
            state = self._live.get(job_id)
            return dict(state) if state else None

    def active_ids(self) -> set:
        """Ids of queued and running jobs."""
        with self._lock:
            return set(self._live)

    def queue_position(self, job_id: str) -> Optional[int]:
        with self._queue.mutex:
            pending = [j for j in self._queue.queue if j]
        return pending.index(job_id) + 1 if job_id in pending else None

    # -- worker ---------------------------------------------------------
    def _run(self) -> None:
        last_idle = 0.0
        while True:
            try:
                job_id = self._queue.get(timeout=30)
            except queue.Empty:
                job_id = ""
            if job_id is None:
                return
            if job_id:
                self._process(job_id)
            if self.idle_task and time.time() - last_idle > self.idle_every_s:
                last_idle = time.time()
                try:
                    self.idle_task()
                except Exception:
                    log.exception("Idle task failed")

    def _process(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is None or job["status"] != "queued":
            self._forget(job_id)
            return
        started = time.time()
        self.db.update_job(job_id, status="processing", started_at=started, progress=0.0,
                           stage="Starting", attempts=job["attempts"] + 1, error=None)
        last_write = [0.0]

        def report(fraction: float, stage: str) -> None:
            if job_id in self._cancelled:
                raise JobCancelled()
            if time.time() - started > self.timeout_s:
                raise JobTimeout()
            fraction = float(min(max(fraction, 0.0), 0.99))
            with self._lock:
                self._live[job_id] = {"progress": fraction, "stage": stage}
            if time.time() - last_write[0] > 1.0:
                last_write[0] = time.time()
                self.db.update_job(job_id, progress=fraction, stage=stage)

        try:
            result = self.processor(job, report)
            self.db.update_job(job_id, status="completed", progress=1.0, stage="Done",
                               result=result, finished_at=time.time())
            log.info("Job %s completed in %.1fs", job_id, time.time() - started)
        except JobCancelled:
            self.db.update_job(job_id, status="cancelled", stage="Cancelled",
                               finished_at=time.time())
        except JobTimeout:
            self._fail(job_id, AppError(
                "timeout", f"Processing took longer than {self.timeout_s // 60} minutes and was "
                           f"stopped. Try a smaller output size or the fast model.",
                retryable=True))
        except AppError as exc:
            log.warning("Job %s failed: %s (%s)", job_id, exc.message, exc.code)
            self._fail(job_id, exc)
        except MemoryError:
            self._fail(job_id, AppError("out_of_memory", "The system ran out of memory. Try a "
                                        "smaller output size.", retryable=True))
        except Exception:
            log.exception("Job %s crashed", job_id)
            self._fail(job_id, AppError("processing_failed", "Processing failed unexpectedly. "
                                        "See backend/data/logs/backend.log for details.",
                                        retryable=True))
        finally:
            self._forget(job_id)

    def _fail(self, job_id: str, err: AppError) -> None:
        self.db.update_job(job_id, status="failed", stage="Failed", error=err.to_dict(),
                           finished_at=time.time())

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._live.pop(job_id, None)
            self._cancelled.discard(job_id)
