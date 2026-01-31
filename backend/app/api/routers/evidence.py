"""
Evidence Chain router.
GET /alerts/{alert_id}/evidence-chain
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
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
    
    The evidence chain links:
    - Alert to supporting flows
    - Flows to explaining features
    - Alert to hypothesis (if investigation exists)
    - Hypothesis to recommended actions
    - Actions to dry-run results
    
    Returns EvidenceChain with nodes and edges for visualization.
    """
    # TODO: Implement evidence chain building
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)
