"""Hardware detection. torch is imported lazily so the API can start (and
report a clear status) even when PyTorch is missing or broken."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("enhancer.device")
_torch = None
_torch_error: Optional[str] = None


def get_torch():
    """Return the torch module, or None when it cannot be imported."""
    global _torch, _torch_error
    if _torch is None and _torch_error is None:
        try:
            import torch
            _torch = torch
        except Exception as exc:  # ImportError, DLL load failures on Windows, ...
            _torch_error = f"{type(exc).__name__}: {exc}"
            log.warning("PyTorch unavailable: %s", _torch_error)
    return _torch


def device_info(preference: str = "auto", want_fp16: bool = True) -> dict:
    torch = get_torch()
    info = {
        "torch_available": torch is not None, "torch_version": None, "torch_error": _torch_error,
        "cuda_available": False, "device": "cpu", "gpu_name": None,
        "vram_total_mb": None, "vram_free_mb": None, "fp16": False, "note": None,
    }
    if torch is None:
        info["note"] = "PyTorch is not installed; AI models cannot run."
        return info
    info["torch_version"] = str(torch.__version__)
    try:
        cuda = bool(torch.cuda.is_available())
    except Exception as exc:
        cuda = False
        info["note"] = f"CUDA check failed: {exc}"
    info["cuda_available"] = cuda
    if cuda:
        try:
            free, total = torch.cuda.mem_get_info(0)
            info.update(gpu_name=torch.cuda.get_device_name(0),
                        vram_total_mb=int(total / 2 ** 20), vram_free_mb=int(free / 2 ** 20))
        except Exception as exc:
            info["note"] = f"Could not query GPU memory: {exc}"
    if preference == "cpu":
        info["note"] = "CPU mode forced by configuration."
    elif cuda:
        info["device"] = "cuda"
        info["fp16"] = bool(want_fp16)
    elif info["note"] is None:
        info["note"] = "No CUDA GPU detected by PyTorch; running on CPU (slow)."
    return info


def free_vram_mb() -> Optional[int]:
    torch = get_torch()
    if torch is None or not torch.cuda.is_available():
        return None
    try:
        return int(torch.cuda.mem_get_info(0)[0] / 2 ** 20)
    except Exception:
        return None


def empty_cache() -> None:
    torch = get_torch()
    if torch is not None and torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def is_oom(exc: BaseException) -> bool:
    torch = get_torch()
    if torch is not None and isinstance(exc, getattr(torch.cuda, "OutOfMemoryError", ())):
        return True
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()
