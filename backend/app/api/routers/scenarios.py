"""
Scenarios router.
POST /scenarios
GET /scenarios
POST /scenarios/{scenario_id}/run
GET /scenarios/{scenario_id}/latest-run
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.models.pcap import PcapFile
from app.models.scenario import ScenarioRun
from app.schemas.common import ApiResponse
from app.schemas.scenario import (
    ScenarioSchema,
    ScenarioRunResultSchema,
    CreateScenarioRequest,
)
from app.services.scenarios.service import ScenariosService
from app.api.routers.stream import broadcast_scenario_done

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
    # 校验 PCAP 是否存在
    pcap = db.query(PcapFile).filter(PcapFile.id == request.pcap_ref.pcap_id).first()
    if not pcap:
        raise NotFoundError(message=f"PcapFile {request.pcap_ref.pcap_id} not found")

    svc = ScenariosService(db)
    scenario = svc.create_scenario(
        name=request.name,
        description=request.description,
        pcap_id=request.pcap_ref.pcap_id,
        expectations=request.expectations,
        tags=request.tags,
    )
    return ApiResponse.success(scenario)


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
    svc = ScenariosService(db)
    scenarios = svc.list_scenarios(limit=limit, offset=offset)
    return ApiResponse.success(scenarios)


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
    1. Checks min_alerts expectation
    2. Checks must_have patterns
    3. Checks evidence_chain_contains
    4. If dry_run_required, verifies dry-run exists
    
    Returns ScenarioRunResult with:
    - status: pass/fail
    - checks: Individual check results
    - metrics: Aggregate metrics
    """
    svc = ScenariosService(db)
    scenario = svc.get_scenario(scenario_id)
    if not scenario:
        raise NotFoundError(message=f"Scenario {scenario_id} not found")

    result = svc.run_scenario(scenario)

    # WS 广播：scenario.run.done（DOC C C7.2）
    asyncio.create_task(
        broadcast_scenario_done(scenario_id=scenario.id, status=result.status)
    )

    return ApiResponse.success(result)


@router.get(
    "/{scenario_id}/latest-run",
    response_model=ApiResponse[ScenarioRunResultSchema],
    summary="Get Latest Scenario Run",
    description="Fetch the most recent run result for a scenario.",
)
async def get_latest_scenario_run(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioRunResultSchema]:
    run = (
        db.query(ScenarioRun)
        .filter(ScenarioRun.scenario_id == scenario_id)
        .order_by(ScenarioRun.created_at.desc())
        .first()
    )
    if not run:
        raise NotFoundError(message=f"No runs found for Scenario {scenario_id}")
    payload = json.loads(run.payload) if isinstance(run.payload, str) else run.payload
    return ApiResponse.success(ScenarioRunResultSchema.model_validate(payload))
