"""Tiled inference helper (numpy only, model-agnostic).

Each tile is processed with `pad` pixels of surrounding context and only the
un-padded centre is written to the output, so neighbouring tiles agree at
their borders and no seams are visible. The output is written straight into
one uint8 buffer - no float accumulators or extra full-size copies."""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np


def tiled_apply(img: np.ndarray, fn: Callable[[np.ndarray], np.ndarray], scale: int,
                tile: int, pad: int = 16,
                progress: Optional[Callable[[float], None]] = None) -> np.ndarray:
    h, w, c = img.shape
    if tile <= 0 or (h <= tile and w <= tile):
        out = fn(img)
        _check(out, h, w, scale)
        if progress:
            progress(1.0)
        return out
    out = np.empty((h * scale, w * scale, c), dtype=np.uint8)
    ys = list(range(0, h, tile))
    xs = list(range(0, w, tile))
    total, done = len(ys) * len(xs), 0
    for y0 in ys:
        y1 = min(y0 + tile, h)
        py0, py1 = max(y0 - pad, 0), min(y1 + pad, h)
        for x0 in xs:
            x1 = min(x0 + tile, w)
            px0, px1 = max(x0 - pad, 0), min(x1 + pad, w)
            res = fn(img[py0:py1, px0:px1])
            _check(res, py1 - py0, px1 - px0, scale)
            oy, ox = (y0 - py0) * scale, (x0 - px0) * scale
            out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = \
                res[oy:oy + (y1 - y0) * scale, ox:ox + (x1 - x0) * scale]
            done += 1
            if progress:
                progress(done / total)
    return out


def _check(res: np.ndarray, h: int, w: int, scale: int) -> None:
    if res.shape[0] != h * scale or res.shape[1] != w * scale:
        raise RuntimeError(
            f"model returned {res.shape[1]}x{res.shape[0]}, expected {w * scale}x{h * scale}")
