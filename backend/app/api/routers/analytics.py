"""标准化分析 API 路由。所有端点位于 /analytics/* 命名空间下。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.analytics import (
    AnalyticsOverviewSchema,
    ScoreResultSchema,
    TopAssetsSchema,
)
from app.schemas.common import ApiResponse
from app.schemas.dashboard import (
    ActivityEventSchema,
    DistributionsSchema,
    TopologySnapshotSchema,
    TrendsSchema,
)
from app.services.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=ApiResponse[AnalyticsOverviewSchema])
async def get_overview(
    db: Session = Depends(get_db),
) -> ApiResponse[AnalyticsOverviewSchema]:
    return ApiResponse.success(AnalyticsService(db).get_overview())


@router.get("/scores/posture", response_model=ApiResponse[ScoreResultSchema])
async def get_posture_score(
    db: Session = Depends(get_db),
) -> ApiResponse[ScoreResultSchema]:
    return ApiResponse.success(AnalyticsService(db).get_posture_score())


@router.get("/scores/action-safety", response_model=ApiResponse[ScoreResultSchema])
async def get_action_safety_score(
    db: Session = Depends(get_db),
) -> ApiResponse[ScoreResultSchema]:
    return ApiResponse.success(AnalyticsService(db).get_action_safety_score())


@router.get("/trends", response_model=ApiResponse[TrendsSchema])
async def get_trends(
    db: Session = Depends(get_db),
) -> ApiResponse[TrendsSchema]:
    return ApiResponse.success(AnalyticsService(db).get_trends())


@router.get("/distributions", response_model=ApiResponse[DistributionsSchema])
async def get_distributions(
    db: Session = Depends(get_db),
) -> ApiResponse[DistributionsSchema]:
    return ApiResponse.success(AnalyticsService(db).get_distributions())


@router.get(
    "/topology-snapshot", response_model=ApiResponse[TopologySnapshotSchema]
)
async def get_topology_snapshot(
    db: Session = Depends(get_db),
) -> ApiResponse[TopologySnapshotSchema]:
    return ApiResponse.success(AnalyticsService(db).get_topology_snapshot())


@router.get(
    "/recent-activity",
    response_model=ApiResponse[list[ActivityEventSchema]],
)
async def get_recent_activity(
    db: Session = Depends(get_db),
) -> ApiResponse[list[ActivityEventSchema]]:
    return ApiResponse.success(AnalyticsService(db).get_recent_activity())


@router.get("/top-assets", response_model=ApiResponse[TopAssetsSchema])
async def get_top_assets(
    db: Session = Depends(get_db),
) -> ApiResponse[TopAssetsSchema]:
    return ApiResponse.success(AnalyticsService(db).get_top_assets())
