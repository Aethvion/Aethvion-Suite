"""
core/exceptions.py
Domain exception classes for Aethvion Suite.

Raise these from business logic; they map to HTTP responses automatically
via the exception handlers registered in server.py.

Usage:
    from core.exceptions import NotFoundError, BadRequestError
    raise NotFoundError("Workflow not found")
"""
from __future__ import annotations


class AethvionError(Exception):
    """Base domain exception — maps to an HTTP error response."""
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class NotFoundError(AethvionError):
    """Resource does not exist (404)."""
    status_code = 404


class BadRequestError(AethvionError):
    """Invalid input or malformed request (400)."""
    status_code = 400


class ConflictError(AethvionError):
    """Resource already exists or state conflict (409)."""
    status_code = 409


class ServiceUnavailableError(AethvionError):
    """A required service or dependency is unavailable (503)."""
    status_code = 503
