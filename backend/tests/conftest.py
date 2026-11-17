"""Shared test helpers. The fake model manager stands in for PyTorch so the
pipeline, scaling engine, job queue and API can be tested on any machine;
tests/test_models.py exercises the real models when they are installed."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.tiling import tiled_apply  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.errors import AppError  # noqa: E402


def make_image(w: int = 96, h: int = 64, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.stack([xx * 255 / max(w - 1, 1), yy * 255 / max(h - 1, 1),
                    (xx + yy) * 255 / max(w + h - 2, 1)], axis=2)
    img += rng.normal(0, 6, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 4, (240, 60, 40), -1)
    cv2.rectangle(img, (4, 4), (w // 4, h // 4), (20, 200, 90), 2)
    return np.ascontiguousarray(img)


def image_bytes(fmt: str = "PNG", w: int = 96, h: int = 64, **save) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(make_image(w, h)).save(buf, fmt, **save)
    return buf.getvalue()


class FakeUpscaler:
    scale, device, half, supports_denoise, last_tile = 4, "cpu", False, False, 32

    def __init__(self):
        self.calls = []

    def upscale(self, img, progress=None):
        self.calls.append(img.shape[:2])
        fn = lambda t: cv2.resize(t, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)  # noqa: E731
        return tiled_apply(img, fn, 4, 32, 8, progress)


class FakeModels:
    """Implements the ModelManager interface with a deterministic 4x 'model'."""
    installed = {"realesr-general"}

    def __init__(self):
        self.upscaler = FakeUpscaler()

    def availability(self, model_id):
        if model_id in self.installed or model_id == "lanczos":
            return True, None
        return False, "Model is not downloaded."

    def is_available(self, model_id):
        return self.availability(model_id)[0]

    def face_detection_available(self):
        return False

    def detect_faces(self, rgb):
        return None

    def get_upscaler(self, model_id, preference="auto"):
        if not self.is_available(model_id):
            raise AppError("model_unavailable", "AI model unavailable.", status=503)
        return self.upscaler

    def get_face_restorer(self, model_id, preference="auto"):
        raise AppError("model_unavailable", "AI model unavailable.", status=503)

    def release_gpu(self):
        pass

    def device(self, preference="auto"):
        return {"torch_available": False, "device": "cpu", "cuda_available": False,
                "gpu_name": None, "torch_version": None, "vram_free_mb": None,
                "vram_total_mb": None, "fp16": False, "note": "fake", "torch_error": None}

    def describe(self):
        return []


@pytest.fixture
def settings(tmp_path):
    return load_settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models",
                         allowed_hosts=("testserver", "127.0.0.1", "localhost"),
                         job_timeout_s=60)


@pytest.fixture
def ctx(settings):
    from app.context import AppContext
    context = AppContext(settings, models=FakeModels())
    context.queue.start()
    yield context
    context.queue.stop()
