from __future__ import annotations


class CanvasError(Exception):
    """Base for all Canvas API errors."""
    def __init__(self, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class CanvasAuthError(CanvasError):
    """401"""


class CanvasNotFoundError(CanvasError):
    """404"""


class CanvasVerifyError(CanvasError):
    """Raised when the access code cannot be confirmed after write."""


class ScheduleConflictError(Exception):
    """Raised when a proposed schedule overlaps an existing one."""

    def __init__(self, conflict_ids: list[int]) -> None:
        self.conflict_ids = conflict_ids
        super().__init__(
            f"Overlaps with existing schedule(s): {', '.join(str(i) for i in conflict_ids)}"
        )
