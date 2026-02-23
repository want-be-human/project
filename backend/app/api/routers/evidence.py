"""
Evidence Chain router.
GET /alerts/{alert_id}/evidence-chain — DOC C C6.6
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.models.alert import Alert
from app.schemas.common import ApiResponse
from app.schemas.evidence import EvidenceChainSchema

router = APIRouter(prefix="/alerts", tags=["evidence"])


@router.get(
    "/{alert_id}/evidence-chain",
    response_model=ApiResponse[EvidenceChainSchema],
    summary="Get Evidence Chain",
    description="Get evidence chain visualization for alert. (DOC C C6.6)",
)
async def get_evidence_chain(
    alert_id: str = Path(..., description="Alert ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[EvidenceChainSchema]:
    """
    Build and return the evidence chain for an alert.
    
    Always returns at least alert + flow + feature nodes
    per DOC F Week-5 DoD requirement.
    """
    alert = db.get(Alert, alert_id)
    if not alert:
        raise NotFoundError(
            message=f"Alert not found: {alert_id}",
            details={"alert_id": alert_id},
        )

    from app.services.evidence import EvidenceService

    svc = EvidenceService(db)
    chain = svc.build_evidence_chain(alert)
    return ApiResponse.success(chain)
