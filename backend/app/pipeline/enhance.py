"""The enhancement pipeline. Order of operations:

  1. source clean-up   denoise / JPEG artifact reduction / deblur
  2. AI upscaling      staged, tiled passes planned by the scaling engine
  3. exact resize      to the requested output size
  4. face restoration  detect -> align -> restore -> blend back
  5. tone and colour   fade restore, auto colour, low light, manual sliders
  6. detail            local contrast, sharpening
  7. intensity         blend with a plain resize of the original
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional, Tuple

import numpy as np

from ..ai.registry import LANCZOS_ID, get_spec
from ..errors import AppError
from . import classical as ops
from .analysis import analyze_image
from .presets import pick_model, recommend
from .scaling import ScalePlan, build_plan
from .settings import EnhanceSettings

Progress = Callable[[float, str], None]


def resolve_settings(settings: EnhanceSettings, analysis: Optional[dict], models) -> Tuple[
        EnhanceSettings, list]:
    """Apply the automatic recommendation (when auto is on) and pick a concrete model."""
    notes = []
    s = settings
    if s.auto and analysis:
        rec = recommend(analysis, models.is_available, models.is_available(s.face_model))
        patch = dict(rec["settings"])
        if s.model != "auto":
            patch.pop("model", None)      # an explicit model choice always wins
        s = replace(s, **patch)
        notes.extend(rec["reasons"])
    if s.model == "auto":
        category = analysis["category"] if analysis else "default"
        chosen = pick_model(category, models.is_available)
        if chosen is None:
            raise AppError("model_unavailable",
                           "AI model unavailable: no upscaling model is installed. Run "
                           "setup.bat (or backend\\scripts\\download_models.py) and try again.",
                           status=503, retryable=True)
        s = replace(s, model=chosen)
    elif s.model != LANCZOS_ID:
        spec = get_spec(s.model)
        if spec is None or spec.kind != "upscaler":
            raise AppError("invalid_settings", "Unknown upscaling model.")
    for model_id in ([s.model] if s.model != LANCZOS_ID else []) + (
            [s.face_model] if s.face_restore else []):
        ok, reason = models.availability(model_id)
        if not ok:
            raise AppError("model_unavailable",
                           f"AI model unavailable: {reason} Run setup.bat (or "
                           f"backend\\scripts\\download_models.py) and try again.",
                           status=503, retryable=True)
    return s, notes


def model_scale(model_id: str) -> int:
    return 0 if model_id == LANCZOS_ID else get_spec(model_id).scale


def plan_for(src_w: int, src_h: int, s: EnhanceSettings, limits) -> ScalePlan:
    return build_plan(src_w, src_h, s, model_scale(s.model),
                      limits.max_output_pixels, limits.max_output_side)


def run_enhancement(rgb: np.ndarray, alpha: Optional[np.ndarray], settings: EnhanceSettings,
                    models, limits, analysis: Optional[dict] = None,
                    progress: Optional[Progress] = None) -> Tuple[np.ndarray, Optional[np.ndarray], dict]:
    """`models` is a ModelManager (or any object with the same interface);
    `limits` exposes max_output_pixels / max_output_side.
    `progress(fraction, stage)` may raise to abort (cancel / timeout)."""
    report = progress or (lambda fraction, stage: None)
    started = time.time()
    src_h, src_w = rgb.shape[:2]
    report(0.0, "Analysing")
    if analysis is None and settings.auto:
        analysis = analyze_image(rgb, models.detect_faces)
    s, notes = resolve_settings(settings, analysis, models)
    plan = plan_for(src_w, src_h, s, limits)
    warnings = []
    meta = {"model": s.model, "passes": plan.passes, "settings": s.to_dict(), "notes": notes,
            "warnings": warnings, "faces_restored": 0, "device": "cpu", "fp16": False, "tile": 0}

    # 1. source clean-up ------------------------------------------------
    work = rgb
    use_ai = s.model != LANCZOS_ID
    upscaler = None
    if use_ai:
        upscaler = models.get_upscaler(s.model, s.device)
        meta.update(device=upscaler.device, fp16=bool(getattr(upscaler, "half", False)))
    model_denoises = bool(upscaler is not None and getattr(upscaler, "supports_denoise", False))
    report(0.02, "Cleaning up source")
    if s.denoise > 0.02 and not model_denoises:
        work = ops.denoise(work, s.denoise)
    if s.jpeg_artifacts > 0.02:
        work = ops.reduce_jpeg_artifacts(work, s.jpeg_artifacts)
    if s.deblur > 0.02:
        work = ops.deblur(work, s.deblur)

    # 2. AI upscaling ---------------------------------------------------
    if use_ai:
        if model_denoises:
            upscaler.set_denoise(s.denoise)
        for i, (in_w, in_h) in enumerate(plan.stage_inputs):
            if i > 0:
                work = ops.resize(work, in_w, in_h)
            lo, span = 0.05 + 0.65 * i / plan.passes, 0.65 / plan.passes
            label = f"AI upscaling (pass {i + 1}/{plan.passes})" if plan.passes > 1 else "AI upscaling"
            work = upscaler.upscale(work, lambda f, lo=lo, span=span, label=label:
                                    report(round(lo + span * f, 4), label))
        meta["tile"] = getattr(upscaler, "last_tile", 0)

    # 3. exact output size ----------------------------------------------
    report(0.7, "Resizing to output size")
    work = ops.resize(work, plan.out_w, plan.out_h)
    if work is rgb:
        work = rgb.copy()

    # 4. face restoration -----------------------------------------------
    if s.face_restore:
        report(0.72, "Detecting faces")
        faces = models.detect_faces(work)
        if faces is None:
            warnings.append("Face restoration skipped: the face detector is not installed.")
        elif not faces:
            warnings.append("Face restoration skipped: no faces were detected.")
        else:
            models.release_gpu()
            restorer = models.get_face_restorer(s.face_model, s.device)
            meta["faces_restored"] = restorer.restore(
                work, faces, s.face_strength,
                lambda f: report(0.74 + 0.14 * f, "Restoring faces"))
            meta["face_model"] = s.face_model

    # 5-6. tone, colour, detail -------------------------------------------
    report(0.88, "Adjusting colour and detail")
    if s.fade_restore:
        work = ops.fade_restore(work)
    if s.auto_color:
        work = ops.auto_color(work)
    work = ops.low_light(work, s.low_light)
    work = ops.color_adjust(work, s.exposure, s.brightness, s.contrast, s.temperature,
                            s.saturation)
    work = ops.enhance_detail(work, s.detail)
    work = ops.sharpen(work, s.sharpness)

    # 7. intensity ------------------------------------------------------
    if s.intensity < 0.999:
        report(0.95, "Blending")
        work = ops.blend(ops.resize(rgb, plan.out_w, plan.out_h), work, s.intensity)

    out_alpha = ops.resize(alpha, plan.out_w, plan.out_h) if alpha is not None else None
    if work.shape[1] != plan.out_w or work.shape[0] != plan.out_h:
        raise AppError("processing_failed", "Output size did not match the request.", status=500)
    meta.update(width=plan.out_w, height=plan.out_h, seconds=round(time.time() - started, 2))
    report(0.98, "Saving")
    return work, out_alpha, meta
