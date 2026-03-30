"""
场景路由。
POST   /scenarios
GET    /scenarios
POST   /scenarios/{scenario_id}/run
GET    /scenarios/{scenario_id}/latest-run
PATCH  /scenarios/{scenario_id}/archive
PATCH  /scenarios/{scenario_id}/unarchive
DELETE /scenarios/{scenario_id}
"""

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
    description="List scenarios. Default: active only. Pass include_archived=true to include archived.",
)
async def list_scenarios(
    limit: int = Query(default=50, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip count"),
    include_archived: bool = Query(default=False, description="Include archived scenarios"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ScenarioSchema]]:
    svc = ScenariosService(db)
    scenarios = svc.list_scenarios(limit=limit, offset=offset, include_archived=include_archived)
    return ApiResponse.success(scenarios)


@router.post(
    "/{scenario_id}/run",
    response_model=ApiResponse[ScenarioRunResultSchema],
    summary="Run Scenario",
    description="Execute a scenario and return results. Returns 409 if scenario is archived. "
                "Emits real-time WS events: scenario.run.started, scenario.stage.*, scenario.run.done.",
)
async def run_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioRunResultSchema]:
    svc = ScenariosService(db)
    scenario = svc.get_scenario(scenario_id)
    if not scenario:
        raise NotFoundError(message=f"Scenario {scenario_id} not found")

    # ScenarioRunTracker 内部已发布所有事件（started / stage.* / progress / done）
    result = svc.run_scenario(scenario)

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


@router.patch(
    "/{scenario_id}/archive",
    response_model=ApiResponse[ScenarioSchema],
    summary="Archive Scenario",
    description="Archive a scenario. Returns 409 if already archived.",
)
async def archive_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioSchema]:
    svc = ScenariosService(db)
    scenario = svc.archive_scenario(scenario_id)
    return ApiResponse.success(scenario)


@router.patch(
    "/{scenario_id}/unarchive",
    response_model=ApiResponse[ScenarioSchema],
    summary="Unarchive Scenario",
    description="Restore an archived scenario to active. Returns 409 if already active.",
)
async def unarchive_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[ScenarioSchema]:
    svc = ScenariosService(db)
    scenario = svc.unarchive_scenario(scenario_id)
    return ApiResponse.success(scenario)


@router.delete(
    "/{scenario_id}",
    status_code=204,
    summary="Delete Scenario",
    description="Permanently delete a scenario and all its run records. Irreversible.",
)
async def delete_scenario(
    scenario_id: str = Path(..., description="Scenario ID"),
    db: Session = Depends(get_db),
) -> None:
    svc = ScenariosService(db)
    svc.delete_scenario(scenario_id)
