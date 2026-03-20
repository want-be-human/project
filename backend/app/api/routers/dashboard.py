"""
仪表盘路由。
GET /dashboard/summary — 获取仪表盘聚合数据。
实现需求 1.1、1.2。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.dashboard import DashboardSummarySchema
from app.services.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=ApiResponse[DashboardSummarySchema],
    summary="获取仪表盘聚合数据",
)
async def get_dashboard_summary(
    db: Session = Depends(get_db),
) -> ApiResponse[DashboardSummarySchema]:
    """聚合所有仪表盘所需数据并返回。"""
    service = DashboardService(db)
    summary = service.get_summary()
    return ApiResponse.success(summary)
