"""Manual mode presets and the automatic recommendation built from analysis."""
from __future__ import annotations

from typing import Callable, Optional

# Preferred upscalers per kind of content, best first.
MODEL_PREFERENCE = {
    "illustration": ("realesrgan-anime", "realesr-general", "realesrgan-x4plus"),
    "default": ("realesr-general", "realesrgan-x4plus", "swinir-real"),
}

PRESETS = {
    "photo": {"label": "Photo", "description": "General photographs.",
              "settings": {"model": "realesr-general", "face_restore": False, "denoise": 0.25,
                           "detail": 0.15, "sharpness": 0.1}},
    "portrait": {"label": "Portrait", "description": "People: upscaling plus face restoration.",
                 "settings": {"model": "realesr-general", "face_restore": True,
                              "face_strength": 0.6, "denoise": 0.3, "sharpness": 0.05}},
    "product": {"label": "Product", "description": "Crisp edges and clean colour for product shots.",
                "settings": {"model": "realesrgan-x4plus", "face_restore": False, "denoise": 0.2,
                             "detail": 0.25, "sharpness": 0.25, "auto_color": True}},
    "landscape": {"label": "Landscape", "description": "Texture-rich scenes; adds local contrast.",
                  "settings": {"model": "realesrgan-x4plus", "face_restore": False, "denoise": 0.15,
                               "detail": 0.35, "sharpness": 0.15, "saturation": 0.1}},
    "illustration": {"label": "Illustration", "description": "Digital art and drawings.",
                     "settings": {"model": "realesrgan-anime", "face_restore": False,
                                  "denoise": 0.2, "sharpness": 0.1}},
    "anime": {"label": "Anime", "description": "Anime and cel-shaded art (line-preserving model).",
              "settings": {"model": "realesrgan-anime", "face_restore": False, "denoise": 0.3}},
    "old_photo": {"label": "Old photo", "description": "Faded, noisy scans: fade correction, "
                                                       "denoising and face restoration.",
                  "settings": {"model": "realesr-general", "face_restore": True,
                               "face_strength": 0.7, "denoise": 0.6, "jpeg_artifacts": 0.3,
                               "fade_restore": True}},
    "low_light": {"label": "Low light", "description": "Brightens dark photos and reduces noise.",
                  "settings": {"model": "realesr-general", "face_restore": False, "denoise": 0.55,
                               "low_light": 0.6}},
}


def pick_model(category: str, is_available: Callable[[str], bool]) -> Optional[str]:
    order = MODEL_PREFERENCE.get(category, MODEL_PREFERENCE["default"])
    for model_id in order + MODEL_PREFERENCE["default"]:
        if is_available(model_id):
            return model_id
    return None


def recommend(analysis: dict, is_available: Callable[[str], bool],
              face_available: bool) -> dict:
    """Return {"settings": patch, "reasons": [...], "model_available": bool}."""
    m = analysis["metrics"]
    issues = {i["id"]: i for i in analysis["issues"]}
    category = analysis["category"]
    reasons = []
    model = pick_model(category, is_available)
    patch = {"model": model or "auto", "face_restore": False, "face_strength": 0.6,
             "denoise": 0.25, "jpeg_artifacts": 0.0, "deblur": 0.0, "detail": 0.15,
             "sharpness": 0.1, "auto_color": False, "fade_restore": False, "low_light": 0.0}

    if category == "illustration":
        reasons.append("Flat colours detected: using the line-preserving illustration model.")
        patch.update(detail=0.0, sharpness=0.05)
    else:
        reasons.append(f"{analysis['category_label']}: using the general photo model.")

    faces = analysis.get("faces")
    if faces and category != "illustration":
        if face_available:
            strength = 0.65 if analysis["largest_face_fraction"] < 0.05 or "blurry" in issues else 0.45
            patch.update(face_restore=True, face_strength=strength)
            reasons.append(f"{faces} face{'s' if faces != 1 else ''} detected: face restoration on.")
        else:
            reasons.append(f"{faces} face{'s' if faces != 1 else ''} detected, but no face "
                           "restoration model is installed.")
    if "noise" in issues:
        patch["denoise"] = 0.7 if issues["noise"]["severity"] == "high" else 0.5
        reasons.append(f"Noise level {m['noise_sigma']:.1f}: stronger denoising.")
    if "jpeg" in issues:
        patch["jpeg_artifacts"] = 0.6 if issues["jpeg"]["severity"] == "high" else 0.35
        reasons.append("JPEG blocking found: artifact reduction on.")
    if "blurry" in issues and category != "illustration":
        patch["deblur"] = 0.35
        patch["sharpness"] = 0.2
        reasons.append("Image is soft: mild deblurring and sharpening.")
    if "low_light" in issues:
        patch["low_light"] = 0.5
        reasons.append("Dark exposure: low-light enhancement on.")
    if ("low_contrast" in issues or "color_cast" in issues) and category != "illustration":
        patch["auto_color"] = True
        reasons.append("Low contrast or colour cast: automatic colour correction on.")
    if model is None:
        reasons.append("No AI upscaling model is installed yet - run the model download step.")
    return {"settings": patch, "reasons": reasons, "model_available": model is not None}
