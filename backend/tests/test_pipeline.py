"""Tests that need only numpy / OpenCV / Pillow (no PyTorch, no FastAPI)."""
from __future__ import annotations

import io
import time

import cv2
import numpy as np
import pytest
from PIL import Image

from app.ai.tiling import tiled_apply
from app.errors import AppError
from app.pipeline import classical as ops
from app.pipeline.analysis import analyze_image
from app.pipeline.enhance import run_enhancement
from app.pipeline.presets import recommend
from app.pipeline.scaling import build_plan
from app.pipeline.settings import EnhanceSettings
from app.services import imageio
from app.services.storage import LocalStorage

from .conftest import FakeModels, image_bytes, make_image

MAXPX, MAXSIDE = 150_000_000, 16384


def S(**kw):
    return EnhanceSettings.from_dict({"auto": False, "model": "realesr-general", **kw})


def wait(ctx, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = ctx.job_view(job_id)
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# --- settings ------------------------------------------------------------
def test_settings_validation():
    assert S(factor=4).factor == 4
    for bad in ({"factor": 17}, {"sharpness": 1.5}, {"contrast": -2}, {"nope": 1},
                {"scale_mode": "dimensions"}, {"face_model": "x"}, {"auto": "yes"},
                {"device": "gpu9"}, {"factor": float("nan")}):
        with pytest.raises(AppError):
            EnhanceSettings.from_dict(bad)


# --- scaling engine --------------------------------------------------------
@pytest.mark.parametrize("factor,passes", [(1, 1), (2, 1), (4, 1), (8, 2), (16, 2), (3.5, 1), (5, 2)])
def test_plan_factors(factor, passes):
    plan = build_plan(100, 80, S(factor=factor), 4, MAXPX, MAXSIDE)
    assert (plan.out_w, plan.out_h) == (round(100 * factor), round(80 * factor))
    assert plan.passes == passes and plan.stage_inputs[0] == (100, 80)


def test_plan_custom_modes():
    assert build_plan(100, 80, S(scale_mode="percent", percent=250), 4, MAXPX, MAXSIDE).out_w == 250
    plan = build_plan(100, 80, S(scale_mode="dimensions", width=300), 4, MAXPX, MAXSIDE)
    assert (plan.out_w, plan.out_h) == (300, 240)            # aspect preserved
    plan = build_plan(100, 80, S(scale_mode="dimensions", width=300, height=500), 4, MAXPX, MAXSIDE)
    assert (plan.out_w, plan.out_h) == (300, 500) and plan.passes == 2
    assert build_plan(100, 80, S(factor=2), 0, MAXPX, MAXSIDE).passes == 0   # non-AI resize


def test_plan_limits_offer_alternative():
    with pytest.raises(AppError) as err:
        build_plan(4000, 3000, S(factor=16), 4, MAXPX, MAXSIDE)
    assert err.value.code == "output_too_large"
    assert err.value.details["suggested_factor"] == 2
    assert err.value.details["suggested"] == {"width": 8000, "height": 6000}
    with pytest.raises(AppError) as err:
        build_plan(100, 100, S(scale_mode="dimensions", width=1700, height=100), 4, MAXPX, MAXSIDE)
    assert err.value.code == "invalid_scale"


# --- tiling ----------------------------------------------------------------
def test_tiling_is_seamless_and_exact():
    img = make_image(150, 110)
    fn = lambda t: cv2.resize(t, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)  # noqa: E731
    seen = []
    tiled = tiled_apply(img, fn, 4, 48, 8, seen.append)
    whole = fn(img)
    assert tiled.shape == (440, 600, 3)
    assert int(np.abs(tiled.astype(int) - whole.astype(int)).max()) <= 1
    assert seen[-1] == 1.0 and len(seen) == 12
    with pytest.raises(RuntimeError):
        tiled_apply(img, lambda t: t, 4, 48, 8)


# --- image I/O and validation ------------------------------------------------
@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "TIFF"])
def test_decode_supported_formats(fmt):
    rgb, alpha, info = imageio.decode_upload(image_bytes(fmt), 40_000_000, None)
    assert rgb.shape == (64, 96, 3) and alpha is None and info["width"] == 96


def test_decode_rejects_bad_input():
    cases = [
        (b"MZ\x90\x00 not an image", None, "invalid_image"),
        (image_bytes("PNG")[:200], None, "invalid_image"),
        (image_bytes("GIF"), None, "unsupported_format"),
        (image_bytes("BMP"), None, "unsupported_format"),
        (image_bytes("PNG"), "text/html", "unsupported_format"),
        (image_bytes("PNG", 8, 8), None, "image_too_small"),
    ]
    for data, mime, code in cases:
        with pytest.raises(AppError) as err:
            imageio.decode_upload(data, 40_000_000, mime)
        assert err.value.code == code
    with pytest.raises(AppError) as err:
        imageio.decode_upload(image_bytes("PNG", 400, 300), 100_000, None)
    assert err.value.code == "image_too_large"


def test_alpha_and_orientation():
    rgba = np.dstack([make_image(40, 30), np.full((30, 40), 128, np.uint8)])
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    rgb, alpha, info = imageio.decode_upload(buf.getvalue(), 10 ** 7, "image/png")
    assert info["has_alpha"] and alpha.shape == (30, 40)
    back_rgb, back_alpha = imageio.decode_png(imageio.encode_png(rgb, alpha))
    assert np.array_equal(back_rgb, rgb) and np.array_equal(back_alpha, alpha)
    exif = Image.Exif()
    exif[0x0112] = 6                                         # rotate 90 degrees
    buf = io.BytesIO()
    Image.fromarray(make_image(40, 30)).save(buf, "JPEG", exif=exif)
    rotated, _, info = imageio.decode_upload(buf.getvalue(), 10 ** 7, None)
    assert (info["width"], info["height"]) == (30, 40)


def test_convert_formats_and_names():
    png = imageio.encode_png(make_image(80, 60))
    for fmt, magic in (("png", b"\x89PNG"), ("jpg", b"\xff\xd8"), ("webp", b"RIFF")):
        data, ext, mime = imageio.convert_png(png, fmt, 85)
        assert data.startswith(magic) and ext == fmt and Image.open(io.BytesIO(data)).size == (80, 60)
    small = len(imageio.convert_png(png, "jpg", 30)[0])
    assert small < len(imageio.convert_png(png, "jpg", 95)[0])   # quality is real
    with pytest.raises(AppError):
        imageio.convert_png(png, "exe")
    assert imageio.safe_display_name("..\\..\\evil/../a<b>.png") == "a_b_.png"
    assert imageio.safe_display_name("") == "image"


def test_storage_rejects_traversal(tmp_path):
    store = LocalStorage(tmp_path)
    key = "originals/" + "a" * 32 + ".png"
    store.write(key, b"x")
    assert store.read(key) == b"x" and store.exists(key)
    for bad in ("../x.png", "originals/../../x.png", "originals/abc.png", "C:/x.png",
                "originals/" + "a" * 32 + ".exe"):
        with pytest.raises(ValueError):
            store.write(bad, b"x")
    store.delete(key)
    assert not store.exists(key)


# --- classical operations: every control changes pixels in the right direction ---
def test_manual_controls_have_real_effect():
    img = make_image(160, 120)
    mean = lambda a: float(a.mean())  # noqa: E731
    sat = lambda a: float(cv2.cvtColor(a, cv2.COLOR_RGB2HSV)[:, :, 1].mean())  # noqa: E731
    lap = lambda a: float(cv2.Laplacian(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())  # noqa: E731
    assert np.array_equal(ops.color_adjust(img), img)
    assert mean(ops.color_adjust(img, brightness=0.5)) > mean(img) > mean(ops.color_adjust(img, brightness=-0.5))
    assert mean(ops.color_adjust(img, exposure=0.5)) > mean(img)
    assert ops.color_adjust(img, contrast=0.6).std() > img.std() > ops.color_adjust(img, contrast=-0.6).std()
    assert sat(ops.color_adjust(img, saturation=0.6)) > sat(img) > sat(ops.color_adjust(img, saturation=-0.6))
    warm = ops.color_adjust(img, temperature=0.8)
    assert warm[:, :, 0].mean() > img[:, :, 0].mean() and warm[:, :, 2].mean() < img[:, :, 2].mean()
    assert lap(ops.sharpen(img, 0.8)) > lap(img)
    assert lap(ops.enhance_detail(img, 0.8)) > lap(img) * 1.5
    tall = make_image(90, 3000)                          # strips join without seams
    assert np.array_equal(ops.enhance_detail(tall, 0.7, strip=256), ops.enhance_detail(tall, 0.7, strip=5000))
    low, high = (float(np.abs(ops.enhance_detail(img, v).astype(int) - img).mean()) for v in (0.2, 0.8))
    assert high > low * 2.5                             # the slider scales the effect
    assert lap(ops.denoise(img, 0.8)) < lap(img)
    assert lap(ops.deblur(cv2.GaussianBlur(img, (0, 0), 1.5), 0.7)) > lap(cv2.GaussianBlur(img, (0, 0), 1.5))
    dark = (img * 0.25).astype(np.uint8)
    assert mean(ops.low_light(dark, 0.7)) > mean(dark) * 1.3
    faded = (img * 0.4 + 90).astype(np.uint8)
    assert ops.fade_restore(faded).std() > faded.std() * 1.5
    cast = img.copy()
    cast[:, :, 0] = np.clip(cast[:, :, 0] * 1.25, 0, 255)
    fixed = ops.auto_color(cast).reshape(-1, 3).mean(axis=0)
    before = cast.reshape(-1, 3).mean(axis=0)
    assert abs(fixed[0] - fixed[1]) < abs(before[0] - before[1])
    jpg = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 8])[1], 1)
    assert not np.array_equal(ops.reduce_jpeg_artifacts(jpg, 0.7), jpg)
    assert np.array_equal(ops.blend(img, warm, 1.0), warm)
    half = ops.blend(img, warm, 0.5)
    assert abs(mean(half) - (mean(img) + mean(warm)) / 2) < 1.0


# --- analysis ----------------------------------------------------------------
def test_analysis_measures_real_problems():
    base = cv2.resize(make_image(96, 64), (480, 320), interpolation=cv2.INTER_CUBIC)
    clean = analyze_image(base)
    assert clean["faces"] is None and clean["faces_note"]         # no detector: says so
    noisy = np.clip(base + np.random.default_rng(1).normal(0, 20, base.shape), 0, 255).astype(np.uint8)
    assert analyze_image(noisy)["metrics"]["noise_sigma"] > clean["metrics"]["noise_sigma"] + 5
    assert "noise" in {i["id"] for i in analyze_image(noisy)["issues"]}
    blurred = cv2.GaussianBlur(base, (0, 0), 4)
    assert analyze_image(blurred)["metrics"]["sharpness"] < clean["metrics"]["sharpness"]
    dark = (base * 0.15).astype(np.uint8)
    assert "low_light" in {i["id"] for i in analyze_image(dark)["issues"]}
    blocky = cv2.imdecode(cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 5])[1], 1)
    assert analyze_image(blocky)["metrics"]["blockiness"] > 1.25
    flat = np.full((300, 400, 3), 255, np.uint8)
    cv2.circle(flat, (200, 150), 90, (230, 40, 40), -1)
    cv2.rectangle(flat, (40, 40), (120, 110), (30, 60, 200), -1)
    assert analyze_image(flat)["category"] == "illustration"
    rec = recommend(analyze_image(dark), lambda m: m == "realesr-general", False)
    assert rec["settings"]["low_light"] > 0 and rec["settings"]["model"] == "realesr-general"
    assert recommend(clean, lambda m: False, False)["model_available"] is False


# --- full pipeline with the fake 4x model -------------------------------------
class Limits:
    max_output_pixels, max_output_side = MAXPX, MAXSIDE


@pytest.mark.parametrize("kw,size,passes", [
    ({"factor": 1}, (96, 64), 1), ({"factor": 2}, (192, 128), 1), ({"factor": 4}, (384, 256), 1),
    ({"factor": 8}, (768, 512), 2), ({"factor": 16}, (1536, 1024), 2),
    ({"scale_mode": "percent", "percent": 310}, (298, 198), 1),
    ({"scale_mode": "dimensions", "width": 500, "height": 333}, (500, 333), 2),
    ({"scale_mode": "dimensions", "height": 100}, (150, 100), 1),
])
def test_pipeline_output_dimensions(kw, size, passes):
    models = FakeModels()
    stages = []
    out, alpha, meta = run_enhancement(make_image(), None, S(**kw), models, Limits, None,
                                       lambda f, s: stages.append((f, s)))
    assert (out.shape[1], out.shape[0]) == size == (meta["width"], meta["height"])
    assert len(models.upscaler.calls) == passes == meta["passes"]
    assert models.upscaler.calls[0] == (64, 96)                   # pass 1 sees the full source
    fractions = [f for f, _ in stages]
    assert fractions == sorted(fractions) and fractions[-1] <= 1.0


def test_pipeline_modes():
    img, models = make_image(), FakeModels()
    plain, _, meta = run_enhancement(img, None, S(model="lanczos", factor=2), models, Limits)
    assert plain.shape == (128, 192, 3) and meta["passes"] == 0 and not models.upscaler.calls
    base, _, _ = run_enhancement(img, None, S(factor=2), models, Limits)
    sharp, _, _ = run_enhancement(img, None, S(factor=2, sharpness=1.0, contrast=0.5), models, Limits)
    assert not np.array_equal(base, sharp)
    mixed, _, _ = run_enhancement(img, None, S(factor=2, sharpness=1.0, contrast=0.5, intensity=0.0),
                                  models, Limits)
    assert np.array_equal(mixed, ops.resize(img, 192, 128))       # intensity 0 = plain resize
    _, _, meta = run_enhancement(img, None, S(factor=2, face_restore=False, auto=True), models, Limits)
    assert meta["notes"]                                           # auto mode explains itself
    alpha = np.full((64, 96), 100, np.uint8)
    _, out_alpha, _ = run_enhancement(img, alpha, S(factor=4), models, Limits)
    assert out_alpha.shape == (256, 384)
    with pytest.raises(AppError) as err:
        run_enhancement(img, None, S(factor=2, model="realesrgan-x4plus"), models, Limits)
    assert err.value.code == "model_unavailable"
    with pytest.raises(AppError) as err:
        run_enhancement(img, None, S(factor=2, face_restore=True), models, Limits)
    assert err.value.code == "model_unavailable"


# --- jobs, batch, retry, cancel, cleanup ----------------------------------------
def test_job_lifecycle(ctx):
    image = ctx.add_image(image_bytes("JPEG", quality=90), "photo.jpg", "image/jpeg")
    assert image["analysis"]["width"] == 96 and image["format"] == "jpg"
    job = wait(ctx, ctx.create_job(image["id"], S(factor=4))["id"])
    assert job["status"] == "completed" and job["progress"] == 1.0
    assert (job["result"]["width"], job["result"]["height"]) == (384, 256)
    assert imageio.png_dimensions(ctx.result_bytes(job["id"])) == (384, 256)
    preview = ctx.storage.read(ctx.result_key(job["id"], "previews"))
    assert preview.startswith(b"RIFF") and Image.open(io.BytesIO(preview)).size == (384, 256)
    ctx.storage.delete(ctx.result_key(job["id"], "previews"))       # old results: made on demand
    assert ctx.storage.exists(ctx.preview_key(job["id"]))
    big = imageio.make_preview(make_image(5000, 1000))
    assert Image.open(io.BytesIO(big)).size == (4096, 819)
    with pytest.raises(AppError) as err:                         # rejected before queueing
        ctx.create_job(image["id"], S(factor=2, model="realesrgan-anime"))
    assert err.value.code == "model_unavailable"
    plan = ctx.plan(image, S(factor=2, model="realesrgan-anime"))
    assert plan["blocked"] and plan["out_w"] == 192               # size still previewed
    ctx.delete_image(image["id"])
    with pytest.raises(AppError):
        ctx.result_bytes(job["id"])
    assert not ctx.storage.exists(f"originals/{image['id']}.png")


def test_job_failure_retry_and_cancel(ctx):
    image = ctx.add_image(image_bytes(), "a.png", "image/png")
    real = ctx.models.upscaler.upscale
    state = {"fail": True}

    def flaky(img, progress=None):
        if state["fail"]:
            raise RuntimeError("boom")
        return real(img, progress)

    ctx.models.upscaler.upscale = flaky
    job = wait(ctx, ctx.create_job(image["id"], S(factor=2))["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "processing_failed"
    assert "boom" not in job["error"]["message"]                  # internals are not leaked
    with pytest.raises(AppError):
        ctx.result_bytes(job["id"])
    state["fail"] = False
    assert ctx.retry_job(job["id"])["status"] == "queued"
    job = wait(ctx, job["id"])
    assert job["status"] == "completed" and job["attempts"] == 2

    def slow(img, progress=None):
        for i in range(100):
            time.sleep(0.02)
            progress(i / 100)
        return real(img, progress)

    ctx.models.upscaler.upscale = slow
    running = ctx.create_job(image["id"], S(factor=2))
    queued = ctx.create_job(image["id"], S(factor=2))
    assert ctx.queue.cancel(queued["id"]) and ctx.job_view(queued["id"])["status"] == "cancelled"
    time.sleep(0.2)
    assert ctx.job_view(running["id"])["status"] == "processing"
    assert ctx.queue.cancel(running["id"])
    assert wait(ctx, running["id"])["status"] == "cancelled"


def test_timeout_and_cleanup(ctx):
    image = ctx.add_image(image_bytes(), "a.png", "image/png")
    ctx.queue.timeout_s = 0

    def slow(img, progress=None):
        time.sleep(0.05)
        progress(0.5)

    ctx.models.upscaler.upscale = slow
    job = wait(ctx, ctx.create_job(image["id"], S(factor=2))["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "timeout"
    assert ctx.cleanup() == 0
    with ctx.db._conn() as conn:
        conn.execute("UPDATE images SET created_at = 0")
    assert ctx.cleanup() == 1
    with pytest.raises(AppError):
        ctx.get_image(image["id"])


def test_rate_limiter_and_queue_caps(ctx):
    from app.security import RateLimiter
    limiter = RateLimiter(window_s=0.3)
    limiter.hit("uploads", "a", 3, 2)
    limiter.hit("uploads", "b", 3, 3)                 # other clients are independent
    with pytest.raises(AppError) as err:
        limiter.hit("uploads", "a", 3, 2)
    assert err.value.code == "rate_limited" and err.value.status == 429
    limiter.hit("uploads", "a", 0, 100)               # 0 = unlimited
    time.sleep(0.35)
    limiter.hit("uploads", "a", 3, 3)                 # window slid

    image = ctx.add_image(image_bytes(), "a.png", "image/png")
    real = ctx.models.upscaler.upscale

    def slow(img, progress=None):
        for i in range(50):
            time.sleep(0.02)
            progress(i / 50)
        return real(img, progress)

    ctx.models.upscaler.upscale = slow
    ctx.settings.__dict__.update(max_queued_per_client=1, max_queued_jobs=2)
    try:
        first = ctx.create_job(image["id"], S(factor=2), client="alice")
        with pytest.raises(AppError) as err:
            ctx.create_job(image["id"], S(factor=2), client="alice")
        assert err.value.code == "too_many_jobs"
        ctx.create_job(image["id"], S(factor=2), client="bob")
        with pytest.raises(AppError) as err:
            ctx.create_job(image["id"], S(factor=2), client="carol")
        assert err.value.code == "server_busy"
        assert wait(ctx, first["id"])["status"] == "completed"
    finally:
        ctx.settings.__dict__.update(max_queued_per_client=0, max_queued_jobs=0)
