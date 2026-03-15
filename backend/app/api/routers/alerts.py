"""
Alerts router.
GET /alerts, GET /alerts/{alert_id}, PATCH /alerts/{alert_id}
Implements DOC C C6.4.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.core.utils import datetime_to_iso, iso_to_datetime
from app.models.alert import Alert
from app.schemas.common import ApiResponse
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


# ---------- helper: ORM → Pydantic ----------

def _parse_json(text: str, fallback=None):
    """Safely parse a JSON TEXT column."""
    if not text:
        return fallback if fallback is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else {}


def _alert_to_schema(alert: Alert) -> AlertSchema:
    """Convert Alert ORM to AlertSchema (DOC C C1.3)."""
    evidence_raw = _parse_json(alert.evidence, {})
    aggregation_raw = _parse_json(alert.aggregation, {})
    agent_raw = _parse_json(alert.agent, {})
    twin_raw = _parse_json(alert.twin, {})
    tags_raw = _parse_json(alert.tags, [])

    # Build nested evidence
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


# ---------- endpoints ----------

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
    """List alert records with optional filters."""
    stmt = select(Alert)

    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if type:
        stmt = stmt.where(Alert.type == type)
    if start:
        stmt = stmt.where(Alert.time_window_start >= iso_to_datetime(start))
    if end:
        stmt = stmt.where(Alert.time_window_end <= iso_to_datetime(end))

    stmt = stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    alerts = db.execute(stmt).scalars().all()
    return ApiResponse.success([_alert_to_schema(a) for a in alerts])


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
    """Get alert by ID with full evidence/top_flows/top_features."""
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
    description="Update alert status, severity, tags, or notes. (DOC C C6.4)",
)
async def update_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: AlertUpdateRequest = Depends(),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertSchema]:
    """
    Partial update of alert fields.
    Broadcasts WS alert.updated on success.
    """
    alert = db.get(Alert, alert_id)
    if not alert:
        raise NotFoundError(
            message=f"Alert not found: {alert_id}",
            details={"alert_id": alert_id},
        )

    # Apply partial updates
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

    # WS broadcast alert.updated (fire-and-forget via EventBus)
    try:
        from app.api.routers.stream import broadcast_alert_updated
        asyncio.create_task(broadcast_alert_updated(alert.id, alert.status))
    except Exception:
        pass

    return ApiResponse.success(_alert_to_schema(alert))
