"""
Agent router.
POST /alerts/{alert_id}/triage
POST /alerts/{alert_id}/investigate
POST /alerts/{alert_id}/recommend
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.models.alert import Alert
from app.schemas.common import ApiResponse
from app.schemas.agent import (
    TriageRequest,
    TriageResponse,
    InvestigationSchema,
    RecommendationSchema,
)
from app.services.agent.service import AgentService

router = APIRouter(prefix="/alerts", tags=["agent"])


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
    db: Session = Depends(get_db),
) -> ApiResponse[InvestigationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    service = AgentService(db)
    investigation = service.investigate(alert)
    return ApiResponse.success(investigation)


@router.post(
    "/{alert_id}/recommend",
    response_model=ApiResponse[RecommendationSchema],
    summary="Recommend Actions",
    description="Generate action recommendations for alert. (DOC C C6.5)",
)
async def recommend_actions(
    alert_id: str = Path(..., description="Alert ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[RecommendationSchema]:
    alert = _get_alert_or_404(alert_id, db)
    service = AgentService(db)
    recommendation = service.recommend(alert)
    return ApiResponse.success(recommendation)
