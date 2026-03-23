"""
Agent router.
POST /alerts/{alert_id}/triage
POST /alerts/{alert_id}/investigate
POST /alerts/{alert_id}/recommend
POST /alerts/{alert_id}/compile-planGET  /investigations/{investigation_id}
GET  /recommendations/{recommendation_id}"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

import json

from app.api.deps import get_db
from app.core.config import settings
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
from app.services.agent.service import AgentService
from app.services.plan_compiler.service import PlanCompilerService
from app.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/alerts", tags=["agent"])
lookup_router = APIRouter(tags=["agent"])


def _get_alert_or_404(alert_id: str, db: Session) -> Alert:
    """Fetch alert or raise NotFoundError."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert {alert_id} not found")
    return alert


@router.post(
    "/{alert_id}/triage",
    response_model=ApiResponse[TriageResponse],
    summary="Triage Alert",
    description="Generate triage summary for alert. (DOC C C6.5)",
)
async def triage_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: TriageRequest = TriageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[TriageResponse]:
    alert = _get_alert_or_404(alert_id, db)
    if settings.WORKFLOW_ENGINE_ENABLED:
        engine = WorkflowEngine(db)
        summary = engine.run_stage("triage", alert, language=request.language)
    else:
        service = AgentService(db)
        summary = service.triage(alert, language=request.language)
    return ApiResponse.success(TriageResponse(triage_summary=summary))


@router.post(
    "/{alert_id}/investigate",
    response_model=ApiResponse[InvestigationSchema],
    summary="Investigate Alert",
    description="Generate investigation analysis for alert. (DOC C C6.5)",
)
async def investigate_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: LanguageRequest = LanguageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[InvestigationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    if settings.WORKFLOW_ENGINE_ENABLED:
        engine = WorkflowEngine(db)
        investigation = engine.run_stage("investigate", alert, language=request.language)
    else:
        service = AgentService(db)
        investigation = service.investigate(alert, language=request.language)
    return ApiResponse.success(investigation)


@router.post(
    "/{alert_id}/recommend",
    response_model=ApiResponse[RecommendationSchema],
    summary="Recommend Actions",
    description="Generate action recommendations for alert. (DOC C C6.5)",
)
async def recommend_actions(
    alert_id: str = Path(..., description="Alert ID"),
    request: LanguageRequest = LanguageRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[RecommendationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    if settings.WORKFLOW_ENGINE_ENABLED:
        engine = WorkflowEngine(db)
        recommendation = engine.run_stage("recommend", alert, language=request.language)
    else:
        service = AgentService(db)
        recommendation = service.recommend(alert, language=request.language)
    return ApiResponse.success(recommendation)


@router.post(
    "/{alert_id}/compile-plan",
    response_model=ApiResponse[CompilePlanResponse],
    summary="Compile Recommendation into ActionPlan",
    description="Compile Agent recommendations into a structured Twin ActionPlan for dry-run.",
)
async def compile_plan(
    alert_id: str = Path(..., description="Alert ID"),
    request: CompilePlanRequest = CompilePlanRequest(),
    db: Session = Depends(get_db),
) -> ApiResponse[CompilePlanResponse]:
    _get_alert_or_404(alert_id, db)
    if settings.WORKFLOW_ENGINE_ENABLED:
        engine = WorkflowEngine(db)
        response = engine.run_stage(
            "compile_plan",
            _get_alert_or_404(alert_id, db),
            language=request.language,
            previous_outputs={"recommendation_id": request.recommendation_id},
        )
    else:
        service = PlanCompilerService(db)
        response = service.compile_for_alert(
            alert_id=alert_id,
            recommendation_id=request.recommendation_id,
            language=request.language,
        )
    return ApiResponse.success(response)


# ---------- 查询接口 ----------

@lookup_router.get(
    "/investigations/{investigation_id}",
    response_model=ApiResponse[InvestigationSchema],
    summary="Get Investigation by ID",
    description="Retrieve a previously generated investigation result by its ID.",
)
async def get_investigation(
    investigation_id: str = Path(..., description="Investigation ID"),
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
    description="Retrieve a previously generated recommendation result by its ID.",
)
async def get_recommendation(
    recommendation_id: str = Path(..., description="Recommendation ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[RecommendationSchema]:
    rec = db.query(RecommendationModel).filter(RecommendationModel.id == recommendation_id).first()
    if not rec:
        raise NotFoundError(message=f"Recommendation {recommendation_id} not found")
    payload = json.loads(rec.payload)
    return ApiResponse.success(RecommendationSchema(**payload))
