"""Runtime configuration, read from environment variables / backend/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    models_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: tuple = ("http://localhost:3000", "http://127.0.0.1:3000")
    allowed_hosts: tuple = ("127.0.0.1", "localhost")
    max_upload_mb: int = 50
    max_files_per_upload: int = 20
    max_input_pixels: int = 40_000_000
    max_output_pixels: int = 150_000_000
    max_output_side: int = 16384
    job_timeout_s: int = 1800
    file_ttl_hours: int = 24
    device: str = "auto"          # auto | cuda | cpu
    fp16: bool = True
    tile_size: int = 0            # 0 = choose automatically from free VRAM
    tile_pad: int = 16
    codeformer_fidelity: float = 0.7
    max_faces: int = 20
    # Public (internet-facing) mode -------------------------------------
    public: bool = False          # hides /docs, enables the limits below when set
    access_key: str = ""          # when set, every /api call except /api/health needs it
    allowed_origin_regex: str = ""
    rate_uploads_per_hour: int = 0    # per client; 0 = unlimited
    rate_jobs_per_hour: int = 0       # per client; 0 = unlimited
    max_queued_jobs: int = 0          # all clients together; 0 = unlimited
    max_queued_per_client: int = 0    # 0 = unlimited


def load_settings(**overrides) -> Settings:
    env_file = os.environ.get("ENHANCER_ENV_FILE", ".env")
    env_path = Path(env_file)
    _load_dotenv(env_path if env_path.is_absolute() else BACKEND_DIR / env_path)
    env = os.environ.get

    def path(name: str, default: Path) -> Path:
        raw = env(name)
        p = Path(raw) if raw else default
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    values = dict(
        data_dir=path("ENHANCER_DATA_DIR", BACKEND_DIR / "data"),
        models_dir=path("ENHANCER_MODELS_DIR", BACKEND_DIR / "models"),
        host=env("ENHANCER_HOST", "127.0.0.1"),
        port=int(env("ENHANCER_PORT", "8000")),
        allowed_origins=tuple(
            o.strip() for o in env(
                "ENHANCER_ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()),
        allowed_hosts=tuple(
            h.strip() for h in env("ENHANCER_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
            if h.strip()),
        max_upload_mb=int(env("ENHANCER_MAX_UPLOAD_MB", "50")),
        max_files_per_upload=int(env("ENHANCER_MAX_FILES_PER_UPLOAD", "20")),
        max_input_pixels=int(env("ENHANCER_MAX_INPUT_PIXELS", "40000000")),
        max_output_pixels=int(env("ENHANCER_MAX_OUTPUT_PIXELS", "150000000")),
        max_output_side=int(env("ENHANCER_MAX_OUTPUT_SIDE", "16384")),
        job_timeout_s=int(env("ENHANCER_JOB_TIMEOUT_S", "1800")),
        file_ttl_hours=int(env("ENHANCER_FILE_TTL_HOURS", "24")),
        device=env("ENHANCER_DEVICE", "auto").lower(),
        fp16=env("ENHANCER_FP16", "1") not in ("0", "false", "False"),
        tile_size=int(env("ENHANCER_TILE_SIZE", "0")),
        tile_pad=int(env("ENHANCER_TILE_PAD", "16")),
        codeformer_fidelity=float(env("ENHANCER_CODEFORMER_FIDELITY", "0.7")),
        max_faces=int(env("ENHANCER_MAX_FACES", "20")),
        public=env("ENHANCER_PUBLIC", "0") in ("1", "true", "True"),
        access_key=env("ENHANCER_ACCESS_KEY", ""),
        allowed_origin_regex=env("ENHANCER_ALLOWED_ORIGIN_REGEX", ""),
        rate_uploads_per_hour=int(env("ENHANCER_RATE_UPLOADS_PER_HOUR", "0")),
        rate_jobs_per_hour=int(env("ENHANCER_RATE_JOBS_PER_HOUR", "0")),
        max_queued_jobs=int(env("ENHANCER_MAX_QUEUED_JOBS", "0")),
        max_queued_per_client=int(env("ENHANCER_MAX_QUEUED_PER_CLIENT", "0")),
    )
    values.update(overrides)
    return Settings(**values)
