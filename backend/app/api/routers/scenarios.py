"""
Scenarios router.
POST /scenarios
GET /scenarios
POST /scenarios/{scenario_id}/run
"""

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.scenario import (
    ScenarioSchema,
    ScenarioRunResultSchema,
    CreateScenarioRequest,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post(
    "",
    response_model=ApiResponse[ScenarioSchema],
    summary="Create Scenario",
    description="Create a regression scenario. (DOC C C6.9)",
)
async def create_scenario(
    request: CreateScenarioRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioSchema]:
    """
    Create a new scenario for regression testing.
    
    A scenario defines:
    - PCAP reference
    - Expected alerts (min_alerts, must_have types)
    - Evidence chain requirements
    - Whether dry-run is required
    """
    # TODO: Implement scenario creation
    # Verify PCAP exists, create and save scenario
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="PcapFile", resource_id=request.pcap_ref.pcap_id)


@router.get(
    "",
    response_model=ApiResponse[list[ScenarioSchema]],
    summary="List Scenarios",
    description="List all scenarios. (DOC C C6.9)",
)
async def list_scenarios(
    limit: int = Query(default=50, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip count"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ScenarioSchema]]:
    """
    List all scenarios with pagination.
    """
    # TODO: Implement scenario listing
    return ApiResponse.success([])


@router.post(
    "/{scenario_id}/run",
    response_model=ApiResponse[ScenarioRunResultSchema],
    summary="Run Scenario",
    description="Execute a scenario and return results. (DOC C C6.9)",
)
async def run_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioRunResultSchema]:
    """
    Run a scenario and check expectations.
    
    The run:
    1. Processes the referenced PCAP (if not already done)
    2. Checks min_alerts expectation
    3. Checks must_have patterns
    4. Checks evidence_chain_contains
    5. If dry_run_required, verifies dry-run exists or triggers one
    
    Returns ScenarioRunResult with:
    - status: pass/fail
    - checks: Individual check results
    - metrics: Aggregate metrics
    """
    # TODO: Implement scenario execution
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Scenario", resource_id=scenario_id)
