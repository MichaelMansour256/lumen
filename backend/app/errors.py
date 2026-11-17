"""User-facing application errors. Messages here are safe to show in the UI."""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400,
                 retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "details": self.details}


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass
