"""Face detection (YuNet via OpenCV) and face restoration (GFPGAN / CodeFormer).

Faces are aligned to the 512px FFHQ template using the detector's five
landmarks, restored, blended with the untouched crop according to `strength`
and pasted back through a feathered mask so no box edge is visible."""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable, List, Optional

import cv2
import numpy as np

from .device import get_torch
from .registry import ModelSpec

log = logging.getLogger("enhancer.face")
FACE_SIZE = 512
TEMPLATE = np.array([[192.98138, 239.94708], [318.90277, 240.1936], [256.63416, 314.01935],
                     [201.26117, 371.41043], [313.08905, 371.15118]], dtype=np.float32)
_extra_installed = False


def _feather_mask(size: int = FACE_SIZE) -> np.ndarray:
    mask = np.zeros((size, size), np.float32)
    inset = int(size * 0.1)
    mask[inset:-inset, inset:-inset] = 1.0
    k = int(size * 0.08) * 2 + 1
    return cv2.GaussianBlur(mask, (k, k), 0)


class FaceDetector:
    def __init__(self, model_path: Path, max_side: int = 1280, score: float = 0.6):
        self.max_side = max_side
        self.net = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), score, 0.3, 200)

    def detect(self, rgb: np.ndarray) -> List[dict]:
        h, w = rgb.shape[:2]
        k = min(1.0, self.max_side / max(h, w))
        small = rgb if k == 1.0 else cv2.resize(rgb, (max(1, round(w * k)), max(1, round(h * k))),
                                                interpolation=cv2.INTER_AREA)
        bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        self.net.setInputSize((bgr.shape[1], bgr.shape[0]))
        _, found = self.net.detect(bgr)
        faces = []
        for row in (found if found is not None else []):
            x, y, bw, bh = (float(v) / k for v in row[:4])
            if min(bw, bh) * k < 20:
                continue
            landmarks = (np.asarray(row[4:14], dtype=np.float32).reshape(5, 2) / k)
            faces.append({"box": [x, y, bw, bh], "landmarks": landmarks.tolist(),
                          "score": float(row[14])})
        faces.sort(key=lambda f: -f["score"])
        return faces


class FaceRestorer:
    kind = "face"

    def __init__(self, spec: ModelSpec, models_dir: Path, fidelity: float = 0.7):
        self.spec = spec
        self.models_dir = Path(models_dir)
        self.fidelity = fidelity
        self.device = "cpu"
        self.desc = None
        self._mask = _feather_mask()

    def load(self) -> None:
        global _extra_installed
        from spandrel import MAIN_REGISTRY, ModelLoader
        if self.spec.requires_extra and not _extra_installed:
            import spandrel_extra_arches
            if hasattr(spandrel_extra_arches, "install"):
                spandrel_extra_arches.install()
            else:
                MAIN_REGISTRY.add(*spandrel_extra_arches.EXTRA_REGISTRY)
            _extra_installed = True
        self.desc = ModelLoader().load_from_file(str(self.spec.path(self.models_dir)))
        net = self.desc.model.eval()
        for p in net.parameters():
            p.requires_grad_(False)

    def to(self, device: str, half: bool = False) -> None:
        # StyleGAN-based face models are run in FP32: FP16 is not reliable for them.
        self.device = device
        self.desc.model.to(device).float()

    def to_cpu(self) -> None:
        self.to("cpu")

    def unload(self) -> None:
        self.desc = None

    def _forward(self, t):
        net = self.desc.model
        if self.spec.id == "codeformer":
            try:
                return net(t, weight=self.fidelity)
            except TypeError:
                return net(t, w=self.fidelity, adain=True)
        return net(t)

    def _infer(self, crop: np.ndarray) -> np.ndarray:
        torch = get_torch()
        t = torch.from_numpy(np.ascontiguousarray(crop)).to(self.device)
        t = t.permute(2, 0, 1).unsqueeze(0).float().div_(255.0).sub_(0.5).div_(0.5)
        with torch.inference_mode():
            out = self._forward(t)
            if isinstance(out, (tuple, list)):
                out = out[0]
            out = out.float().clamp_(-1, 1).add_(1.0).mul_(127.5).round_().to(torch.uint8)
            return out.squeeze(0).permute(1, 2, 0).contiguous().cpu().numpy()

    def restore(self, img: np.ndarray, faces: List[dict], strength: float,
                progress: Optional[Callable[[float], None]] = None) -> int:
        """Restore `faces` inside `img` in place. Returns the number restored."""
        h, w = img.shape[:2]
        done = 0
        for i, face in enumerate(faces):
            landmarks = np.asarray(face["landmarks"], dtype=np.float32)
            matrix, _ = cv2.estimateAffinePartial2D(landmarks, TEMPLATE, method=cv2.LMEDS)
            if matrix is not None:
                crop = cv2.warpAffine(img, matrix, (FACE_SIZE, FACE_SIZE),
                                      flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
                restored = self._infer(crop)
                if restored.shape[:2] != (FACE_SIZE, FACE_SIZE):
                    restored = cv2.resize(restored, (FACE_SIZE, FACE_SIZE),
                                          interpolation=cv2.INTER_AREA)
                mixed = cv2.addWeighted(restored, strength, crop, 1.0 - strength, 0)
                inverse = cv2.invertAffineTransform(matrix)
                corners = cv2.transform(
                    np.array([[[0, 0], [FACE_SIZE, 0], [FACE_SIZE, FACE_SIZE], [0, FACE_SIZE]]],
                             dtype=np.float32), inverse)[0]
                x0 = max(0, math.floor(corners[:, 0].min()))
                y0 = max(0, math.floor(corners[:, 1].min()))
                x1 = min(w, math.ceil(corners[:, 0].max()))
                y1 = min(h, math.ceil(corners[:, 1].max()))
                if x1 > x0 and y1 > y0:
                    inverse[0, 2] -= x0
                    inverse[1, 2] -= y0
                    size = (x1 - x0, y1 - y0)
                    warped = cv2.warpAffine(mixed, inverse, size, flags=cv2.INTER_CUBIC)
                    mask = cv2.warpAffine(self._mask, inverse, size,
                                          flags=cv2.INTER_LINEAR)[:, :, None]
                    roi = img[y0:y1, x0:x1].astype(np.float32)
                    out = warped.astype(np.float32) * mask + roi * (1.0 - mask)
                    img[y0:y1, x0:x1] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
                    done += 1
            if progress:
                progress((i + 1) / len(faces))
        return done
