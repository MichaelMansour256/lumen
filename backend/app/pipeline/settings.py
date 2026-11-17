"""Enhancement settings: the single source of truth for validation.
Every field maps to a real processing parameter (see pipeline/enhance.py)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Optional

from ..errors import AppError

SCALE_MODES = ("factor", "percent", "dimensions")
FACE_MODELS = ("gfpgan", "codeformer")
UNIT = ("face_strength", "denoise", "jpeg_artifacts", "deblur", "detail", "sharpness",
        "low_light", "intensity")
SIGNED = ("exposure", "brightness", "contrast", "saturation", "temperature")
BOOLS = ("auto", "face_restore", "auto_color", "fade_restore")
MAX_FACTOR = 16.0


@dataclass
class EnhanceSettings:
    auto: bool = True               # let the analyser choose model + corrections
    scale_mode: str = "factor"
    factor: float = 2.0
    percent: float = 200.0
    width: Optional[int] = None
    height: Optional[int] = None
    model: str = "auto"             # "auto", a registry id, or "lanczos" (non-AI resize)
    face_restore: bool = False
    face_model: str = "gfpgan"
    face_strength: float = 0.6
    denoise: float = 0.25
    jpeg_artifacts: float = 0.0
    deblur: float = 0.0
    detail: float = 0.0
    sharpness: float = 0.0
    auto_color: bool = False
    fade_restore: bool = False
    low_light: float = 0.0
    exposure: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    temperature: float = 0.0
    intensity: float = 1.0
    device: str = "auto"            # "auto" or "cpu"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "EnhanceSettings":
        if not isinstance(data, dict):
            raise AppError("invalid_settings", "Settings must be an object.")
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise AppError("invalid_settings", f"Unknown setting: {sorted(unknown)[0]}.")
        s = cls()

        def number(name: str, lo: float, hi: float) -> float:
            value = data[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AppError("invalid_settings", f"'{name}' must be a number.")
            if value != value or not (lo <= value <= hi):
                raise AppError("invalid_settings", f"'{name}' must be between {lo:g} and {hi:g}.")
            return float(value)

        for name in BOOLS:
            if name in data:
                if not isinstance(data[name], bool):
                    raise AppError("invalid_settings", f"'{name}' must be true or false.")
                setattr(s, name, data[name])
        for name in UNIT:
            if name in data:
                setattr(s, name, number(name, 0.0, 1.0))
        for name in SIGNED:
            if name in data:
                setattr(s, name, number(name, -1.0, 1.0))
        if "scale_mode" in data:
            if data["scale_mode"] not in SCALE_MODES:
                raise AppError("invalid_scale", "Invalid scaling mode.")
            s.scale_mode = data["scale_mode"]
        if "factor" in data:
            s.factor = number("factor", 0.1, MAX_FACTOR)
        if "percent" in data:
            s.percent = number("percent", 10.0, MAX_FACTOR * 100)
        for name in ("width", "height"):
            if data.get(name) is not None:
                setattr(s, name, int(number(name, 1, 100_000)))
        if s.scale_mode == "dimensions" and s.width is None and s.height is None:
            raise AppError("invalid_scale", "Enter a width or a height for custom dimensions.")
        for name in ("model", "face_model", "device"):
            if name in data:
                if not isinstance(data[name], str) or len(data[name]) > 64:
                    raise AppError("invalid_settings", f"'{name}' is invalid.")
                setattr(s, name, data[name])
        if s.face_model not in FACE_MODELS:
            raise AppError("invalid_settings", "Unknown face restoration model.")
        if s.device not in ("auto", "cpu"):
            raise AppError("invalid_settings", "'device' must be 'auto' or 'cpu'.")
        return s
