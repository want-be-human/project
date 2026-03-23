"""
场景路由。
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
    创建用于回归测试的新场景。

    一个场景定义了：
    - PCAP 引用
    - 期望告警（min_alerts、must_have 类型）
    - 证据链要求
    - 是否要求 dry-run
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
    分页列出所有场景。
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
    运行场景并校验期望结果。

    运行过程：
    1. 校验 min_alerts
    2. 校验 must_have 模式
    3. 校验 evidence_chain_contains
    4. 若 dry_run_required 为真，验证 dry-run 是否存在

    返回 ScenarioRunResult，包含：
    - status: pass/fail
    - checks: 各项检查结果
    - metrics: 聚合指标
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
