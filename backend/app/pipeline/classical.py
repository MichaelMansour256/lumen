"""Traditional (non-AI) image operations with OpenCV. All functions take and
return uint8 RGB arrays. Point operations are applied through lookup tables so
very large outputs never need a float copy."""
from __future__ import annotations

import cv2
import numpy as np


def _thumb(img: np.ndarray, side: int = 512) -> np.ndarray:
    h, w = img.shape[:2]
    k = side / max(h, w)
    return img if k >= 1 else cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))),
                                         interpolation=cv2.INTER_AREA)


def _apply_tables(img: np.ndarray, tables: np.ndarray) -> np.ndarray:
    """tables: float array (3, 256) in 0..255."""
    lut = np.clip(np.rint(tables), 0, 255).astype(np.uint8).T.reshape(256, 1, 3)
    return cv2.LUT(img, lut)


def resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    if img.shape[1] == w and img.shape[0] == h:
        return img
    shrinking = w < img.shape[1] or h < img.shape[0]
    return cv2.resize(img, (w, h),
                      interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4)


# --- restoration (run on the source, before upscaling) -------------------
def denoise(img: np.ndarray, strength: float) -> np.ndarray:
    """Non-local means denoising."""
    if strength <= 0.02:
        return img
    h = 2.0 + 8.0 * strength
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    out = cv2.fastNlMeansDenoisingColored(bgr, None, h, h, 5, 15)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def reduce_jpeg_artifacts(img: np.ndarray, strength: float) -> np.ndarray:
    """Edge-preserving smoothing of luma blocks plus chroma median filtering."""
    if strength <= 0.02:
        return img
    y, cr, cb = cv2.split(cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb))
    smooth = cv2.bilateralFilter(y, 5, 10 + 30 * strength, 2 + 3 * strength)
    mix = min(1.0, 0.4 + strength)
    y = cv2.addWeighted(smooth, mix, y, 1 - mix, 0)
    k = 3 if strength < 0.5 else 5
    cr, cb = cv2.medianBlur(cr, k), cv2.medianBlur(cb, k)
    return cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2RGB)


def deblur(img: np.ndarray, strength: float) -> np.ndarray:
    """Richardson-Lucy deconvolution of the luma channel with a Gaussian PSF.
    Effective for mild defocus / soft-focus blur, not for strong motion blur."""
    if strength <= 0.02:
        return img
    sigma = 0.6 + 1.6 * strength
    iters = int(6 + 10 * strength)
    ycc = cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb)
    y = ycc[:, :, 0].astype(np.float32) / 255.0 + 1e-3
    est = y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        est *= cv2.GaussianBlur(y / np.maximum(conv, 1e-4), (0, 0), sigma)
    ycc[:, :, 0] = np.clip((est - 1e-3) * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)


# --- colour and tone -----------------------------------------------------
def auto_color(img: np.ndarray, wb_strength: float = 0.7) -> np.ndarray:
    """Damped grey-world white balance followed by a gentle levels stretch."""
    t = _thumb(img).reshape(-1, 3).astype(np.float32)
    means = t.mean(axis=0) + 1e-3
    gains = np.clip(means.mean() / means, 0.75, 1.33)
    gains = 1.0 + (gains - 1.0) * wb_strength
    luma = (t * gains) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    lo, hi = np.percentile(luma, [0.5, 99.5])
    lo, hi = min(float(lo), 40.0), max(float(hi), 200.0)
    x = np.arange(256, dtype=np.float32)
    tables = np.stack([(x * g - lo) * 255.0 / max(hi - lo, 1.0) for g in gains])
    return _apply_tables(img, tables)


def fade_restore(img: np.ndarray) -> np.ndarray:
    """Old-photo fade correction: per-channel black/white point stretch, which
    restores contrast and removes the colour cast of faded prints."""
    t = _thumb(img).reshape(-1, 3)
    x = np.arange(256, dtype=np.float32)
    tables = []
    for c in range(3):
        lo, hi = np.percentile(t[:, c], [1.0, 99.0])
        lo, hi = min(float(lo), 70.0), max(float(hi), 185.0)
        tables.append((x - lo) * 255.0 / max(hi - lo, 1.0))
    return _apply_tables(img, np.stack(tables))


def low_light(img: np.ndarray, strength: float) -> np.ndarray:
    """Gamma lift plus CLAHE on the lightness channel."""
    if strength <= 0.02:
        return img
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    x = np.arange(256, dtype=np.float32) / 255.0
    gamma = 1.0 / (1.0 + 1.2 * strength)
    lightness = cv2.LUT(lab[:, :, 0], np.clip(np.rint(x ** gamma * 255), 0, 255).astype(np.uint8))
    clahe = cv2.createCLAHE(clipLimit=1.0 + 2.0 * strength, tileGridSize=(8, 8))
    lab[:, :, 0] = cv2.addWeighted(clahe.apply(lightness), 0.5, lightness, 0.5, 0)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def color_adjust(img: np.ndarray, exposure: float = 0.0, brightness: float = 0.0,
                 contrast: float = 0.0, temperature: float = 0.0,
                 saturation: float = 0.0) -> np.ndarray:
    """All inputs are in -1..1; 0 leaves the image untouched."""
    if any(abs(v) > 1e-3 for v in (exposure, brightness, contrast, temperature)):
        x = np.arange(256, dtype=np.float32) / 255.0
        gains = (1.0 + 0.18 * temperature, 1.0, 1.0 - 0.18 * temperature)
        tables = []
        for g in gains:
            v = x * g * (2.0 ** (exposure * 1.5)) + brightness * 0.25
            v = (v - 0.5) * (1.0 + contrast * 0.8) + 0.5
            tables.append(v * 255.0)
        img = _apply_tables(img, np.stack(tables))
    if abs(saturation) > 1e-3:
        f = 1.0 + saturation
        gray = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
        img = cv2.addWeighted(img, f, gray, 1.0 - f, 0)
    return img


# --- detail (run on the final-size image) --------------------------------
def enhance_detail(img: np.ndarray, strength: float, strip: int = 1024) -> np.ndarray:
    """Texture boost: amplifies fine detail (pores, hair, fabric) and, more gently, the
    next-coarser band. Radii follow image size so the effect looks alike at any output
    size. Processed in horizontal strips so large outputs need little extra memory."""
    if strength <= 0.02:
        return img
    short = min(img.shape[:2])
    s1 = max(0.8, short / 2400.0)           # fine band (about 2 px on a 4.9k image)
    s2 = s1 * 3.0                           # medium band
    fine_amt, mid_amt = 1.6 * strength, 0.8 * strength
    pad = int(np.ceil(s2 * 4)) + 2
    out = np.empty_like(img)
    h = img.shape[0]
    for y0 in range(0, h, strip):
        y1 = min(h, y0 + strip)
        a0, a1 = max(0, y0 - pad), min(h, y1 + pad)
        part = img[a0:a1].astype(np.float32)
        b1 = cv2.GaussianBlur(part, (0, 0), s1)
        b2 = cv2.GaussianBlur(part, (0, 0), s2)
        res = part + fine_amt * (part - b1) + mid_amt * (b1 - b2)
        out[y0:y1] = np.clip(res[y0 - a0:y0 - a0 + (y1 - y0)], 0, 255).astype(np.uint8)
    return out


def sharpen(img: np.ndarray, strength: float) -> np.ndarray:
    """Unsharp mask at a fine radius."""
    if strength <= 0.02:
        return img
    sigma = max(0.8, min(img.shape[:2]) / 1500.0)
    amount = 1.2 * strength
    return cv2.addWeighted(img, 1 + amount, cv2.GaussianBlur(img, (0, 0), sigma), -amount, 0)


def blend(base: np.ndarray, enhanced: np.ndarray, intensity: float) -> np.ndarray:
    if intensity >= 0.999:
        return enhanced
    return cv2.addWeighted(enhanced, intensity, base, 1.0 - intensity, 0)
