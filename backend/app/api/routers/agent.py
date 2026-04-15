"""智能体路由：所有 agent 动作统一通过 WorkflowEngine 执行。"""

import json

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.models.alert import Alert
from app.models.investigation import Investigation
from app.models.recommendation import Recommendation as RecommendationModel
from app.schemas.common import ApiResponse
from app.schemas.agent import (
    TriageRequest,
    TriageResponse,
    InvestigationSchema,
    RecommendationSchema,
    LanguageRequest,
)
from app.schemas.twin import CompilePlanRequest, CompilePlanResponse
from app.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/alerts", tags=["agent"])
lookup_router = APIRouter(tags=["agent"])


def _get_alert_or_404(alert_id: str, db: Session) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert {alert_id} not found")
    return alert


@router.post(
    "/{alert_id}/triage",
    response_model=ApiResponse[TriageResponse],
    summary="Triage Alert",
    description="为指定告警生成分诊摘要。(DOC C C6.5)",
)
async def triage_alert(
    alert_id: str = Path(..., description="告警 ID"),
    request: TriageRequest = TriageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[TriageResponse]:
    alert = _get_alert_or_404(alert_id, db)
    engine = WorkflowEngine(db)
    summary = engine.run_stage("triage", alert, language=request.language)
    return ApiResponse.success(TriageResponse(triage_summary=summary))


@router.post(
    "/{alert_id}/investigate",
    response_model=ApiResponse[InvestigationSchema],
    summary="Investigate Alert",
    description="为指定告警生成调查分析。(DOC C C6.5)",
)
async def investigate_alert(
    alert_id: str = Path(..., description="告警 ID"),
    request: LanguageRequest = LanguageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[InvestigationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    engine = WorkflowEngine(db)
    investigation = engine.run_stage("investigate", alert, language=request.language)
    return ApiResponse.success(investigation)


@router.post(
    "/{alert_id}/recommend",
    response_model=ApiResponse[RecommendationSchema],
    summary="Recommend Actions",
    description="为指定告警生成处置推荐动作。(DOC C C6.5)",
)
async def recommend_actions(
    alert_id: str = Path(..., description="告警 ID"),
    request: LanguageRequest = LanguageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[RecommendationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    engine = WorkflowEngine(db)
    recommendation = engine.run_stage("recommend", alert, language=request.language)
    return ApiResponse.success(recommendation)


@router.post(
    "/{alert_id}/compile-plan",
    response_model=ApiResponse[CompilePlanResponse],
    summary="Compile Recommendation into ActionPlan",
    description="将 Agent 推荐编译为结构化的孪生 ActionPlan 以供 dry-run。",
)
async def compile_plan(
    alert_id: str = Path(..., description="告警 ID"),
    request: CompilePlanRequest = CompilePlanRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[CompilePlanResponse]:
    alert = _get_alert_or_404(alert_id, db)
    engine = WorkflowEngine(db)
    response = engine.run_stage(
        "compile_plan",
        alert,
        language=request.language,
        previous_outputs={"recommendation_id": request.recommendation_id},
    )
    return ApiResponse.success(response)


@lookup_router.get(
    "/investigations/{investigation_id}",
    response_model=ApiResponse[InvestigationSchema],
    summary="Get Investigation by ID",
    description="按 ID 查询已生成的调查结果。",
)
async def get_investigation(
    investigation_id: str = Path(..., description="调查结果 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[InvestigationSchema]:
    inv = db.query(Investigation).filter(Investigation.id == investigation_id).first()
    if not inv:
        raise NotFoundError(message=f"Investigation {investigation_id} not found")
    payload = json.loads(inv.payload)
    return ApiResponse.success(InvestigationSchema(**payload))


@lookup_router.get(
    "/recommendations/{recommendation_id}",
    response_model=ApiResponse[RecommendationSchema],
    summary="Get Recommendation by ID",
    description="按 ID 查询已生成的推荐结果。",
)
async def get_recommendation(
    recommendation_id: str = Path(..., description="推荐结果 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[RecommendationSchema]:
    rec = db.query(RecommendationModel).filter(RecommendationModel.id == recommendation_id).first()
    if not rec:
        raise NotFoundError(message=f"Recommendation {recommendation_id} not found")
    payload = json.loads(rec.payload)
    return ApiResponse.success(RecommendationSchema(**payload))
