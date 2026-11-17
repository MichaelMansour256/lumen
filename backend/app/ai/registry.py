"""Model registry: the only place model files, sources and licences are declared.
Weights are downloaded exclusively from the official release URLs listed here."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    kind: str                 # "upscaler" | "face" | "detector"
    filename: str
    url: str
    size_mb: float            # approximate download size, used as a sanity check
    license: str
    source: str
    description: str
    scale: int = 1
    default_tile: int = 256   # tile edge on a ~4 GB GPU; halved automatically when VRAM is low
    vram_mb: int = 0          # rough peak VRAM at the default tile size
    companion: Optional[str] = None      # optional extra weight file id
    requires_extra: bool = False         # needs the spandrel_extra_arches package
    recommended: bool = True             # downloaded by the default setup
    notes: str = ""

    def path(self, models_dir: Path) -> Path:
        return Path(models_dir) / self.filename


_GH = "https://github.com"
SPECS = [
    ModelSpec(
        id="realesr-general", name="Real-ESRGAN General v3 (fast)", kind="upscaler", scale=4,
        filename="realesr-general-x4v3.pth",
        url=f"{_GH}/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
        size_mb=4.7, license="BSD-3-Clause", source=f"{_GH}/xinntao/Real-ESRGAN",
        description="Compact general-purpose 4x model. Fast and light on VRAM; "
                    "supports adjustable denoising.",
        default_tile=512, vram_mb=1200, companion="realesr-general-wdn"),
    ModelSpec(
        id="realesr-general-wdn", name="Real-ESRGAN General v3 (weak-denoise weights)",
        kind="companion", scale=4, filename="realesr-general-wdn-x4v3.pth",
        url=f"{_GH}/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-wdn-x4v3.pth",
        size_mb=4.7, license="BSD-3-Clause", source=f"{_GH}/xinntao/Real-ESRGAN",
        description="Blended with the general model to control denoising strength."),
    ModelSpec(
        id="realesrgan-x4plus", name="Real-ESRGAN x4plus (quality)", kind="upscaler", scale=4,
        filename="RealESRGAN_x4plus.pth",
        url=f"{_GH}/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        size_mb=64, license="BSD-3-Clause", source=f"{_GH}/xinntao/Real-ESRGAN",
        description="Larger RRDB model. Slower, usually the best texture on photos.",
        default_tile=256, vram_mb=2400),
    ModelSpec(
        id="realesrgan-anime", name="Real-ESRGAN x4plus Anime 6B", kind="upscaler", scale=4,
        filename="RealESRGAN_x4plus_anime_6B.pth",
        url=f"{_GH}/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        size_mb=17, license="BSD-3-Clause", source=f"{_GH}/xinntao/Real-ESRGAN",
        description="For anime, illustrations and line art; keeps edges clean.",
        default_tile=384, vram_mb=1800),
    ModelSpec(
        id="swinir-real", name="SwinIR-M x4 real-world (slow)", kind="upscaler", scale=4,
        filename="003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth",
        url=f"{_GH}/JingyunLiang/SwinIR/releases/download/v0.0/"
            "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth",
        size_mb=64, license="Apache-2.0", source=f"{_GH}/JingyunLiang/SwinIR",
        description="Transformer restoration model. Much slower on a 4 GB GPU; optional.",
        default_tile=192, vram_mb=3000, recommended=False),
    ModelSpec(
        id="gfpgan", name="GFPGAN v1.4", kind="face", filename="GFPGANv1.4.pth",
        url=f"{_GH}/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
        size_mb=332, license="Apache-2.0", source=f"{_GH}/TencentARC/GFPGAN",
        description="Face restoration. Natural results with strength control.", vram_mb=2000),
    ModelSpec(
        id="codeformer", name="CodeFormer", kind="face", filename="codeformer.pth",
        url=f"{_GH}/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
        size_mb=360, license="S-Lab License 1.0 (non-commercial use only)",
        source=f"{_GH}/sczhou/CodeFormer",
        description="Alternative face restoration for heavily degraded faces.",
        vram_mb=2200, requires_extra=True, recommended=False,
        notes="Needs `pip install spandrel_extra_arches`. Non-commercial licence."),
    ModelSpec(
        id="yunet", name="YuNet face detector", kind="detector",
        filename="face_detection_yunet_2023mar.onnx",
        url=f"{_GH}/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
            "face_detection_yunet_2023mar.onnx",
        size_mb=0.23, license="MIT", source=f"{_GH}/opencv/opencv_zoo",
        description="Lightweight face and landmark detector (runs on CPU via OpenCV)."),
]
BY_ID = {s.id: s for s in SPECS}
LANCZOS_ID = "lanczos"


def get_spec(model_id: str) -> Optional[ModelSpec]:
    return BY_ID.get(model_id)
