"""Automatic image analysis.

Everything reported here is measured with a documented heuristic. The category
is an estimate from those measurements (plus real face detection when the
detector model is installed); the analyser does not recognise scene content
such as landscapes or specific objects and never claims to."""
from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np


def _center_crop(img: np.ndarray, side: int = 1024) -> np.ndarray:
    h, w = img.shape[:2]
    ch, cw = min(h, side), min(w, side)
    y, x = (h - ch) // 2, (w - cw) // 2
    return img[y:y + ch, x:x + cw]


def _noise_sigma(gray: np.ndarray) -> float:
    """Immerkaer's estimator, restricted to the flatter half of the image so
    texture is not mistaken for noise."""
    g = gray.astype(np.float32)
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
    resp = np.abs(cv2.filter2D(g, -1, kernel))
    grad = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    flat = grad <= np.median(grad)
    if not flat.any():
        return 0.0
    return float(np.sqrt(np.pi / 2.0) * resp[flat].mean() / 6.0)


def _blockiness(gray: np.ndarray) -> float:
    """Ratio of gradient energy on the 8x8 JPEG grid to energy elsewhere."""
    g = gray.astype(np.float32)
    if min(g.shape) < 32:
        return 1.0
    dx = np.abs(np.diff(g, axis=1)).mean(axis=0)
    dy = np.abs(np.diff(g, axis=0)).mean(axis=1)
    ratios = []
    for d in (dx, dy):
        idx = np.arange(d.size)
        on = d[idx % 8 == 7]
        off = d[idx % 8 != 7]
        if on.size and off.size:
            ratios.append(float(on.mean() / (off.mean() + 1e-3)))
    return float(np.mean(ratios)) if ratios else 1.0


def analyze_image(rgb: np.ndarray,
                  detect_faces: Optional[Callable[[np.ndarray], Optional[list]]] = None) -> dict:
    h, w = rgb.shape[:2]
    crop = _center_crop(rgb)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    k = 512 / max(h, w)
    thumb = rgb if k >= 1 else cv2.resize(rgb, (max(1, int(w * k)), max(1, int(h * k))),
                                           interpolation=cv2.INTER_AREA)
    tgray = cv2.cvtColor(thumb, cv2.COLOR_RGB2GRAY)

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    noise = _noise_sigma(gray)
    blockiness = _blockiness(gray)
    p5, p50, p95 = (float(v) for v in np.percentile(tgray, [5, 50, 95]))
    lab = cv2.cvtColor(thumb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    cast = float(np.hypot(lab[:, 1].mean() - 128.0, lab[:, 2].mean() - 128.0))
    t16 = thumb.astype(np.int16)
    chan_spread = float(np.abs(t16.max(axis=2) - t16.min(axis=2)).mean())
    saturation = float(cv2.cvtColor(thumb, cv2.COLOR_RGB2HSV)[:, :, 1].mean())

    # Flat-colour test: share of pixels covered by the 16 most common colours
    # after quantising to 4 bits per channel.
    q = (thumb >> 4).reshape(-1, 3).astype(np.int32)
    codes = (q[:, 0] << 8) | (q[:, 1] << 4) | q[:, 2]
    counts = np.sort(np.bincount(codes, minlength=4096))[::-1]
    top16 = float(counts[:16].sum() / codes.size)

    # Plain bright border test (studio / product style background).
    b = max(2, int(min(thumb.shape[:2]) * 0.06))
    border = np.concatenate([tgray[:b].ravel(), tgray[-b:].ravel(),
                             tgray[:, :b].ravel(), tgray[:, -b:].ravel()])
    plain_border = bool(border.std() < 12 and border.mean() > 200 and tgray.std() > 25)

    faces = detect_faces(rgb) if detect_faces else None
    face_count = len(faces) if faces is not None else None
    largest_face = 0.0
    if faces:
        largest_face = max(f["box"][2] * f["box"][3] for f in faces) / float(w * h)

    grayscale = chan_spread < 3.0
    issues = []
    if sharpness < 60:
        issues.append({"id": "blurry", "label": "Blurry or very soft", "severity": "high"})
    elif sharpness < 150:
        issues.append({"id": "soft", "label": "Slightly soft", "severity": "low"})
    if noise > 8:
        issues.append({"id": "noise", "label": "Heavy noise", "severity": "high"})
    elif noise > 4:
        issues.append({"id": "noise", "label": "Visible noise", "severity": "medium"})
    if blockiness > 1.6:
        issues.append({"id": "jpeg", "label": "Strong JPEG block artifacts", "severity": "high"})
    elif blockiness > 1.25:
        issues.append({"id": "jpeg", "label": "JPEG block artifacts", "severity": "medium"})
    if p50 < 60 and p95 < 190:
        issues.append({"id": "low_light", "label": "Underexposed / low light", "severity": "medium"})
    if p95 - p5 < 110:
        issues.append({"id": "low_contrast", "label": "Low contrast", "severity": "medium"})
    if not grayscale and cast > 10:
        issues.append({"id": "color_cast", "label": "Possible colour cast", "severity": "low"})
    if max(w, h) < 800:
        issues.append({"id": "low_res", "label": "Low resolution", "severity": "low"})

    if top16 > 0.75 and noise < 3.0:
        category, label = "illustration", "Illustration / flat artwork"
    elif faces and largest_face >= 0.02:
        category, label = "portrait", "Portrait (faces detected)"
    elif plain_border:
        category, label = "product", "Subject on a plain bright background"
    else:
        category, label = "photo", "Photograph"

    return {
        "width": w, "height": h, "megapixels": round(w * h / 1e6, 2),
        "category": category, "category_label": label,
        "category_note": "Estimated from colour statistics and face detection.",
        "grayscale": grayscale,
        "faces": face_count,
        "faces_note": None if faces is not None else "Face detector not installed.",
        "largest_face_fraction": round(largest_face, 4),
        "metrics": {
            "sharpness": round(sharpness, 1), "noise_sigma": round(noise, 2),
            "blockiness": round(blockiness, 3), "brightness_median": round(p50, 1),
            "contrast_range": round(p95 - p5, 1), "color_cast": round(cast, 1),
            "saturation": round(saturation, 1), "flat_color_share": round(top16, 3),
        },
        "issues": issues,
    }
