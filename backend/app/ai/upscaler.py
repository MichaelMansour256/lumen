"""Super-resolution model wrapper (Real-ESRGAN family, SwinIR) built on
spandrel, which reconstructs the architecture from the official weight file
and refuses to unpickle arbitrary code.

Input / output: uint8 RGB numpy arrays; output is exactly `scale` times larger."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..errors import AppError
from .device import empty_cache, free_vram_mb, get_torch, is_oom
from .registry import ModelSpec, get_spec
from .tiling import tiled_apply

log = logging.getLogger("enhancer.upscaler")
MIN_TILE = 64


class _HalfPrecisionFailure(Exception):
    pass


def _raw_state_dict(path: Path) -> dict:
    torch = get_torch()
    data = torch.load(str(path), map_location="cpu", weights_only=True)
    for key in ("params_ema", "params", "state_dict"):
        if isinstance(data, dict) and key in data and isinstance(data[key], dict):
            return data[key]
    return data


class UpscalerModel:
    kind = "upscaler"

    def __init__(self, spec: ModelSpec, models_dir: Path, tile_size: int = 0, tile_pad: int = 16):
        self.spec = spec
        self.scale = spec.scale
        self.models_dir = Path(models_dir)
        self.tile_size = tile_size
        self.tile_pad = tile_pad
        self.device = "cpu"
        self.half = False
        self.desc = None
        self._sd_main: Optional[dict] = None
        self._sd_wdn: Optional[dict] = None
        self._denoise: Optional[float] = None
        self.last_tile = 0

    # -- lifecycle ------------------------------------------------------
    @property
    def supports_denoise(self) -> bool:
        return self._sd_wdn is not None

    def load(self) -> None:
        from spandrel import ModelLoader
        path = self.spec.path(self.models_dir)
        companion = get_spec(self.spec.companion) if self.spec.companion else None
        if companion and companion.path(self.models_dir).is_file():
            self._sd_main = _raw_state_dict(path)
            self._sd_wdn = _raw_state_dict(companion.path(self.models_dir))
            self._build(1.0)
        else:
            self.desc = ModelLoader().load_from_file(str(path))
            self._finish_build()
        if int(self.desc.scale) != self.scale:
            raise RuntimeError(f"{self.spec.filename}: expected a {self.scale}x model, "
                               f"file is {self.desc.scale}x")

    def _build(self, strength: float) -> None:
        """(Re)build the network from blended weights: `strength` of the main
        weights and 1 - strength of the weak-denoise weights (Real-ESRGAN 'dni')."""
        from spandrel import ModelLoader
        blended = {k: strength * v + (1.0 - strength) * self._sd_wdn[k]
                   for k, v in self._sd_main.items()}
        self.desc = ModelLoader().load_from_state_dict(blended)
        self._denoise = strength
        self._finish_build()

    def _finish_build(self) -> None:
        net = self.desc.model.eval()
        for p in net.parameters():
            p.requires_grad_(False)
        self._place()

    def _place(self) -> None:
        net = self.desc.model
        net.to(self.device)
        if self.half:
            net.half()
        else:
            net.float()

    def to(self, device: str, half: bool) -> None:
        self.device = device
        self.half = bool(half and device == "cuda" and getattr(self.desc, "supports_half", True))
        self._place()

    def to_cpu(self) -> None:
        self.to("cpu", False)

    def unload(self) -> None:
        self.desc = None
        self._sd_main = self._sd_wdn = None

    def set_denoise(self, strength: float) -> None:
        if not self.supports_denoise:
            return
        strength = round(float(strength) * 20) / 20
        if self._denoise is None or abs(strength - self._denoise) > 1e-6:
            self._build(strength)

    # -- inference ------------------------------------------------------
    def pick_tile(self) -> int:
        base = self.tile_size or self.spec.default_tile
        if self.device == "cpu":
            return min(base, 256)
        free = free_vram_mb()
        if free is not None:
            if free < 1500:
                base //= 4
            elif free < 2800:
                base //= 2
        return max(MIN_TILE, base)

    def _infer(self, tile: np.ndarray) -> np.ndarray:
        torch = get_torch()
        t = torch.from_numpy(np.ascontiguousarray(tile)).to(self.device)
        t = t.permute(2, 0, 1).unsqueeze(0)
        t = (t.half() if self.half else t.float()).div_(255.0)
        with torch.inference_mode():
            out = self.desc(t)
            if self.half and not bool(torch.isfinite(out).all()):
                raise _HalfPrecisionFailure()
            out = out.float().clamp_(0, 1).mul_(255.0).round_().to(torch.uint8)
            return out.squeeze(0).permute(1, 2, 0).contiguous().cpu().numpy()

    def upscale(self, img: np.ndarray,
                progress: Optional[Callable[[float], None]] = None) -> np.ndarray:
        tile = self.pick_tile()
        while True:
            retry = None
            try:
                self.last_tile = tile
                return tiled_apply(img, self._infer, self.scale, tile, self.tile_pad, progress)
            except _HalfPrecisionFailure:
                retry = "fp32"
            except Exception as exc:
                if not is_oom(exc):
                    raise
                retry = "oom"
            empty_cache()
            if retry == "fp32":
                log.warning("%s produced NaN in FP16; switching to FP32", self.spec.id)
                self.half = False
                self._place()
                continue
            if tile <= MIN_TILE:
                where = "GPU" if self.device == "cuda" else "system"
                raise AppError(
                    "gpu_oom" if self.device == "cuda" else "out_of_memory",
                    f"Not enough {where} memory for {self.spec.name}, even with the smallest "
                    f"tiles. Close other GPU apps, pick the fast model or a smaller size"
                    + (", or retry on CPU." if self.device == "cuda" else "."),
                    status=507, retryable=True)
            tile = max(MIN_TILE, tile // 2)
            log.warning("Out of memory; retrying %s with %dpx tiles", self.spec.id, tile)
