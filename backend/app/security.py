"""Access control for internet-facing use: an optional shared access key,
per-client rate limits and queue caps. All of it is off by default (local use)."""
from __future__ import annotations

import hmac
import math
import threading
import time
from collections import defaultdict, deque
from .errors import AppError

try:  # FastAPI resolves the annotation below at runtime, so import it for real when present
    from fastapi import Request
except ImportError:  # the job layer and its tests use this module without FastAPI
    Request = object  # type: ignore[assignment,misc]

KEY_HEADER = "X-Access-Key"


def client_id(request: Request) -> str:
    """Cloudflare puts the visitor's address in CF-Connecting-IP; behind the
    tunnel every request otherwise appears to come from 127.0.0.1."""
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if forwarded:
        return forwarded[:64]
    return request.client.host if request.client else "unknown"


def check_access_key(request: Request) -> None:
    expected = request.app.state.ctx.settings.access_key
    if not expected:
        return
    given = request.headers.get(KEY_HEADER, "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise AppError("auth_required",
                       "This server needs an access key. Ask the owner for the share link.",
                       status=401)


class RateLimiter:
    """Sliding one-hour window per (bucket, client)."""

    def __init__(self, window_s: float = 3600.0):
        self.window_s = window_s
        self._hits: "defaultdict[tuple, deque]" = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, client: str, limit: int, count: int = 1) -> None:
        if limit <= 0:
            return
        now = time.time()
        with self._lock:
            hits = self._hits[(bucket, client)]
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) + count > limit:
                wait = math.ceil((hits[0] + self.window_s - now) / 60) if hits else 60
                raise AppError(
                    "rate_limited",
                    f"Too many {bucket} from your connection (limit {limit} per hour). "
                    f"Try again in about {wait} minute{'s' if wait != 1 else ''}.",
                    status=429, retryable=True)
            hits.extend([now] * count)
