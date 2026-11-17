"""Safe decoding of uploads and encoding of results.

Images are handled internally as uint8 RGB numpy arrays (plus an optional
separate alpha plane). Uploads are decoded with Pillow, never executed or
trusted by extension or declared MIME type."""
from __future__ import annotations

import io
import re
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..errors import AppError

ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "TIFF": "tiff"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/x-tiff",
                "application/octet-stream", ""}
MIN_SIDE = 16
WEBP_MAX_SIDE = 16383
JPEG_MAX_SIDE = 65535


def safe_display_name(name: Optional[str]) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^\w.\- ()]", "_", base, flags=re.UNICODE).strip(" .")
    return base[:120] or "image"


def decode_upload(data: bytes, max_pixels: int,
                  declared_mime: Optional[str] = None) -> Tuple[np.ndarray, Optional[np.ndarray], dict]:
    """Validate and decode an uploaded file -> (rgb, alpha or None, info)."""
    if declared_mime is not None and declared_mime.lower() not in ALLOWED_MIME:
        raise AppError("unsupported_format",
                       "Unsupported file format. Use JPG, PNG, WebP or TIFF.")
    Image.MAX_IMAGE_PIXELS = max(max_pixels, 1) * 2
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            if fmt not in ALLOWED_FORMATS:
                raise AppError("unsupported_format",
                               "Unsupported file format. Use JPG, PNG, WebP or TIFF.")
            if width * height > max_pixels:
                raise AppError(
                    "image_too_large",
                    f"Image is too large ({width}x{height}). The limit is "
                    f"{max_pixels / 1e6:.0f} megapixels.")
            if min(width, height) < MIN_SIDE:
                raise AppError("image_too_small",
                               f"Image is too small ({width}x{height}). Minimum side is {MIN_SIDE}px.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.seek(0)
            img = ImageOps.exif_transpose(img)
            if img.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
                arr = np.asarray(img, dtype=np.float32)
                peak = float(arr.max()) or 1.0
                div = 257.0 if peak > 255 else 1.0
                img = Image.fromarray(np.clip(arr / div, 0, 255).astype(np.uint8), "L")
            has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
            img = img.convert("RGBA" if has_alpha else "RGB")
            arr = np.asarray(img)
    except AppError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError,
            SyntaxError, EOFError, MemoryError):
        raise AppError("invalid_image", "The file is not a valid or readable image.")

    rgb = np.ascontiguousarray(arr[:, :, :3])
    alpha = None
    if has_alpha:
        alpha = np.ascontiguousarray(arr[:, :, 3])
        if int(alpha.min()) == 255:   # fully opaque: drop it
            alpha = None
    info = {"format": ALLOWED_FORMATS[fmt], "width": int(rgb.shape[1]),
            "height": int(rgb.shape[0]), "has_alpha": alpha is not None}
    return rgb, alpha, info


def encode_png(rgb: np.ndarray, alpha: Optional[np.ndarray] = None, compression: int = 2) -> bytes:
    if alpha is not None:
        arr = cv2.cvtColor(np.dstack([rgb, alpha]), cv2.COLOR_RGBA2BGRA)
    else:
        arr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".png", arr, [cv2.IMWRITE_PNG_COMPRESSION, compression])
    if not ok:
        raise AppError("processing_failed", "Could not encode the image.", status=500)
    return buf.tobytes()


def decode_png(data: bytes) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise AppError("processing_failed", "Stored image could not be read.", status=500)
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB), None
    if arr.shape[2] == 4:
        rgba = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)
        return np.ascontiguousarray(rgba[:, :, :3]), np.ascontiguousarray(rgba[:, :, 3])
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB), None


def png_dimensions(data: bytes) -> Tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        return img.size


def make_preview(rgb: np.ndarray, alpha: Optional[np.ndarray] = None, max_side: int = 4096,
                 quality: int = 88) -> bytes:
    """Small WebP of a result for the comparison view (fast over slow connections)."""
    h, w = rgb.shape[:2]
    k = min(1.0, max_side / max(h, w))
    if k < 1.0:
        size = (max(1, round(w * k)), max(1, round(h * k)))
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(alpha, size, interpolation=cv2.INTER_AREA) if alpha is not None else None
    img = Image.fromarray(np.dstack([rgb, alpha]) if alpha is not None else rgb,
                          "RGBA" if alpha is not None else "RGB")
    out = io.BytesIO()
    img.save(out, "WEBP", quality=quality, method=3)
    return out.getvalue()


def convert_png(data: bytes, fmt: str, quality: int = 90) -> Tuple[bytes, str, str]:
    """Convert a stored PNG result to the requested download format.
    Returns (bytes, extension, mime)."""
    fmt = fmt.lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt == "png":
        return data, "png", "image/png"
    if fmt not in ("jpg", "webp"):
        raise AppError("invalid_format", "Download format must be PNG, JPG or WebP.")
    quality = int(min(100, max(1, quality)))
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        limit = JPEG_MAX_SIDE if fmt == "jpg" else WEBP_MAX_SIDE
        if max(img.size) > limit:
            raise AppError(
                "format_limit",
                f"{fmt.upper()} files cannot exceed {limit}px per side; this image is "
                f"{img.size[0]}x{img.size[1]}. Download it as PNG instead.")
        out = io.BytesIO()
        if fmt == "jpg":
            if img.mode == "RGBA":      # JPEG has no alpha: flatten onto white
                flat = Image.new("RGB", img.size, (255, 255, 255))
                flat.paste(img, mask=img.split()[3])
                img = flat
            img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True,
                                    subsampling=0 if quality >= 90 else 2)
            return out.getvalue(), "jpg", "image/jpeg"
        img.save(out, "WEBP", quality=quality, method=4)
        return out.getvalue(), "webp", "image/webp"
