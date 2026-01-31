"""
Twin router (ActionPlan & DryRun).
POST /twin/plans
POST /twin/plans/{plan_id}/dry-run
GET /twin/dry-runs
"""

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    CreatePlanRequest,
    DryRunRequest,
)

router = APIRouter(prefix="/twin", tags=["twin"])


@router.post(
    "/plans",
    response_model=ApiResponse[ActionPlanSchema],
    summary="Create Action Plan",
    description="Create an action plan for dry-run simulation. (DOC C C6.8)",
)
async def create_plan(
    request: CreatePlanRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[ActionPlanSchema]:
    """
    Create an action plan for an alert.
    
    Plans can be:
    - agent: Generated from recommendation
    - manual: Created by user
    
    The plan is saved and can be used for dry-run simulations.
    """
    # TODO: Implement plan creation
    # Verify alert exists, create and save plan
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Alert", resource_id=request.alert_id)


@router.post(
    "/plans/{plan_id}/dry-run",
    response_model=ApiResponse[DryRunResultSchema],
    summary="Execute Dry Run",
    description="Execute dry-run simulation for a plan. (DOC C C6.8)",
)
async def execute_dry_run(
    plan_id: str = Path(..., description="Plan ID"),
    request: DryRunRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[DryRunResultSchema]:
    """
    Execute a dry-run simulation for the given plan.
    
    The simulation:
    1. Builds graph for the time window
    2. Applies planned actions to graph
    3. Calculates impact metrics
    4. Finds alternative paths
    
    Optional parameters:
    - start/end: Override time window (defaults to alert.time_window)
    - mode: ip or subnet
    """
    # TODO: Implement dry-run execution
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="TwinPlan", resource_id=plan_id)


@router.get(
    "/dry-runs",
    response_model=ApiResponse[list[DryRunResultSchema]],
    summary="List Dry Runs",
    description="List dry-run results with optional alert filter. (DOC C C6.8)",
)
async def list_dry_runs(
    alert_id: str | None = Query(default=None, description="Filter by alert ID"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[DryRunResultSchema]]:
    """
    List dry-run results, optionally filtered by alert.
    """
    # TODO: Implement dry-run listing
    return ApiResponse.success([])
