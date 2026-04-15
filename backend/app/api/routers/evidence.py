"""证据链路由。GET /alerts/{alert_id}/evidence-chain — DOC C C6.6。"""

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
    description="获取告警的证据链可视化数据。(DOC C C6.6)",
)
async def get_evidence_chain(
    alert_id: str = Path(..., description="告警 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[EvidenceChainSchema]:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise NotFoundError(
            message=f"Alert not found: {alert_id}",
            details={"alert_id": alert_id},
        )

    from app.services.evidence import EvidenceService

    chain = EvidenceService(db).build_evidence_chain(alert)
    return ApiResponse.success(chain)
