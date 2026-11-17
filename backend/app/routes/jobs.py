from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ..context import AppContext
from ..errors import AppError
from ..pipeline.scaling import estimate_file_bytes
from ..pipeline.settings import EnhanceSettings
from ..security import client_id
from ..services import imageio
from .common import ID_PATTERN, get_ctx, id_param, job_view

router = APIRouter(prefix="/api", tags=["jobs"])
ImageId = Field(..., pattern=ID_PATTERN)


class PlanRequest(BaseModel):
    image_id: str = ImageId
    settings: Dict[str, Any] = Field(default_factory=dict)
    format: str = "png"
    quality: int = Field(90, ge=1, le=100)


class JobsRequest(BaseModel):
    image_ids: List[str] = Field(..., min_length=1, max_length=100)
    settings: Dict[str, Any] = Field(default_factory=dict)


class ZipRequest(BaseModel):
    job_ids: List[str] = Field(..., min_length=1, max_length=100)
    format: str = "png"
    quality: int = Field(90, ge=1, le=100)


def _check_ids(ids: List[str]) -> None:
    if any(not re.match(ID_PATTERN, i) for i in ids):
        raise AppError("invalid_id", "Invalid id.")


def _download_name(ctx: AppContext, job: dict, ext: str) -> str:
    image = ctx.db.get_image(job["image_id"]) or {"name": "image"}
    stem = image["name"].rsplit(".", 1)[0] or "image"
    return f"{stem}_enhanced.{ext}"


@router.post("/plan")
def plan(req: PlanRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Resolution preview and size estimate for the given settings (no processing)."""
    image = ctx.get_image(req.image_id)
    result = ctx.plan(image, EnhanceSettings.from_dict(req.settings))
    result["est_file_bytes"] = estimate_file_bytes(
        result["out_w"] * result["out_h"], req.format.lower(), req.quality)
    return result


@router.post("/jobs")
def create_jobs(req: JobsRequest, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Start one enhancement job per image (batch). Per-image failures are reported
    without blocking the rest of the batch."""
    _check_ids(req.image_ids)
    settings = EnhanceSettings.from_dict(req.settings)
    jobs, errors = [], []
    for image_id in req.image_ids:
        try:
            jobs.append(job_view(ctx.create_job(image_id, settings, client_id(request))))
        except AppError as exc:
            errors.append({"image_id": image_id, "error": exc.to_dict()})
    return {"jobs": jobs, "errors": errors}


@router.get("/jobs")
def list_jobs(ids: str = Query(..., max_length=4000), ctx: AppContext = Depends(get_ctx)) -> dict:
    wanted = [i for i in ids.split(",") if i]
    _check_ids(wanted)
    jobs = []
    for job_id in wanted:
        try:
            jobs.append(job_view(ctx.job_view(job_id)))
        except AppError:
            continue
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str = id_param(), ctx: AppContext = Depends(get_ctx)) -> dict:
    return job_view(ctx.job_view(job_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str = id_param(),
              device: Optional[str] = Query(None, pattern="^(auto|cpu)$"),
              ctx: AppContext = Depends(get_ctx)) -> dict:
    return job_view(ctx.retry_job(job_id, device, client_id(request)))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str = id_param(), ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"cancelled": ctx.queue.cancel(job_id)}


@router.get("/jobs/{job_id}/result")
def get_result(job_id: str = id_param(), format: str = Query("png", max_length=8),
               quality: int = Query(90, ge=1, le=100), download: bool = False,
               ctx: AppContext = Depends(get_ctx)) -> Response:
    """The enhanced image. PNG is the stored lossless result; JPG / WebP are
    encoded on request with the given quality."""
    headers = {"Cache-Control": "private, max-age=3600"}
    if format.lower() == "png":
        key = ctx.result_key(job_id)
        ext, mime, path = "png", "image/png", ctx.storage.local_path(key)
        data = None if path else ctx.storage.read(key)
    else:
        data, ext, mime = imageio.convert_png(ctx.result_bytes(job_id), format, quality)
        path = None
    if download:
        name = _download_name(ctx, ctx.db.get_job(job_id), ext)
        ascii_name = name.encode("ascii", "replace").decode().replace('"', "_")
        headers["Content-Disposition"] = f'attachment; filename="{ascii_name}"'
    if path is not None:      # streamed from disk; supports Range requests
        return FileResponse(path, media_type=mime, headers=headers)
    return Response(data, media_type=mime, headers=headers)


@router.get("/jobs/{job_id}/preview")
def get_preview(job_id: str = id_param(), ctx: AppContext = Depends(get_ctx)) -> Response:
    """Reduced-size WebP of the result (max 4096 px), used by the comparison view."""
    key = ctx.preview_key(job_id)
    headers = {"Cache-Control": "private, max-age=3600"}
    path = ctx.storage.local_path(key)
    if path is not None:
        return FileResponse(path, media_type="image/webp", headers=headers)
    return Response(ctx.storage.read(key), media_type="image/webp", headers=headers)


@router.post("/download/zip")
def download_zip(req: ZipRequest, ctx: AppContext = Depends(get_ctx)) -> Response:
    _check_ids(req.job_ids)
    buffer = io.BytesIO()
    used: set = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for job_id in req.job_ids:
            data, ext, _ = imageio.convert_png(ctx.result_bytes(job_id), req.format, req.quality)
            name = _download_name(ctx, ctx.db.get_job(job_id), ext)
            stem, n = name.rsplit(".", 1)[0], 1
            while name in used:
                n += 1
                name = f"{stem}_{n}.{ext}"
            used.add(name)
            archive.writestr(name, data)
    return Response(buffer.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="enhanced_images.zip"'})
