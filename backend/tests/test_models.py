"""Real AI model tests. They run only where PyTorch, spandrel and the model
weights are installed (i.e. on the target machine after setup.bat) and use
tiny images to keep GPU use minimal."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("spandrel")

from app.ai.device import device_info  # noqa: E402
from app.ai.manager import ModelManager  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.pipeline.enhance import run_enhancement  # noqa: E402
from app.pipeline.settings import EnhanceSettings  # noqa: E402

from .conftest import make_image  # noqa: E402

FACE_ASSET = Path(__file__).parent / "assets" / "face.jpg"


@pytest.fixture(scope="module")
def manager():
    return ModelManager(load_settings())


def need(manager, model_id):
    ok, reason = manager.availability(model_id)
    if not ok:
        pytest.skip(f"{model_id}: {reason}")


def enhance(manager, img, **kw):
    settings = EnhanceSettings.from_dict({"auto": False, **kw})
    try:
        return run_enhancement(img, None, settings, manager, manager.settings)
    finally:
        manager.release_gpu()


def test_gpu_detection():
    info = device_info()
    print("\nDEVICE:", info)
    assert info["torch_available"]
    if info["cuda_available"]:
        assert info["device"] == "cuda" and info["vram_total_mb"] > 0 and info["gpu_name"]
    assert device_info("cpu")["device"] == "cpu"


@pytest.mark.parametrize("model_id", ["realesr-general", "realesrgan-x4plus", "realesrgan-anime"])
@pytest.mark.parametrize("factor", [2, 4])
def test_real_upscaling(manager, model_id, factor):
    need(manager, model_id)
    img = make_image(96, 64)
    out, _, meta = enhance(manager, img, model=model_id, factor=factor)
    assert out.shape == (64 * factor, 96 * factor, 3) and out.dtype == np.uint8
    bicubic = cv2.resize(img, (96 * factor, 64 * factor), interpolation=cv2.INTER_CUBIC)
    diff = float(np.abs(out.astype(int) - bicubic.astype(int)).mean())
    print(f"\n{model_id} {factor}x on {meta['device']} fp16={meta['fp16']} tile={meta['tile']} "
          f"{meta['seconds']}s, mean diff vs bicubic {diff:.2f}")
    assert 0.3 < diff < 60          # a real model output: not a plain resize, not garbage


def test_denoise_strength_changes_weights(manager):
    need(manager, "realesr-general")
    if not manager.get_upscaler("realesr-general").supports_denoise:
        pytest.skip("weak-denoise companion weights not installed")
    img = make_image(64, 64, seed=3)
    weak, _, _ = enhance(manager, img, model="realesr-general", factor=4, denoise=0.0)
    strong, _, _ = enhance(manager, img, model="realesr-general", factor=4, denoise=1.0)
    assert not np.array_equal(weak, strong)


def test_staged_8x_with_tiles(manager):
    need(manager, "realesr-general")
    manager.settings.__dict__["tile_size"] = 64        # force several tiles
    try:
        manager._loaded.clear()
        out, _, meta = enhance(manager, make_image(150, 100), model="realesr-general", factor=8)
    finally:
        manager.settings.__dict__["tile_size"] = 0
        manager._loaded.clear()
    assert out.shape == (800, 1200, 3) and meta["passes"] == 2 and meta["tile"] == 64


def test_cpu_fallback(manager):
    need(manager, "realesr-general")
    out, _, meta = enhance(manager, make_image(48, 48), model="realesr-general", factor=4, device="cpu")
    assert out.shape == (192, 192, 3) and meta["device"] == "cpu" and meta["fp16"] is False


def test_face_restoration(manager):
    need(manager, "gfpgan")
    if not manager.face_detection_available():
        pytest.skip("face detector not installed")
    if not FACE_ASSET.is_file():
        pytest.skip("put a portrait photo at backend/tests/assets/face.jpg to run this test")
    img = cv2.cvtColor(cv2.imread(str(FACE_ASSET)), cv2.COLOR_BGR2RGB)
    k = 256 / max(img.shape[:2])
    img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    assert manager.detect_faces(img), "no face detected in the test photo"
    plain, _, _ = enhance(manager, img, model="realesr-general", factor=2)
    faces, _, meta = enhance(manager, img, model="realesr-general", factor=2,
                             face_restore=True, face_strength=0.8)
    assert meta["faces_restored"] >= 1 and faces.shape == plain.shape
    assert not np.array_equal(faces, plain)
