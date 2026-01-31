"""
Alerts router.
GET /alerts, GET /alerts/{alert_id}, PATCH /alerts/{alert_id}
"""

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.alert import AlertSchema, AlertUpdateRequest

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=ApiResponse[list[AlertSchema]],
    summary="List Alerts",
    description="List alerts with filtering and pagination. (DOC C C6.4)",
)
async def list_alerts(
    status: str | None = Query(default=None, description="Filter by status"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    type: str | None = Query(default=None, description="Filter by type"),
    start: str | None = Query(default=None, description="Start time filter ISO8601"),
    end: str | None = Query(default=None, description="End time filter ISO8601"),
    limit: int = Query(default=50, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip count"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[AlertSchema]]:
    """
    List alert records with optional filters.
    """
    # TODO: Implement alert listing with filters
    return ApiResponse.success([])


@router.get(
    "/{alert_id}",
    response_model=ApiResponse[AlertSchema],
    summary="Get Alert Details",
    description="Get a specific alert by ID. (DOC C C6.4)",
)
async def get_alert(
    alert_id: str = Path(..., description="Alert ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertSchema]:
    """
    Get alert by ID.
    """
    # TODO: Implement alert retrieval
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)


@router.patch(
    "/{alert_id}",
    response_model=ApiResponse[AlertSchema],
    summary="Update Alert",
    description="Update alert status, severity, tags, or notes. (DOC C C6.4)",
)
async def update_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: AlertUpdateRequest = ...,
    db: Session = Depends(get_db),
) -> ApiResponse[AlertSchema]:
    """
    Update alert fields.
    
    Allowed fields:
    - status: new, triaged, investigating, resolved, false_positive
    - severity: low, medium, high, critical
    - tags: list of strings
    - notes: string
    """
    # TODO: Implement alert update
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=alert_id)
