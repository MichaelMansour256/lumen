"""Application context: wires configuration, storage, database, models and the
job queue together. Routes only talk to this object."""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from typing import Callable, Optional

from .ai.manager import ModelManager
from .config import Settings
from .errors import AppError
from .pipeline.analysis import analyze_image
from .pipeline.enhance import plan_for, resolve_settings, run_enhancement
from .pipeline.settings import EnhanceSettings
from .services import imageio
from .services.db import Database
from .services.jobs import LocalJobQueue
from .security import RateLimiter
from .services.storage import LocalStorage, Storage

log = logging.getLogger("enhancer")


def new_id() -> str:
    return uuid.uuid4().hex


class AppContext:
    def __init__(self, settings: Settings, models=None, storage: Optional[Storage] = None):
        self.settings = settings
        self.storage: Storage = storage or LocalStorage(settings.data_dir / "files")
        self.db = Database(settings.data_dir / "enhancer.sqlite3")
        self.models = models or ModelManager(settings)
        self.queue = LocalJobQueue(self.db, self._process_job, settings.job_timeout_s,
                                   idle_task=self.cleanup,
                                   idle_every_s=min(1800, settings.file_ttl_hours * 900))
        self.limiter = RateLimiter()
        self._job_clients: dict = {}

    # -- images ---------------------------------------------------------
    def add_image(self, data: bytes, filename: Optional[str], mime: Optional[str]) -> dict:
        rgb, alpha, info = imageio.decode_upload(data, self.settings.max_input_pixels, mime)
        image_id = new_id()
        self.storage.write(f"originals/{image_id}.png", imageio.encode_png(rgb, alpha))
        try:
            analysis = analyze_image(rgb, self.models.detect_faces)
        except Exception:
            log.exception("Analysis failed for %s", image_id)
            analysis = None
        record = {"id": image_id, "name": imageio.safe_display_name(filename),
                  "format": info["format"], "width": info["width"], "height": info["height"],
                  "size_bytes": len(data), "has_alpha": info["has_alpha"], "analysis": analysis}
        self.db.add_image(record)
        return self.get_image(image_id)

    def get_image(self, image_id: str) -> dict:
        image = self.db.get_image(image_id)
        if image is None:
            raise AppError("not_found", "Image not found. It may have been cleaned up.", status=404)
        return image

    def delete_image(self, image_id: str) -> None:
        self.get_image(image_id)
        for job_id in self.db.delete_image(image_id):
            self.queue.cancel(job_id)
            self._job_clients.pop(job_id, None)
            self.storage.delete(f"results/{job_id}.png")
            self.storage.delete(f"previews/{job_id}.webp")
        self.storage.delete(f"originals/{image_id}.png")

    def recommendation(self, image: dict) -> Optional[dict]:
        from .pipeline.presets import recommend
        if not image.get("analysis"):
            return None
        return recommend(image["analysis"], self.models.is_available,
                         self.models.is_available("gfpgan"))

    # -- planning and jobs ------------------------------------------------
    def plan(self, image: dict, settings: EnhanceSettings, strict: bool = False) -> dict:
        """Output size plan. When a model is missing the size is still reported
        (non-strict) together with the reason enhancement is blocked."""
        blocked = None
        try:
            resolved, notes = resolve_settings(settings, image.get("analysis"), self.models)
        except AppError as exc:
            if strict or exc.code != "model_unavailable":
                raise
            blocked, notes = exc.message, []
            resolved = replace(settings, model="realesr-general", face_restore=False)
        plan = plan_for(image["width"], image["height"], resolved, self.settings).to_dict()
        plan.update(model=None if blocked else resolved.model, notes=notes, blocked=blocked)
        return plan

    def _check_capacity(self, client: str) -> None:
        cfg = self.settings
        active = self.queue.active_ids()
        if cfg.max_queued_jobs and len(active) >= cfg.max_queued_jobs:
            raise AppError("server_busy", "The server is busy with other images. Please try "
                                          "again in a few minutes.", status=503, retryable=True)
        if cfg.max_queued_per_client:
            mine = sum(1 for j in active if self._job_clients.get(j) == client)
            if mine >= cfg.max_queued_per_client:
                raise AppError("too_many_jobs",
                               f"You already have {mine} image(s) processing. Wait for them to "
                               f"finish before starting more.", status=429, retryable=True)

    def create_job(self, image_id: str, settings: EnhanceSettings, client: str = "local") -> dict:
        image = self.get_image(image_id)
        self.plan(image, settings, strict=True)         # validates size + models up front
        self._check_capacity(client)
        self.limiter.hit("enhancements", client, self.settings.rate_jobs_per_hour)
        job_id = new_id()
        self.db.add_job(job_id, image_id, settings.to_dict())
        self._job_clients[job_id] = client
        self.queue.submit(job_id)
        return self.job_view(job_id)

    def retry_job(self, job_id: str, device: Optional[str] = None, client: str = "local") -> dict:
        job = self.db.get_job(job_id)
        if job is None:
            raise AppError("not_found", "Job not found.", status=404)
        if job["status"] not in ("failed", "cancelled"):
            raise AppError("invalid_state", "Only failed or cancelled jobs can be retried.")
        self._check_capacity(client)
        self.limiter.hit("enhancements", client, self.settings.rate_jobs_per_hour)
        self._job_clients[job_id] = client
        settings = dict(job["settings"])
        if device in ("auto", "cpu"):
            settings["device"] = device
        self.db.update_job(job_id, status="queued", progress=0.0, stage="Queued", error=None,
                           settings=settings, finished_at=None)
        self.queue.submit(job_id)
        return self.job_view(job_id)

    def job_view(self, job_id: str) -> dict:
        job = self.db.get_job(job_id)
        if job is None:
            raise AppError("not_found", "Job not found.", status=404)
        live = self.queue.live(job_id) if job["status"] in ("queued", "processing") else None
        if live and job["status"] == "processing":
            job["progress"], job["stage"] = live["progress"], live["stage"]
        job["queue_position"] = (self.queue.queue_position(job_id)
                                 if job["status"] == "queued" else None)
        return job

    def _process_job(self, job: dict, report: Callable[[float, str], None]) -> dict:
        image = self.get_image(job["image_id"])
        settings = EnhanceSettings.from_dict(job["settings"])
        rgb, alpha = imageio.decode_png(self.storage.read(f"originals/{image['id']}.png"))
        try:
            out, out_alpha, meta = run_enhancement(
                rgb, alpha, settings, self.models, self.settings, image.get("analysis"), report)
        finally:
            self.models.release_gpu()
        key = f"results/{job['id']}.png"
        self.storage.write(key, imageio.encode_png(out, out_alpha))
        self.storage.write(f"previews/{job['id']}.webp", imageio.make_preview(out, out_alpha))
        del out, out_alpha
        # Only report success once the file exists and has the requested size.
        width, height = imageio.png_dimensions(self.storage.read(key))
        if (width, height) != (meta["width"], meta["height"]):
            self.storage.delete(key)
            raise AppError("processing_failed", "The saved result failed validation.", status=500)
        meta["size_bytes"] = self.storage.size(key)
        return meta

    def result_key(self, job_id: str, kind: str = "results") -> str:
        job = self.db.get_job(job_id)
        key = f"{kind}/{job_id}.{'png' if kind == 'results' else 'webp'}"
        if job is None or job["status"] != "completed" or not self.storage.exists(key):
            raise AppError("not_found", "Result not available. It may have been cleaned up.",
                           status=404)
        return key

    def preview_key(self, job_id: str) -> str:
        """Preview of a result; made on demand for results saved before previews existed."""
        key = f"previews/{job_id}.webp"
        if not self.storage.exists(key):
            rgb, alpha = imageio.decode_png(self.storage.read(self.result_key(job_id)))
            self.storage.write(key, imageio.make_preview(rgb, alpha))
        return self.result_key(job_id, "previews")

    def result_bytes(self, job_id: str) -> bytes:
        job = self.db.get_job(job_id)
        key = f"results/{job_id}.png"
        if job is None or job["status"] != "completed" or not self.storage.exists(key):
            raise AppError("not_found", "Result not available. It may have been cleaned up.",
                           status=404)
        return self.storage.read(key)

    # -- housekeeping -----------------------------------------------------
    def cleanup(self) -> int:
        ttl = self.settings.file_ttl_hours * 3600
        removed = 0
        for row in self.db.images_older_than(ttl):
            try:
                self.delete_image(row["id"])
                removed += 1
            except AppError:
                pass
        self.storage.purge_older_than(ttl)
        if removed:
            log.info("Cleanup removed %d expired image(s)", removed)
        return removed
