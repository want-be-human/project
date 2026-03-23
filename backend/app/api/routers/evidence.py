"""
证据链路由。
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
    为指定告警构建并返回证据链。

    按 DOC F Week-5 DoD 要求，至少返回
    alert + flow + feature 三类节点。
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
