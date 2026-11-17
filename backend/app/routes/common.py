from __future__ import annotations

from fastapi import Path, Request

from ..context import AppContext

ID_PATTERN = r"^[0-9a-f]{32}$"


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def id_param(description: str = "Resource id"):
    return Path(..., pattern=ID_PATTERN, description=description)


def image_view(ctx: AppContext, image: dict) -> dict:
    view = dict(image)
    view["url"] = f"/api/images/{image['id']}/file"
    view["recommendation"] = ctx.recommendation(image)
    return view


def job_view(job: dict) -> dict:
    view = dict(job)
    view["result_url"] = (f"/api/jobs/{job['id']}/result" if job["status"] == "completed" else None)
    return view
