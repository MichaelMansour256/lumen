"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .context import AppContext
from .errors import AppError
from .routes import images, jobs, system
from .security import KEY_HEADER, check_access_key

log = logging.getLogger("enhancer")


def _setup_logging(settings: Settings) -> None:
    root = logging.getLogger("enhancer")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for handler in (logging.StreamHandler(),
                    RotatingFileHandler(log_dir / "backend.log", maxBytes=2_000_000,
                                        backupCount=2, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def create_app(settings: Optional[Settings] = None, models=None) -> FastAPI:
    settings = settings or load_settings()
    _setup_logging(settings)
    ctx = AppContext(settings, models=models)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.queue.start()
        ctx.cleanup()
        info = ctx.models.device()
        log.info("Device: %s (%s) | torch %s | VRAM free %s MB", info["device"],
                 info["gpu_name"] or "no GPU", info["torch_version"], info["vram_free_mb"])
        if settings.public:
            log.info("PUBLIC mode | access key %s | origins %s | hosts %s",
                     "ON" if settings.access_key else "OFF (anyone can use it!)",
                     ", ".join(settings.allowed_origins), ", ".join(settings.allowed_hosts))
        yield
        ctx.queue.stop()

    docs = {} if not settings.public else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="AI Image Enhancer API", version="1.1.0", lifespan=lifespan, **docs)
    app.state.ctx = ctx
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_origin_regex=settings.allowed_origin_regex or None,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", KEY_HEADER],
                       expose_headers=["Content-Disposition"], max_age=600)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"error": exc.to_dict()}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse({"error": {"code": "invalid_request", "retryable": False,
                                       "message": "The request was not valid.", "details": {}}},
                            status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse({"error": {"code": "server_error", "retryable": True,
                                       "message": "Something went wrong on the server.",
                                       "details": {}}}, status_code=500)

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "auth": bool(settings.access_key)}

    protected = [Depends(check_access_key)]
    app.include_router(system.router, dependencies=protected)
    app.include_router(images.router, dependencies=protected)
    app.include_router(jobs.router, dependencies=protected)
    return app
