import json
from datetime import timedelta
from typing import Any, Callable, TypeVar

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import datetime_to_iso, utc_now
from app.models.alert import Alert
from app.models.flow import Flow
from app.models.pcap import PcapFile
from app.models.pipeline import PipelineRunModel
from app.models.scenario import Scenario, ScenarioRun
from app.models.twin import DryRun
from app.schemas.dashboard import (
    ActivityEventSchema,
    DashboardSummarySchema,
    DistributionItemSchema,
    DistributionsSchema,
    MetricSparklinesSchema,
    OverviewSchema,
    PipelineSnapshotSchema,
    TopologySnapshotSchema,
    TrendDaySchema,
    TrendsSchema,
)

logger = get_logger(__name__)

T = TypeVar("T")

_OPEN_STATUSES = {"new", "triaged", "investigating"}
_SEVERITIES = ["low", "medium", "high", "critical"]
_ALERT_TYPES = ["scan", "bruteforce", "dos", "anomaly", "exfil", "unknown"]

_COUNTS_SQL = text("""
    SELECT
        (SELECT COUNT(*) FROM pcap_files) AS pcap_total,
        (SELECT COUNT(*) FROM pcap_files WHERE status = 'processing') AS pcap_processing,
        (SELECT COUNT(*) FROM pcap_files WHERE created_at >= :t) AS pcap_24h,
        (SELECT COUNT(*) FROM flows) AS flow_total,
        (SELECT COUNT(*) FROM flows WHERE created_at >= :t) AS flow_24h,
        (SELECT COUNT(*) FROM alerts) AS alert_total,
        (SELECT COUNT(*) FROM alerts WHERE status IN ('open', 'investigating')) AS alert_open
""")


class DashboardService:
    """Aggregates all dashboard data from existing tables. Errors in any
    single module are swallowed by _safe_build so the overall response stays intact."""

    def __init__(self, db: Session):
        self.db = db

    def get_summary(self) -> DashboardSummarySchema:
        overview = self._safe_build(self._build_overview, self._default_overview())
        trends = self._safe_build(self._build_trends, TrendsSchema(days=[]))
        distributions = self._safe_build(
            self._build_distributions, DistributionsSchema(items=[])
        )
        topology_snapshot = self._safe_build(
            self._build_topology_snapshot, self._default_topology()
        )
        recent_activity = self._safe_build(self._build_recent_activity, [])
        metric_sparklines = self._safe_build(
            self._build_metric_sparklines,
            MetricSparklinesSchema(
                pcap_trend=[0] * 7,
                flow_trend=[0] * 7,
                alert_open_trend=[0] * 7,
            ),
        )

        return DashboardSummarySchema(
            overview=overview,
            trends=trends,
            distributions=distributions,
            topology_snapshot=topology_snapshot,
            recent_activity=recent_activity,
            metric_sparklines=metric_sparklines,
        )

    def _safe_build(self, fn: Callable[[], T], default: T) -> T:
        try:
            return fn()
        except Exception as e:
            logger.warning(f"仪表盘构建失败 [{fn.__name__}]: {e}")
            return default

    def _build_overview(self) -> OverviewSchema:
        now = utc_now()
        threshold_24h = now - timedelta(hours=24)

        counts = self.db.execute(_COUNTS_SQL, {"t": threshold_24h}).first()
        pcap_total = counts[0] or 0
        pcap_processing = counts[1] or 0
        pcap_24h_count = counts[2] or 0
        flow_total = counts[3] or 0
        flow_24h_count = counts[4] or 0
        alert_total = counts[5] or 0
        alert_open_count = counts[6] or 0

        pcap_last_done_row = (
            self.db.query(PcapFile.created_at)
            .filter(PcapFile.status == "done")
            .order_by(PcapFile.created_at.desc())
            .first()
        )
        pcap_last_done_at = (
            datetime_to_iso(pcap_last_done_row[0]) if pcap_last_done_row else None
        )

        sev_rows = (
            self.db.query(Alert.severity, func.count(Alert.id))
            .group_by(Alert.severity)
            .all()
        )
        alert_by_severity: dict[str, int] = {s: 0 for s in _SEVERITIES}
        for sev, cnt in sev_rows:
            alert_by_severity[sev] = cnt

        type_rows = (
            self.db.query(Alert.type, func.count(Alert.id))
            .group_by(Alert.type)
            .all()
        )
        alert_by_type: dict[str, int] = {t: 0 for t in _ALERT_TYPES}
        for atype, cnt in type_rows:
            alert_by_type[atype] = cnt

        pipeline_completed_row = (
            self.db.query(PipelineRunModel.created_at)
            .filter(PipelineRunModel.status == "completed")
            .order_by(PipelineRunModel.created_at.desc())
            .first()
        )
        if pipeline_completed_row:
            alert_last_analysis_at = datetime_to_iso(pipeline_completed_row[0])
        else:
            alert_last_row = (
                self.db.query(Alert.created_at)
                .order_by(Alert.created_at.desc())
                .first()
            )
            alert_last_analysis_at = (
                datetime_to_iso(alert_last_row[0]) if alert_last_row else None
            )

        dryrun_total = self.db.query(func.count(DryRun.id)).scalar() or 0
        dryrun_avg_disruption_risk = 0.0
        dryrun_last_result: dict[str, Any] | None = None

        if dryrun_total > 0:
            dryruns = self.db.query(DryRun.payload).all()
            risks: list[float] = []
            for (payload_str,) in dryruns:
                risk = self._extract_disruption_risk(payload_str)
                if risk is not None:
                    risks.append(risk)
            if risks:
                dryrun_avg_disruption_risk = round(sum(risks) / len(risks), 4)

            last_dryrun = (
                self.db.query(DryRun.payload)
                .order_by(DryRun.created_at.desc())
                .first()
            )
            if last_dryrun:
                dryrun_last_result = self._extract_impact(last_dryrun[0])

        scenario_total = self.db.query(func.count(Scenario.id)).scalar() or 0
        scenario_last_status: str | None = None
        scenario_pass_rate = 0.0

        run_total = self.db.query(func.count(ScenarioRun.id)).scalar() or 0
        if run_total > 0:
            last_run = (
                self.db.query(ScenarioRun.status)
                .order_by(ScenarioRun.created_at.desc())
                .first()
            )
            scenario_last_status = last_run[0] if last_run else None

            pass_count = (
                self.db.query(func.count(ScenarioRun.id))
                .filter(ScenarioRun.status == "pass")
                .scalar()
                or 0
            )
            scenario_pass_rate = round(pass_count / run_total, 4)

        return OverviewSchema(
            pcap_total=pcap_total,
            pcap_processing=pcap_processing,
            pcap_last_done_at=pcap_last_done_at,
            pcap_24h_count=pcap_24h_count,
            flow_total=flow_total,
            flow_24h_count=flow_24h_count,
            alert_total=alert_total,
            alert_open_count=alert_open_count,
            alert_by_severity=alert_by_severity,
            alert_by_type=alert_by_type,
            alert_last_analysis_at=alert_last_analysis_at,
            dryrun_total=dryrun_total,
            dryrun_avg_disruption_risk=dryrun_avg_disruption_risk,
            dryrun_last_result=dryrun_last_result,
            scenario_total=scenario_total,
            scenario_last_status=scenario_last_status,
            scenario_pass_rate=scenario_pass_rate,
            scenario_run_total=run_total,
            pipeline_last_run=self._build_pipeline_snapshot(),
        )

    def _build_trends(self) -> TrendsSchema:
        seven_days_ago = utc_now() - timedelta(days=7)

        rows = (
            self.db.query(
                func.date(Alert.created_at).label("day"),
                Alert.severity,
                func.count(Alert.id).label("cnt"),
            )
            .filter(Alert.created_at >= seven_days_ago)
            .group_by(func.date(Alert.created_at), Alert.severity)
            .order_by(func.date(Alert.created_at))
            .all()
        )

        day_map: dict[str, dict[str, int]] = {}
        for day_str, severity, cnt in rows:
            day_key = str(day_str)  
            if day_key not in day_map:
                day_map[day_key] = {s: 0 for s in _SEVERITIES}
            day_map[day_key][severity] = cnt

        sorted_items = sorted(day_map.items())[-7:]

        days = [
            TrendDaySchema(
                date=day_key,
                low=sev_counts.get("low", 0),
                medium=sev_counts.get("medium", 0),
                high=sev_counts.get("high", 0),
                critical=sev_counts.get("critical", 0),
            )
            for day_key, sev_counts in sorted_items
        ]

        return TrendsSchema(days=days)

    def _build_distributions(self) -> DistributionsSchema:
        rows = (
            self.db.query(Alert.type, func.count(Alert.id))
            .group_by(Alert.type)
            .all()
        )

        type_counts: dict[str, int] = {t: 0 for t in _ALERT_TYPES}
        for atype, cnt in rows:
            type_counts[atype] = cnt

        items = [
            DistributionItemSchema(type=atype, count=count)
            for atype, count in type_counts.items()
            if count > 0
        ]

        return DistributionsSchema(items=items)

    def _build_topology_snapshot(self) -> TopologySnapshotSchema:
        from app.services.topology.service import TopologyService

        now = utc_now()
        start = now - timedelta(days=365) 

        graph = TopologyService(self.db).build_graph(start=start, end=now, mode="ip")

        sorted_nodes = sorted(graph.nodes, key=lambda n: n.risk, reverse=True)
        top_risk_nodes = [
            {"id": n.id, "label": n.label, "risk": round(n.risk, 4)}
            for n in sorted_nodes[:10]
        ]

        sorted_edges = sorted(graph.edges, key=lambda e: e.risk, reverse=True)
        top_risk_edges = [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "risk": round(e.risk, 4),
            }
            for e in sorted_edges[:10]
        ]

        return TopologySnapshotSchema(
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            top_risk_nodes=top_risk_nodes,
            top_risk_edges=top_risk_edges,
        )

    def _build_recent_activity(self) -> list[ActivityEventSchema]:
        """Pulls the latest 20 events across pcap/pipeline/alert/dryrun/scenario."""
        events: list[ActivityEventSchema] = []

        pcap_rows = (
            self.db.query(PcapFile)
            .order_by(PcapFile.created_at.desc())
            .limit(20)
            .all()
        )
        for p in pcap_rows:
            events.append(
                ActivityEventSchema(
                    id=p.id,
                    type="pcap",
                    kind="created",
                    entity_type="pcap",
                    entity_id=str(p.id),
                    summary="pcap.created",
                    payload={
                        "filename": str(p.filename),
                        "size_bytes": p.size_bytes if p.size_bytes is not None else 0,
                    },
                    href="/pcaps",
                    detail={
                        "kind": "created",
                        "entity_type": "pcap",
                        "entity_id": p.id,
                        "filename": str(p.filename),
                        "status": str(p.status),
                        "size_bytes": p.size_bytes,
                    },
                    created_at=datetime_to_iso(p.created_at),
                )
            )

        pipeline_rows = (
            self.db.query(PipelineRunModel)
            .order_by(PipelineRunModel.created_at.desc())
            .limit(20)
            .all()
        )
        for pr in pipeline_rows:
            events.append(
                ActivityEventSchema(
                    id=pr.id,
                    type="pipeline",
                    kind="completed",
                    entity_type="pipeline",
                    entity_id=str(pr.id),
                    summary="pipeline.completed",
                    payload={
                        "pcap_id": str(pr.pcap_id),
                        "status": str(pr.status),
                    },
                    href="/pcaps",
                    detail={
                        "kind": pr.status,
                        "entity_type": "pipeline",
                        "entity_id": pr.id,
                        "pcap_id": str(pr.pcap_id),
                        "status": str(pr.status),
                    },
                    created_at=datetime_to_iso(pr.created_at),
                )
            )

        alert_rows = (
            self.db.query(Alert)
            .order_by(Alert.created_at.desc())
            .limit(20)
            .all()
        )
        for a in alert_rows:
            entity_id = str(a.id)
            events.append(
                ActivityEventSchema(
                    id=a.id,
                    type="alert",
                    kind="created",
                    entity_type="alert",
                    entity_id=entity_id,
                    summary="alert.created",
                    payload={
                        "alert_type": str(a.type),
                        "severity": str(a.severity),
                    },
                    href=f"/alerts/{entity_id}",
                    detail={
                        "kind": "created",
                        "entity_type": "alert",
                        "entity_id": a.id,
                        "type": str(a.type),
                        "severity": str(a.severity),
                        "status": str(a.status),
                    },
                    created_at=datetime_to_iso(a.created_at),
                )
            )

        dryrun_rows = (
            self.db.query(DryRun)
            .order_by(DryRun.created_at.desc())
            .limit(20)
            .all()
        )
        for dr in dryrun_rows:
            events.append(
                ActivityEventSchema(
                    id=dr.id,
                    type="dryrun",
                    kind="executed",
                    entity_type="dryrun",
                    entity_id=str(dr.id),
                    summary="dryrun.executed",
                    payload={
                        "alert_id": str(dr.alert_id),
                        "plan_id": str(dr.plan_id),
                    },
                    href="/alerts",
                    detail={
                        "kind": "executed",
                        "entity_type": "dryrun",
                        "entity_id": dr.id,
                        "alert_id": str(dr.alert_id),
                        "plan_id": str(dr.plan_id),
                    },
                    created_at=datetime_to_iso(dr.created_at),
                )
            )

        scenario_run_rows = (
            self.db.query(ScenarioRun)
            .order_by(ScenarioRun.created_at.desc())
            .limit(20)
            .all()
        )
        for sr in scenario_run_rows:
            events.append(
                ActivityEventSchema(
                    id=sr.id,
                    type="scenario",
                    kind="executed",
                    entity_type="scenario",
                    entity_id=str(sr.id),
                    summary="scenario.executed",
                    payload={
                        "scenario_id": str(sr.scenario_id),
                        "status": str(sr.status),
                    },
                    href="/scenarios",
                    detail={
                        "kind": "executed",
                        "entity_type": "scenario",
                        "entity_id": sr.id,
                        "scenario_id": str(sr.scenario_id),
                        "status": str(sr.status),
                    },
                    created_at=datetime_to_iso(sr.created_at),
                )
            )

        events.sort(key=lambda e: e.created_at, reverse=True)
        return events[:20]

    def _build_metric_sparklines(self) -> MetricSparklinesSchema:
        return MetricSparklinesSchema(
            pcap_trend=self._query_daily_counts(PcapFile, PcapFile.created_at),
            flow_trend=self._query_daily_counts(Flow, Flow.created_at),
            alert_open_trend=self._query_open_alert_trend(),
        )

    def _query_daily_counts(self, model, date_col, days=7):
        start = utc_now() - timedelta(days=days)
        rows = (
            self.db.query(func.date(date_col), func.count())
            .filter(date_col >= start)
            .group_by(func.date(date_col))
            .all()
        )
        counts_map = {r[0]: r[1] for r in rows}
        return [
            counts_map.get((start + timedelta(days=i + 1)).strftime("%Y-%m-%d"), 0)
            for i in range(days)
        ]

    def _query_open_alert_trend(self, days=7):
        start = utc_now() - timedelta(days=days)
        rows = (
            self.db.query(func.date(Alert.created_at), func.count())
            .filter(Alert.created_at >= start)
            .filter(Alert.status.in_(list(_OPEN_STATUSES)))
            .group_by(func.date(Alert.created_at))
            .all()
        )
        counts_map = {r[0]: r[1] for r in rows}
        return [
            counts_map.get((start + timedelta(days=i + 1)).strftime("%Y-%m-%d"), 0)
            for i in range(days)
        ]

    def _build_pipeline_snapshot(self) -> PipelineSnapshotSchema | None:
        last_run = (
            self.db.query(PipelineRunModel)
            .order_by(PipelineRunModel.created_at.desc())
            .first()
        )
        if not last_run:
            return None

        stages: list[dict[str, Any]] = []
        failed_stages: list[str] = []
        if last_run.stages_log:
            try:
                stages = json.loads(last_run.stages_log)
                for stage in stages:
                    if isinstance(stage, dict) and stage.get("status") == "failed":
                        stage_name = stage.get("name", stage.get("stage", "unknown"))
                        failed_stages.append(stage_name)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"流水线 stages_log JSON 解析失败: {last_run.id}")

        return PipelineSnapshotSchema(
            id=last_run.id,
            pcap_id=last_run.pcap_id,
            status=last_run.status,
            stages=stages,
            total_latency_ms=last_run.total_latency_ms,
            failed_stages=failed_stages,
        )

    @staticmethod
    def _extract_disruption_risk(payload_str: str) -> float | None:
        try:
            payload = json.loads(payload_str)
            return payload.get("impact", {}).get("service_disruption_risk")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    @staticmethod
    def _extract_impact(payload_str: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(payload_str)
            return payload.get("impact")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    @staticmethod
    def _default_overview() -> OverviewSchema:
        return OverviewSchema(
            pcap_total=0,
            pcap_processing=0,
            pcap_last_done_at=None,
            pcap_24h_count=0,
            flow_total=0,
            flow_24h_count=0,
            alert_total=0,
            alert_open_count=0,
            alert_by_severity={s: 0 for s in _SEVERITIES},
            alert_by_type={t: 0 for t in _ALERT_TYPES},
            alert_last_analysis_at=None,
            dryrun_total=0,
            dryrun_avg_disruption_risk=0.0,
            dryrun_last_result=None,
            scenario_total=0,
            scenario_last_status=None,
            scenario_pass_rate=0.0,
            scenario_run_total=0,
            pipeline_last_run=None,
        )

    @staticmethod
    def _default_topology() -> TopologySnapshotSchema:
        return TopologySnapshotSchema(
            node_count=0,
            edge_count=0,
            top_risk_nodes=[],
            top_risk_edges=[],
        )
