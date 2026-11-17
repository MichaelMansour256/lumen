"""Scaling engine: resolves the requested output size, enforces limits and
plans staged AI passes. It never silently lowers the requested resolution -
impossible requests raise an AppError that carries a supported alternative."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import List, Tuple

from ..errors import AppError
from .settings import MAX_FACTOR, EnhanceSettings

STANDARD_FACTORS = (16, 8, 4, 2, 1)


@dataclass
class ScalePlan:
    src_w: int
    src_h: int
    out_w: int
    out_h: int
    factor: float                    # largest per-axis factor
    passes: int                      # AI passes (0 for a plain resize)
    stage_inputs: List[Tuple[int, int]] = field(default_factory=list)
    megapixels: float = 0.0
    est_memory_mb: int = 0
    est_png_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_target(src_w: int, src_h: int, s: EnhanceSettings) -> Tuple[int, int]:
    if s.scale_mode == "factor":
        f = s.factor
        return max(1, round(src_w * f)), max(1, round(src_h * f))
    if s.scale_mode == "percent":
        f = s.percent / 100.0
        return max(1, round(src_w * f)), max(1, round(src_h * f))
    w, h = s.width, s.height
    if w is None and h is None:
        raise AppError("invalid_scale", "Enter a width or a height for custom dimensions.")
    if w is None:
        w = max(1, round(h * src_w / src_h))
    if h is None:
        h = max(1, round(w * src_h / src_w))
    return int(w), int(h)


def estimate_file_bytes(pixels: int, fmt: str = "png", quality: int = 90) -> int:
    """Rough size estimate for photographic content (shown as 'approx.')."""
    q = min(100, max(1, quality)) / 100.0
    if fmt == "png":
        per_px = 1.5
    elif fmt in ("jpg", "jpeg"):
        per_px = 0.05 + 0.55 * q ** 4
    else:
        per_px = 0.03 + 0.35 * q ** 4
    return int(pixels * per_px)


def max_supported_factor(src_w: int, src_h: int, max_pixels: int, max_side: int) -> float:
    by_pixels = math.sqrt(max_pixels / (src_w * src_h))
    by_side = max_side / max(src_w, src_h)
    return min(MAX_FACTOR, by_pixels, by_side)


def build_plan(src_w: int, src_h: int, s: EnhanceSettings, model_scale: int,
               max_pixels: int, max_side: int) -> ScalePlan:
    """model_scale: native scale of the AI model, or 0 for a non-AI resize."""
    out_w, out_h = resolve_target(src_w, src_h, s)
    factor = max(out_w / src_w, out_h / src_h)
    limit = max_supported_factor(src_w, src_h, max_pixels, max_side)
    suggestion = next((f for f in STANDARD_FACTORS if f <= limit + 1e-9), None)
    details = {
        "requested": {"width": out_w, "height": out_h},
        "max_factor": round(limit, 2),
        "suggested_factor": suggestion,
        "suggested": ({"width": src_w * suggestion, "height": src_h * suggestion}
                      if suggestion else None),
    }
    hint = (f" The largest supported standard size for this image is {suggestion}x "
            f"({src_w * suggestion}x{src_h * suggestion})." if suggestion else "")
    if factor > MAX_FACTOR + 1e-6:
        raise AppError("invalid_scale",
                       f"The requested size is {factor:.1f}x the original; the maximum is "
                       f"{MAX_FACTOR:g}x." + hint, details=details)
    if out_w > max_side or out_h > max_side:
        raise AppError("output_too_large",
                       f"The requested output ({out_w}x{out_h}) exceeds the {max_side}px "
                       f"per-side limit." + hint, details=details)
    if out_w * out_h > max_pixels:
        raise AppError("output_too_large",
                       f"The requested output ({out_w}x{out_h}, {out_w * out_h / 1e6:.0f} MP) "
                       f"exceeds the {max_pixels / 1e6:.0f} MP limit configured for this "
                       f"machine." + hint, details=details)
    if min(out_w, out_h) < 8:
        raise AppError("invalid_scale", "The requested output is too small.", details=details)

    passes, stages = 0, []
    if model_scale and model_scale > 1:
        passes = 1 if factor <= model_scale else math.ceil(
            math.log(factor) / math.log(model_scale) - 1e-9)
        # Pass 1 always sees the untouched source. Later passes get the previous
        # AI output resized so the final pass lands on the requested size.
        stages.append((src_w, src_h))
        for k in range(2, passes + 1):
            remaining = model_scale ** (passes - k + 1)
            stages.append((math.ceil(out_w / remaining), math.ceil(out_h / remaining)))
    pixels = out_w * out_h
    return ScalePlan(
        src_w=src_w, src_h=src_h, out_w=out_w, out_h=out_h, factor=round(factor, 4),
        passes=passes, stage_inputs=stages, megapixels=round(pixels / 1e6, 2),
        est_memory_mb=int(pixels * 3 * 3 / 1e6) + 300,
        est_png_bytes=estimate_file_bytes(pixels, "png"))
