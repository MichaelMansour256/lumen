"""Model manager: loads models on demand, keeps at most one on the GPU and a
small number parked in system RAM, and reports what is installed."""
from __future__ import annotations

import importlib
import logging
import threading
from collections import OrderedDict
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..config import Settings
from ..errors import AppError
from .device import device_info, empty_cache, get_torch
from .face import FaceDetector, FaceRestorer
from .registry import LANCZOS_ID, SPECS, ModelSpec, get_spec
from .upscaler import UpscalerModel

log = logging.getLogger("enhancer.models")
RAM_CACHE = 2


class ModelManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self._loaded: "OrderedDict[str, object]" = OrderedDict()
        self._on_gpu: Optional[str] = None
        self._detector: Optional[FaceDetector] = None
        self._import_cache: dict = {}

    # -- availability ---------------------------------------------------
    def _can_import(self, module: str) -> bool:
        if module not in self._import_cache:
            try:
                importlib.import_module(module)
                self._import_cache[module] = True
            except Exception as exc:
                log.warning("Cannot import %s: %s", module, exc)
                self._import_cache[module] = False
        return self._import_cache[module]

    def availability(self, model_id: str) -> Tuple[bool, Optional[str]]:
        if model_id == LANCZOS_ID:
            return True, None
        spec = get_spec(model_id)
        if spec is None or spec.kind not in ("upscaler", "face"):
            return False, "Unknown model."
        if not spec.path(self.settings.models_dir).is_file():
            return False, f"{spec.name} is not downloaded."
        if get_torch() is None:
            return False, "PyTorch is not installed."
        if not self._can_import("spandrel"):
            return False, "The 'spandrel' package is not installed."
        if spec.requires_extra and not self._can_import("spandrel_extra_arches"):
            return False, "The optional 'spandrel_extra_arches' package is not installed."
        return True, None

    def is_available(self, model_id: str) -> bool:
        return self.availability(model_id)[0]

    def face_detection_available(self) -> bool:
        return (hasattr(cv2, "FaceDetectorYN")
                and get_spec("yunet").path(self.settings.models_dir).is_file())

    def device(self, preference: str = "auto") -> dict:
        pref = "cpu" if "cpu" in (preference, self.settings.device) else "auto"
        return device_info(pref, self.settings.fp16)

    def describe(self) -> List[dict]:
        out = []
        for spec in SPECS:
            if spec.kind not in ("upscaler", "face"):
                continue
            ok, reason = self.availability(spec.id)
            out.append({
                "id": spec.id, "name": spec.name, "kind": spec.kind, "scale": spec.scale,
                "description": spec.description, "license": spec.license, "source": spec.source,
                "size_mb": spec.size_mb, "vram_mb": spec.vram_mb, "notes": spec.notes,
                "installed": spec.path(self.settings.models_dir).is_file(),
                "available": ok, "unavailable_reason": reason,
                "loaded": spec.id in self._loaded, "on_gpu": self._on_gpu == spec.id,
            })
        return out

    # -- loading --------------------------------------------------------
    def _require(self, model_id: str) -> ModelSpec:
        ok, reason = self.availability(model_id)
        if not ok:
            raise AppError("model_unavailable",
                           f"AI model unavailable: {reason} Run setup.bat (or "
                           f"backend\\scripts\\download_models.py) and try again.",
                           status=503, retryable=True)
        return get_spec(model_id)

    def _acquire(self, model_id: str, preference: str):
        spec = self._require(model_id)
        info = self.device(preference)
        with self._lock:
            model = self._loaded.get(model_id)
            if model is None:
                while len(self._loaded) >= RAM_CACHE:
                    old_id, old = self._loaded.popitem(last=False)
                    old.unload()
                    if self._on_gpu == old_id:
                        self._on_gpu = None
                    log.info("Unloaded %s", old_id)
                if spec.kind == "upscaler":
                    model = UpscalerModel(spec, self.settings.models_dir,
                                          self.settings.tile_size, self.settings.tile_pad)
                else:
                    model = FaceRestorer(spec, self.settings.models_dir,
                                         self.settings.codeformer_fidelity)
                try:
                    model.load()
                except Exception:
                    log.exception("Failed to load %s", model_id)
                    raise AppError("model_unavailable",
                                   f"{spec.name} could not be loaded. The weight file may be "
                                   f"corrupt - delete it and download it again.",
                                   status=500, retryable=True)
                self._loaded[model_id] = model
                log.info("Loaded %s into RAM", model_id)
            self._loaded.move_to_end(model_id)
            if info["device"] == "cuda":
                if self._on_gpu not in (None, model_id) and self._on_gpu in self._loaded:
                    self._loaded[self._on_gpu].to_cpu()
                    empty_cache()
                model.to("cuda", info["fp16"])
                self._on_gpu = model_id
            else:
                model.to("cpu", False)
                if self._on_gpu == model_id:
                    self._on_gpu = None
                    empty_cache()
            return model

    def get_upscaler(self, model_id: str, preference: str = "auto") -> UpscalerModel:
        return self._acquire(model_id, preference)

    def get_face_restorer(self, model_id: str, preference: str = "auto") -> FaceRestorer:
        return self._acquire(model_id, preference)

    def release_gpu(self) -> None:
        with self._lock:
            if self._on_gpu and self._on_gpu in self._loaded:
                self._loaded[self._on_gpu].to_cpu()
            self._on_gpu = None
            empty_cache()

    # -- face detection -------------------------------------------------
    def detect_faces(self, rgb: np.ndarray) -> Optional[list]:
        """Returns a list of faces, or None when detection is not available."""
        if not self.face_detection_available():
            return None
        with self._lock:
            try:
                if self._detector is None:
                    self._detector = FaceDetector(get_spec("yunet").path(self.settings.models_dir))
                return self._detector.detect(rgb)[: self.settings.max_faces]
            except Exception:
                log.exception("Face detection failed")
                return None
