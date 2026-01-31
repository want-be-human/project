"""
Health check router.
GET /api/v1/health
"""

from fastapi import APIRouter

from app.schemas.common import ApiResponse, HealthStatus

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ApiResponse[HealthStatus],
    summary="Health Check",
    description="Returns service health status per DOC C C6.1",
)
async def health_check() -> ApiResponse[HealthStatus]:
    """
    Health check endpoint.
    
    Returns:
        { ok: true, data: { status: "ok" } }
    """
    return ApiResponse.success(HealthStatus(status="ok"))
