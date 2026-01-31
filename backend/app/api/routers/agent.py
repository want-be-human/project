"""
Agent router.
POST /alerts/{alert_id}/triage
POST /alerts/{alert_id}/investigate
POST /alerts/{alert_id}/recommend
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.agent import (
    TriageRequest,
    TriageResponse,
    InvestigationSchema,
    RecommendationSchema,
)

router = APIRouter(prefix="/alerts", tags=["agent"])


@router.post(
    "/{alert_id}/triage",
    response_model=ApiResponse[TriageResponse],
    summary="Triage Alert",
    description="Generate triage summary for alert. (DOC C C6.5)",
)
async def triage_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: TriageRequest = ...,
    db: Session = Depends(get_db),
) -> ApiResponse[TriageResponse]:
    """
    Generate a short triage summary for the alert.
    
    The summary is also saved to alert.agent.triage_summary.
    
    Parameters:
    - language: 'zh' for Chinese, 'en' for English
    """
    # TODO: Implement triage generation
    # Verify alert exists first
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)


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
    """
    Generate a structured investigation for the alert.
    
    Returns Investigation with:
    - hypothesis: What the agent thinks is happening
    - why: Reasons supporting the hypothesis
    - impact: Scope and confidence assessment
    - next_steps: Recommended actions
    - safety_note: Disclaimer about advisory nature
    """
    # TODO: Implement investigation generation
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)


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
    """
    Generate action recommendations for the alert.
    
    Returns Recommendation with list of actions including:
    - title: Action description
    - priority: high/medium/low
    - steps: Implementation steps
    - rollback: Rollback instructions
    - risk: Risk description
    """
    # TODO: Implement recommendation generation
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)
