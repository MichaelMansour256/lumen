from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from ..context import AppContext
from ..errors import AppError
from ..security import client_id
from .common import get_ctx, id_param, image_view

router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("")
async def upload_images(request: Request, files: List[UploadFile] = File(...),
                        ctx: AppContext = Depends(get_ctx)) -> dict:
    """Upload one or more images. Each file is validated independently; the
    response lists accepted images and per-file errors."""
    limits = ctx.settings
    if len(files) > limits.max_files_per_upload:
        raise AppError("too_many_files",
                       f"Upload at most {limits.max_files_per_upload} images at a time.")
    ctx.limiter.hit("uploads", client_id(request), limits.rate_uploads_per_hour, len(files))
    max_bytes = limits.max_upload_mb * 1024 * 1024
    images, errors = [], []
    for index, upload in enumerate(files):
        name = upload.filename or "image"
        try:
            data = await upload.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise AppError("file_too_large",
                               f"File is too large. The limit is {limits.max_upload_mb} MB.",
                               status=413)
            if not data:
                raise AppError("invalid_image", "The file is empty.")
            image = await run_in_threadpool(ctx.add_image, data, name, upload.content_type)
            images.append({**image_view(ctx, image), "upload_index": index})
        except AppError as exc:
            errors.append({"name": name[:120], "error": exc.to_dict()})
        finally:
            await upload.close()
    return {"images": images, "errors": errors}


@router.get("/{image_id}")
def get_image(image_id: str = id_param(), ctx: AppContext = Depends(get_ctx)) -> dict:
    return image_view(ctx, ctx.get_image(image_id))


@router.get("/{image_id}/file")
def get_image_file(image_id: str = id_param(), ctx: AppContext = Depends(get_ctx)):
    """The original image exactly as decoded (lossless PNG), used for the comparison view."""
    ctx.get_image(image_id)
    key = f"originals/{image_id}.png"
    headers = {"Cache-Control": "private, max-age=3600"}
    path = ctx.storage.local_path(key)
    if path is not None:
        return FileResponse(path, media_type="image/png", headers=headers)
    if not ctx.storage.exists(key):
        raise AppError("not_found", "Image file not found.", status=404)
    return Response(ctx.storage.read(key), media_type="image/png", headers=headers)


@router.delete("/{image_id}")
def delete_image(image_id: str = id_param(), ctx: AppContext = Depends(get_ctx)) -> dict:
    ctx.delete_image(image_id)
    return {"deleted": image_id}
