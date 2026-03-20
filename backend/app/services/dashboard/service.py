"""
仪表盘聚合服务。
从现有 ORM 模型聚合所有仪表盘所需数据，不创建新表。
"""

import json
from datetime import timedelta
from typing import Any, Callable, TypeVar

from sqlalchemy import func
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
    OverviewSchema,
    PipelineSnapshotSchema,
    TopologySnapshotSchema,
    TrendDaySchema,
    TrendsSchema,
)

logger = get_logger(__name__)

T = TypeVar("T")

# 开放告警状态集合
_OPEN_STATUSES = {"new", "triaged", "investigating"}

# 严重程度列表（用于确保返回所有级别）
_SEVERITIES = ["low", "medium", "high", "critical"]

# 告警类型列表
_ALERT_TYPES = ["scan", "bruteforce", "dos", "anomaly", "exfil", "unknown"]


class DashboardService:
    """
    仪表盘聚合服务。

    从 pcap_files、flows、alerts、dry_runs、scenario_runs、pipeline_runs
    等现有表聚合数据，通过 _safe_build() 容错包装确保单个模块失败不影响整体响应。
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def get_summary(self) -> DashboardSummarySchema:
        """聚合所有仪表盘数据并返回。"""
        overview = self._safe_build(self._build_overview, self._default_overview())
        trends = self._safe_build(self._build_trends, TrendsSchema(days=[]))
        distributions = self._safe_build(
            self._build_distributions, DistributionsSchema(items=[])
        )
        topology_snapshot = self._safe_build(
            self._build_topology_snapshot, self._default_topology()
        )
        recent_activity = self._safe_build(self._build_recent_activity, [])

        return DashboardSummarySchema(
            overview=overview,
            trends=trends,
            distributions=distributions,
            topology_snapshot=topology_snapshot,
            recent_activity=recent_activity,
        )

    # ------------------------------------------------------------------
    # 容错包装
    # ------------------------------------------------------------------

    def _safe_build(self, fn: Callable[[], T], default: T) -> T:
        """
        容错包装：捕获异常并返回默认值，确保单个模块失败不影响整体响应。
        """
        try:
            return fn()
        except Exception as e:
            logger.warning(f"仪表盘构建失败 [{fn.__name__}]: {e}")
            return default

    # ------------------------------------------------------------------
    # 构建方法
    # ------------------------------------------------------------------

    def _build_overview(self) -> OverviewSchema:
        """
        构建总览指标。
        从 pcap_files、flows、alerts、dry_runs、scenario_runs、pipeline_runs 聚合。
        """
        now = utc_now()
        # 去掉时区信息以兼容 SQLite 存储的 naive datetime
        now_naive = now.replace(tzinfo=None)
        threshold_24h = now_naive - timedelta(hours=24)

        # ---- PCAP 指标 ----
        pcap_total = self.db.query(func.count(PcapFile.id)).scalar() or 0
        pcap_processing = (
            self.db.query(func.count(PcapFile.id))
            .filter(PcapFile.status == "processing")
            .scalar()
            or 0
        )
        pcap_24h_count = (
            self.db.query(func.count(PcapFile.id))
            .filter(PcapFile.created_at >= threshold_24h)
            .scalar()
            or 0
        )
        # 最后完成时间
        pcap_last_done_row = (
            self.db.query(PcapFile.created_at)
            .filter(PcapFile.status == "done")
            .order_by(PcapFile.created_at.desc())
            .first()
        )
        pcap_last_done_at = (
            datetime_to_iso(pcap_last_done_row[0]) if pcap_last_done_row else None
        )

        # ---- Flow 指标 ----
        flow_total = self.db.query(func.count(Flow.id)).scalar() or 0
        flow_24h_count = (
            self.db.query(func.count(Flow.id))
            .filter(Flow.created_at >= threshold_24h)
            .scalar()
            or 0
        )

        # ---- Alert 指标 ----
        alert_total = self.db.query(func.count(Alert.id)).scalar() or 0
        alert_open_count = (
            self.db.query(func.count(Alert.id))
            .filter(Alert.status.in_(list(_OPEN_STATUSES)))
            .scalar()
            or 0
        )

        # 按严重程度分组
        sev_rows = (
            self.db.query(Alert.severity, func.count(Alert.id))
            .group_by(Alert.severity)
            .all()
        )
        alert_by_severity: dict[str, int] = {s: 0 for s in _SEVERITIES}
        for sev, cnt in sev_rows:
            alert_by_severity[sev] = cnt

        # 按类型分组
        type_rows = (
            self.db.query(Alert.type, func.count(Alert.id))
            .group_by(Alert.type)
            .all()
        )
        alert_by_type: dict[str, int] = {t: 0 for t in _ALERT_TYPES}
        for atype, cnt in type_rows:
            alert_by_type[atype] = cnt

        # 最后分析时间（最新告警的创建时间）
        alert_last_row = (
            self.db.query(Alert.created_at)
            .order_by(Alert.created_at.desc())
            .first()
        )
        alert_last_analysis_at = (
            datetime_to_iso(alert_last_row[0]) if alert_last_row else None
        )

        # ---- Dry-Run 指标 ----
        dryrun_total = self.db.query(func.count(DryRun.id)).scalar() or 0
        dryrun_avg_disruption_risk = 0.0
        dryrun_last_result: dict[str, Any] | None = None

        if dryrun_total > 0:
            # 计算平均中断风险：从 payload JSON 中提取 service_disruption_risk
            dryruns = self.db.query(DryRun.payload).all()
            risks: list[float] = []
            for (payload_str,) in dryruns:
                risk = self._extract_disruption_risk(payload_str)
                if risk is not None:
                    risks.append(risk)
            if risks:
                dryrun_avg_disruption_risk = round(sum(risks) / len(risks), 4)

            # 最后一次 dry-run 的 impact 摘要
            last_dryrun = (
                self.db.query(DryRun.payload)
                .order_by(DryRun.created_at.desc())
                .first()
            )
            if last_dryrun:
                dryrun_last_result = self._extract_impact(last_dryrun[0])

        # ---- Scenario 指标 ----
        scenario_total = self.db.query(func.count(Scenario.id)).scalar() or 0
        scenario_last_status: str | None = None
        scenario_pass_rate = 0.0

        run_total = self.db.query(func.count(ScenarioRun.id)).scalar() or 0
        if run_total > 0:
            # 最后运行状态
            last_run = (
                self.db.query(ScenarioRun.status)
                .order_by(ScenarioRun.created_at.desc())
                .first()
            )
            scenario_last_status = last_run[0] if last_run else None

            # 通过率
            pass_count = (
                self.db.query(func.count(ScenarioRun.id))
                .filter(ScenarioRun.status == "pass")
                .scalar()
                or 0
            )
            scenario_pass_rate = round(pass_count / run_total, 4)

        # ---- Pipeline 指标 ----
        pipeline_last_run = self._build_pipeline_snapshot()

        # ---- 趋势数据（最近 7 天每日计数）----
        pcap_trend = self._query_daily_counts(PcapFile, PcapFile.created_at)
        flow_trend = self._query_daily_counts(Flow, Flow.created_at)
        alert_open_trend = self._query_open_alert_trend()

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
            pipeline_last_run=pipeline_last_run,
            pcap_trend=pcap_trend,
            flow_trend=flow_trend,
            alert_open_trend=alert_open_trend,
        )

    def _build_trends(self) -> TrendsSchema:
        """
        构建告警趋势数据。
        按最近 7 天分组，按 severity 细分。
        使用 SQLAlchemy func.date() 兼容 SQLite。
        """
        now_naive = utc_now().replace(tzinfo=None)
        seven_days_ago = now_naive - timedelta(days=7)

        # 按日期和严重程度分组查询
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

        # 按日期聚合
        day_map: dict[str, dict[str, int]] = {}
        for day_str, severity, cnt in rows:
            # func.date() 在 SQLite 中返回字符串 "YYYY-MM-DD"
            day_key = str(day_str)
            if day_key not in day_map:
                day_map[day_key] = {s: 0 for s in _SEVERITIES}
            day_map[day_key][severity] = cnt

        # 按日期排序后只保留最近 7 天（避免跨日历日边界导致超过 7 天）
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
        """
        构建告警类型分布数据。
        按 type 分组统计。
        """
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
        """
        构建迷你拓扑快照。
        复用 TopologyService.build_graph()，取 top-10 高风险节点/边。
        """
        from app.services.topology.service import TopologyService

        # 使用较大的时间窗口覆盖所有数据
        now = utc_now()
        start = now - timedelta(days=365)

        topo_service = TopologyService(self.db)
        graph = topo_service.build_graph(start=start, end=now, mode="ip")

        # 按 risk 降序排序，取 top-10 高风险节点
        sorted_nodes = sorted(graph.nodes, key=lambda n: n.risk, reverse=True)
        top_risk_nodes = [
            {"id": n.id, "label": n.label, "risk": round(n.risk, 4)}
            for n in sorted_nodes[:10]
        ]

        # 按 risk 降序排序，取 top-10 高风险边
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
        """
        构建最近活动事件列表。
        UNION 查询 pcap_files、pipeline_runs、alerts、dry_runs、scenario_runs，
        按 created_at DESC 排序取最近 20 条。
        """
        events: list[ActivityEventSchema] = []

        # ---- PCAP 上传事件 ----
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
                    summary="pcap_upload",
                    detail={
                        "filename": str(p.filename),
                        "status": str(p.status),
                        "size_bytes": str(p.size_bytes),
                    },
                    created_at=datetime_to_iso(p.created_at),
                )
            )

        # ---- 流水线运行事件 ----
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
                    summary="pipeline_run",
                    detail={
                        "pcap_id": str(pr.pcap_id),
                        "status": str(pr.status),
                    },
                    created_at=datetime_to_iso(pr.created_at),
                )
            )

        # ---- 告警创建事件 ----
        alert_rows = (
            self.db.query(Alert)
            .order_by(Alert.created_at.desc())
            .limit(20)
            .all()
        )
        for a in alert_rows:
            events.append(
                ActivityEventSchema(
                    id=a.id,
                    type="alert",
                    summary="alert_created",
                    detail={
                        "type": str(a.type),
                        "severity": str(a.severity),
                        "status": str(a.status),
                    },
                    created_at=datetime_to_iso(a.created_at),
                )
            )

        # ---- 推演执行事件 ----
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
                    summary="dryrun_executed",
                    detail={
                        "alert_id": str(dr.alert_id),
                        "plan_id": str(dr.plan_id),
                    },
                    created_at=datetime_to_iso(dr.created_at),
                )
            )

        # ---- 场景运行事件 ----
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
                    summary="scenario_run",
                    detail={
                        "scenario_id": str(sr.scenario_id),
                        "status": str(sr.status),
                    },
                    created_at=datetime_to_iso(sr.created_at),
                )
            )

        # 按 created_at 降序排序，取前 20 条
        events.sort(key=lambda e: e.created_at, reverse=True)
        return events[:20]

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _query_daily_counts(self, model, date_col, days=7):
        """通用：查询最近 N 天每日记录数，返回长度为 days 的 int 数组，缺失日期补 0"""
        now_naive = utc_now().replace(tzinfo=None)
        start = now_naive - timedelta(days=days)
        rows = (
            self.db.query(func.date(date_col), func.count())
            .filter(date_col >= start)
            .group_by(func.date(date_col))
            .all()
        )
        counts_map = {r[0]: r[1] for r in rows}
        result = []
        for i in range(days):
            day = (start + timedelta(days=i + 1)).strftime("%Y-%m-%d")
            result.append(counts_map.get(day, 0))
        return result

    def _query_open_alert_trend(self, days=7):
        """查询最近 N 天每日开放状态告警数，过滤 _OPEN_STATUSES，返回长度为 days 的 int 数组"""
        now_naive = utc_now().replace(tzinfo=None)
        start = now_naive - timedelta(days=days)
        rows = (
            self.db.query(func.date(Alert.created_at), func.count())
            .filter(Alert.created_at >= start)
            .filter(Alert.status.in_(list(_OPEN_STATUSES)))
            .group_by(func.date(Alert.created_at))
            .all()
        )
        counts_map = {r[0]: r[1] for r in rows}
        result = []
        for i in range(days):
            day = (start + timedelta(days=i + 1)).strftime("%Y-%m-%d")
            result.append(counts_map.get(day, 0))
        return result

    def _build_pipeline_snapshot(self) -> PipelineSnapshotSchema | None:
        """构建最后一次流水线运行快照。"""
        last_run = (
            self.db.query(PipelineRunModel)
            .order_by(PipelineRunModel.created_at.desc())
            .first()
        )
        if not last_run:
            return None

        # 解析 stages_log JSON
        stages: list[dict[str, Any]] = []
        failed_stages: list[str] = []
        if last_run.stages_log:
            try:
                stages = json.loads(last_run.stages_log)
                # 提取失败阶段
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
        """从 DryRun payload JSON 中提取 service_disruption_risk 值。"""
        try:
            payload = json.loads(payload_str)
            return payload.get("impact", {}).get("service_disruption_risk")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    @staticmethod
    def _extract_impact(payload_str: str) -> dict[str, Any] | None:
        """从 DryRun payload JSON 中提取 impact 摘要。"""
        try:
            payload = json.loads(payload_str)
            return payload.get("impact")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    # ------------------------------------------------------------------
    # 默认值工厂（空数据库时使用）
    # ------------------------------------------------------------------

    @staticmethod
    def _default_overview() -> OverviewSchema:
        """返回空数据库时的默认总览指标。"""
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
            pipeline_last_run=None,
            pcap_trend=[0] * 7,
            flow_trend=[0] * 7,
            alert_open_trend=[0] * 7,
        )

    @staticmethod
    def _default_topology() -> TopologySnapshotSchema:
        """返回空数据库时的默认拓扑快照。"""
        return TopologySnapshotSchema(
            node_count=0,
            edge_count=0,
            top_risk_nodes=[],
            top_risk_edges=[],
        )
