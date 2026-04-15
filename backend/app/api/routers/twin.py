"""孪生路由（ActionPlan 与 DryRun）。"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.core.utils import iso_to_datetime
from app.models.alert import Alert
from app.models.twin import TwinPlan, DryRun
from app.schemas.common import ApiResponse
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    CreatePlanRequest,
    DryRunRequest,
)
from app.services.twin.service import TwinService

router = APIRouter(prefix="/twin", tags=["twin"])


@router.post(
    "/plans",
    response_model=ApiResponse[ActionPlanSchema],
    summary="Create Action Plan",
    description="创建用于 dry-run 仿真的动作方案。(DOC C C6.8)",
)
async def create_plan(
    request: CreatePlanRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[ActionPlanSchema]:
    alert = db.query(Alert).filter(Alert.id == request.alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert {request.alert_id} not found")

    service = TwinService(db)
    plan = service.create_plan(
        alert_id=request.alert_id,
        actions=request.actions,
        source=request.source,
        notes=request.notes,
    )
    return ApiResponse.success(plan)


@router.post(
    "/plans/{plan_id}/dry-run",
    response_model=ApiResponse[DryRunResultSchema],
    summary="Execute Dry Run",
    description="对指定方案执行 dry-run 仿真。(DOC C C6.8)",
)
async def execute_dry_run(
    plan_id: str = Path(..., description="Plan ID"),
    request: DryRunRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DryRunResultSchema]:
    plan = db.query(TwinPlan).filter(TwinPlan.id == plan_id).first()
    if not plan:
        raise NotFoundError(message=f"TwinPlan {plan_id} not found")

    alert = db.query(Alert).filter(Alert.id == plan.alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert {plan.alert_id} not found")

    # 时间窗口：优先使用请求参数，否则回退到 alert.time_window
    if request and request.start and request.end:
        start = iso_to_datetime(request.start)
        end = iso_to_datetime(request.end)
    else:
        start = alert.time_window_start
        end = alert.time_window_end
    mode = (request.mode if request and request.mode else None) or "ip"

    result = TwinService(db).dry_run(plan, start, end, mode)

    # WS 广播以 fire-and-forget 方式触发，失败不应影响主请求
    try:
        from app.api.routers.stream import broadcast_dryrun_created
        risk = result.impact.service_disruption_risk
        confidence = result.impact.confidence
        asyncio.create_task(broadcast_dryrun_created(result.id, result.alert_id, risk, confidence))
    except Exception:
        pass

    return ApiResponse.success(result)


@router.get(
    "/dry-runs",
    response_model=ApiResponse[list[DryRunResultSchema]],
    summary="List Dry Runs",
    description="列出 dry-run 结果，可按告警 ID 过滤。(DOC C C6.8)",
)
async def list_dry_runs(
    alert_id: str | None = Query(default=None, description="按告警 ID 过滤"),
    limit: int = Query(default=20, ge=1, le=100, description="最大返回条数"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[DryRunResultSchema]]:
    query = db.query(DryRun).order_by(DryRun.created_at.desc())
    if alert_id:
        query = query.filter(DryRun.alert_id == alert_id)
    runs = query.limit(limit).all()

    results = []
    for run in runs:
        payload = json.loads(run.payload) if isinstance(run.payload, str) else run.payload
        results.append(DryRunResultSchema.model_validate(payload))

    return ApiResponse.success(results)


@router.get(
    "/dry-runs/{dry_run_id}",
    response_model=ApiResponse[DryRunResultSchema],
    summary="Get Dry Run",
    description="按 ID 查询单条 dry-run 结果。",
)
async def get_dry_run(
    dry_run_id: str = Path(..., description="Dry-run 结果 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[DryRunResultSchema]:
    run = db.query(DryRun).filter(DryRun.id == dry_run_id).first()
    if not run:
        raise NotFoundError(message=f"DryRun {dry_run_id} not found")
    payload = json.loads(run.payload) if isinstance(run.payload, str) else run.payload
    return ApiResponse.success(DryRunResultSchema.model_validate(payload))
