"""
Pipeline 可观测性路由。
GET /pipeline/{pcap_id}：获取指定 PCAP 的流水线运行记录。

数据来源：
- pipeline_runs 表（直接上传路径由 PipelineTracker 写入，批次路径由 JobRunner 同步写入）
- pcap_files 表兜底（历史数据：无 pipeline_run 但已处理完的 PCAP）
"""

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.errors import NotFoundError
from app.models.pcap import PcapFile
from app.models.pipeline import PipelineRunModel
from app.schemas.common import ApiResponse
from app.schemas.pipeline import PipelineRunSchema, StageRecordSchema
from app.core.utils import datetime_to_iso, generate_uuid

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _model_to_schema(model: PipelineRunModel) -> PipelineRunSchema:
    """将 PipelineRunModel ORM 转换为 API Schema。"""
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


def _synthesize_from_pcap(pcap: PcapFile) -> PipelineRunSchema:
    """兜底：当无 pipeline_run 记录但 PCAP 已完成时，从 pcap_files 构造摘要。"""
    ts = datetime_to_iso(pcap.created_at)
    stages = [
        StageRecordSchema(
            stage_name="parse", status="completed",
            started_at=ts, completed_at=ts,
            key_metrics={"flow_count": pcap.flow_count or 0},
            output_summary={"flow_count": pcap.flow_count or 0},
        ),
        StageRecordSchema(
            stage_name="feature_extract", status="completed",
            started_at=ts, completed_at=ts,
        ),
        StageRecordSchema(
            stage_name="detect", status="completed",
            started_at=ts, completed_at=ts,
            key_metrics={"flow_count": pcap.flow_count or 0},
        ),
        StageRecordSchema(
            stage_name="aggregate", status="completed",
            started_at=ts, completed_at=ts,
            key_metrics={"alert_count": pcap.alert_count or 0},
            output_summary={"alert_count": pcap.alert_count or 0},
        ),
    ]
    return PipelineRunSchema(
        id=generate_uuid(),
        pcap_id=pcap.id,
        status="completed",
        started_at=ts, completed_at=ts,
        total_latency_ms=None,
        stages=stages,
        created_at=ts,
    )


def _find_pipeline_data(pcap_id: str, db: Session) -> PipelineRunSchema | None:
    """查找 pipeline 数据：pipeline_runs → pcap_files 兜底。"""
    # 主查询：pipeline_runs（直接上传 + 批次处理都会写入）
    run = (
        db.query(PipelineRunModel)
        .filter(PipelineRunModel.pcap_id == pcap_id)
        .order_by(PipelineRunModel.created_at.desc())
        .first()
    )
    if run:
        return _model_to_schema(run)

    # 兜底：历史已完成 PCAP（无精确耗时）
    pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
    if pcap and pcap.status in ("done", "completed"):
        return _synthesize_from_pcap(pcap)

    return None


@router.get(
    "/{pcap_id}",
    response_model=ApiResponse[PipelineRunSchema],
    summary="Get Pipeline Run",
    description="Get the most recent pipeline run for a PCAP.",
)
async def get_pipeline_run(
    pcap_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[PipelineRunSchema]:
    if not settings.PIPELINE_OBSERVABILITY_ENABLED:
        raise NotFoundError(
            message="Pipeline observability is disabled",
            details={"feature_flag": "PIPELINE_OBSERVABILITY_ENABLED"},
        )

    result = _find_pipeline_data(pcap_id, db)
    if result:
        return ApiResponse.success(result)

    raise NotFoundError(
        message=f"No pipeline run found for PCAP: {pcap_id}",
        details={"pcap_id": pcap_id},
    )


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
    if not settings.PIPELINE_OBSERVABILITY_ENABLED:
        raise NotFoundError(
            message="Pipeline observability is disabled",
            details={"feature_flag": "PIPELINE_OBSERVABILITY_ENABLED"},
        )

    result = _find_pipeline_data(pcap_id, db)
    if result:
        return ApiResponse.success(result.stages)

    raise NotFoundError(
        message=f"No pipeline run found for PCAP: {pcap_id}",
        details={"pcap_id": pcap_id},
    )
