"""
Common schemas for API responses.
Follows DOC C C0.2 Unified Response Envelope.
"""

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail structure per DOC C C0.2."""

    code: str = Field(..., description="Error code from DOC C C0.3")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional error details")


class ApiResponse(BaseModel, Generic[T]):
    """
    Unified API response envelope per DOC C C0.2.
    
    Success: { "ok": true, "data": {...}, "error": null }
    Failure: { "ok": false, "data": null, "error": {...} }
    """

    ok: bool = Field(..., description="Whether the request succeeded")
    data: T | None = Field(default=None, description="Response data on success")
    error: ErrorDetail | None = Field(default=None, description="Error details on failure")

    @classmethod
    def success(cls, data: T) -> "ApiResponse[T]":
        """Create a success response."""
        return cls(ok=True, data=data, error=None)

    @classmethod
    def failure(cls, code: str, message: str, details: dict[str, Any] | None = None) -> "ApiResponse[None]":
        """Create a failure response."""
        return cls(
            ok=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details or {}),
        )


class PaginationParams(BaseModel):
    """Common pagination parameters."""

    limit: int = Field(default=50, ge=1, le=1000, description="Maximum number of items to return")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class HealthStatus(BaseModel):
    """Health check response data."""

    status: str = Field(default="ok", description="Service status")
