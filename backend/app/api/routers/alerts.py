"""告警路由。实现 DOC C C6.4。"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.core.utils import datetime_to_iso, iso_to_datetime
from app.models.alert import Alert
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.alert import (
    AlertSchema,
    AlertUpdateRequest,
    TimeWindow,
    AlertEntities,
    PrimaryService,
    AlertEvidence,
    AlertAggregation,
    AlertAgent,
    AlertTwin,
    TopFlowSummary,
    TopFeature,
    PcapRef,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _parse_json(text: str, fallback=None):
    if fallback is None:
        fallback = {}
    if not text:
        return fallback
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _alert_to_schema(alert: Alert) -> AlertSchema:
    evidence_raw = _parse_json(alert.evidence, {})
    aggregation_raw = _parse_json(alert.aggregation, {})
    agent_raw = _parse_json(alert.agent, {})
    twin_raw = _parse_json(alert.twin, {})
    tags_raw = _parse_json(alert.tags, [])

    top_flows = [
        TopFlowSummary(
            flow_id=tf.get("flow_id", ""),
            anomaly_score=tf.get("anomaly_score", 0),
            summary=tf.get("summary", ""),
        )
        for tf in evidence_raw.get("top_flows", [])
    ]
    top_features = [
        TopFeature(
            name=feat.get("name", ""),
            value=feat.get("value", 0),
            direction=feat.get("direction", "high"),
        )
        for feat in evidence_raw.get("top_features", [])
    ]
    pcap_ref_raw = evidence_raw.get("pcap_ref")
    pcap_ref = PcapRef(**pcap_ref_raw) if pcap_ref_raw else None

    return AlertSchema(
        version=alert.version,
        id=alert.id,
        created_at=datetime_to_iso(alert.created_at),
        severity=alert.severity,  # type: ignore[arg-type]
        status=alert.status,  # type: ignore[arg-type]
        type=alert.type,  # type: ignore[arg-type],
        time_window=TimeWindow(
            start=datetime_to_iso(alert.time_window_start),
            end=datetime_to_iso(alert.time_window_end),
        ),
        entities=AlertEntities(
            primary_src_ip=alert.primary_src_ip,
            primary_dst_ip=alert.primary_dst_ip,
            primary_service=PrimaryService(
                proto=alert.primary_proto,
                dst_port=alert.primary_dst_port,
            ),
        ),
        evidence=AlertEvidence(
            flow_ids=evidence_raw.get("flow_ids", []),
            top_flows=top_flows,
            top_features=top_features,
            pcap_ref=pcap_ref,
        ),
        aggregation=AlertAggregation(
            rule=aggregation_raw.get("rule", ""),
            group_key=aggregation_raw.get("group_key", ""),
            count_flows=aggregation_raw.get("count_flows", 0),
            dimensions=aggregation_raw.get("dimensions"),
            composite_score=aggregation_raw.get("composite_score"),
            score_breakdown=aggregation_raw.get("score_breakdown"),
            type_reason=aggregation_raw.get("type_reason"),
            aggregation_summary=aggregation_raw.get("aggregation_summary"),
            type_summary=aggregation_raw.get("type_summary"),
            severity_summary=aggregation_raw.get("severity_summary"),
        ),
        agent=AlertAgent(
            triage_summary=agent_raw.get("triage_summary"),
            investigation_id=agent_raw.get("investigation_id"),
            recommendation_id=agent_raw.get("recommendation_id"),
        ),
        twin=AlertTwin(
            plan_id=twin_raw.get("plan_id"),
            dry_run_id=twin_raw.get("dry_run_id"),
        ),
        tags=tags_raw if isinstance(tags_raw, list) else [],
        notes=alert.notes or "",
    )


@router.get(
    "",
    response_model=ApiResponse[PaginatedData[AlertSchema]],
    summary="List Alerts",
    description="分页列出告警，支持多维度过滤。(DOC C C6.4)",
)
async def list_alerts(
    status: str | None = Query(default=None, description="按状态过滤"),
    severity: str | None = Query(default=None, description="按严重度过滤"),
    type: str | None = Query(default=None, description="按类型过滤"),
    start: str | None = Query(default=None, description="起始时间（ISO8601）"),
    end: str | None = Query(default=None, description="结束时间（ISO8601）"),
    limit: int = Query(default=50, ge=1, le=1000, description="最大返回条数"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
    db: Session = Depends(get_db),
) -> ApiResponse[PaginatedData[AlertSchema]]:
    conditions = []
    if status:
        conditions.append(Alert.status == status)
    if severity:
        conditions.append(Alert.severity == severity)
    if type:
        conditions.append(Alert.type == type)
    if start:
        conditions.append(Alert.time_window_start >= iso_to_datetime(start))
    if end:
        conditions.append(Alert.time_window_end <= iso_to_datetime(end))

    count_stmt = select(func.count()).select_from(Alert)
    data_stmt = select(Alert)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        data_stmt = data_stmt.where(cond)

    total = db.execute(count_stmt).scalar() or 0
    data_stmt = data_stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    alerts = db.execute(data_stmt).scalars().all()
    return ApiResponse.success(PaginatedData(
        items=[_alert_to_schema(a) for a in alerts],
        total=total,
        limit=limit,
        offset=offset,
    ))


@router.get(
    "/{alert_id}",
    response_model=ApiResponse[AlertSchema],
    summary="Get Alert Details",
    description="按 ID 查询单条告警详情。(DOC C C6.4)",
)
async def get_alert(
    alert_id: str = Path(..., description="告警 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertSchema]:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise NotFoundError(
            message=f"Alert not found: {alert_id}",
            details={"alert_id": alert_id},
        )
    return ApiResponse.success(_alert_to_schema(alert))


@router.patch(
    "/{alert_id}",
    response_model=ApiResponse[AlertSchema],
    summary="Update Alert",
    description="更新告警的状态、严重度、标签或备注。(DOC C C6.4)",
)
async def update_alert(
    alert_id: str = Path(..., description="告警 ID"),
    request: AlertUpdateRequest = Depends(),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertSchema]:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise NotFoundError(
            message=f"Alert not found: {alert_id}",
            details={"alert_id": alert_id},
        )

    if request.status is not None:
        alert.status = request.status
    if request.severity is not None:
        alert.severity = request.severity
    if request.tags is not None:
        alert.tags = json.dumps(request.tags)
    if request.notes is not None:
        alert.notes = request.notes

    db.commit()
    db.refresh(alert)

    # WS 广播以 fire-and-forget 方式触发，失败不应影响主请求
    try:
        from app.api.routers.stream import broadcast_alert_updated
        asyncio.create_task(broadcast_alert_updated(alert.id, alert.status))
    except Exception:
        pass

    return ApiResponse.success(_alert_to_schema(alert))
