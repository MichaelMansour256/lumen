from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import AppContext
from ..pipeline.presets import PRESETS
from ..pipeline.settings import MAX_FACTOR, EnhanceSettings
from .common import get_ctx

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system")
def system(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Hardware status, installed models, presets, defaults and limits."""
    s = ctx.settings
    return {
        "device": ctx.models.device(),
        "models": ctx.models.describe(),
        "face_detection": ctx.models.face_detection_available(),
        "presets": [{"id": k, **v} for k, v in PRESETS.items()],
        "defaults": EnhanceSettings().to_dict(),
        "public": s.public,
        "limits": {
            "max_upload_mb": s.max_upload_mb, "max_files_per_upload": s.max_files_per_upload,
            "max_input_pixels": s.max_input_pixels, "max_output_pixels": s.max_output_pixels,
            "max_output_side": s.max_output_side, "max_factor": MAX_FACTOR,
            "file_ttl_hours": s.file_ttl_hours,
            "rate_uploads_per_hour": s.rate_uploads_per_hour,
            "rate_jobs_per_hour": s.rate_jobs_per_hour,
        },
    }
