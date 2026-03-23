"""
Pipeline 可观测性路由。
GET /pipeline/{pcap_id}：获取指定 PCAP 的流水线运行记录。
"""

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.errors import NotFoundError
from app.models.pipeline import PipelineRunModel
from app.schemas.common import ApiResponse
from app.schemas.pipeline import PipelineRunSchema, StageRecordSchema
from app.core.utils import datetime_to_iso

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _model_to_schema(model: PipelineRunModel) -> PipelineRunSchema:
    """将 ORM 模型转换为 API Schema。"""
    stages_raw: list[dict[str, Any]] = json.loads(model.stages_log or "[]")
    stages = [StageRecordSchema(**s) for s in stages_raw]
    return PipelineRunSchema(
        id=model.id,
        pcap_id=model.pcap_id,
        status=model.status,
        started_at=datetime_to_iso(model.created_at),
        completed_at=datetime_to_iso(model.completed_at) if model.completed_at else None,
        total_latency_ms=model.total_latency_ms,
        stages=stages,
        created_at=datetime_to_iso(model.created_at),
    )


@router.get(
    "/{pcap_id}",
    response_model=ApiResponse[PipelineRunSchema],
    summary="Get Pipeline Run",
    description="Get the most recent pipeline run for a PCAP. Requires PIPELINE_OBSERVABILITY_ENABLED.",
)
async def get_pipeline_run(
    pcap_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[PipelineRunSchema]:
    """返回指定 PCAP 的最新一次 pipeline run。"""
    if not settings.PIPELINE_OBSERVABILITY_ENABLED:
        raise NotFoundError(
            message="Pipeline observability is disabled",
            details={"feature_flag": "PIPELINE_OBSERVABILITY_ENABLED"},
        )

    run = (
        db.query(PipelineRunModel)
        .filter(PipelineRunModel.pcap_id == pcap_id)
        .order_by(PipelineRunModel.created_at.desc())
        .first()
    )
    if not run:
        raise NotFoundError(
            message=f"No pipeline run found for PCAP: {pcap_id}",
            details={"pcap_id": pcap_id},
        )

    return ApiResponse.success(_model_to_schema(run))


@router.get(
    "/{pcap_id}/stages",
    response_model=ApiResponse[list[StageRecordSchema]],
    summary="Get Pipeline Stages",
    description="Get detailed stage records for the most recent pipeline run of a PCAP.",
)
async def get_pipeline_stages(
    pcap_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StageRecordSchema]]:
    """返回最新 pipeline run 的阶段明细。"""
    if not settings.PIPELINE_OBSERVABILITY_ENABLED:
        raise NotFoundError(
            message="Pipeline observability is disabled",
            details={"feature_flag": "PIPELINE_OBSERVABILITY_ENABLED"},
        )

    run = (
        db.query(PipelineRunModel)
        .filter(PipelineRunModel.pcap_id == pcap_id)
        .order_by(PipelineRunModel.created_at.desc())
        .first()
    )
    if not run:
        raise NotFoundError(
            message=f"No pipeline run found for PCAP: {pcap_id}",
            details={"pcap_id": pcap_id},
        )

    stages_raw = json.loads(run.stages_log or "[]")
    stages = [StageRecordSchema(**s) for s in stages_raw]
    return ApiResponse.success(stages)
