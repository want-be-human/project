"""健康检查路由。"""

from fastapi import APIRouter

from app.schemas.common import ApiResponse, HealthStatus

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ApiResponse[HealthStatus],
    summary="Health Check",
    description="返回服务健康状态（DOC C C6.1）",
)
async def health_check() -> ApiResponse[HealthStatus]:
    return ApiResponse.success(HealthStatus(status="ok"))
