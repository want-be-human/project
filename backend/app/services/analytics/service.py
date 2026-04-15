import json
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.twin import DryRun
from app.schemas.analytics import (
    AnalyticsOverviewSchema,
    ScoreResultSchema,
    TopAssetItemSchema,
    TopAssetsSchema,
)
from app.schemas.dashboard import (
    ActivityEventSchema,
    DistributionsSchema,
    TopologySnapshotSchema,
    TrendsSchema,
)
from app.services.analytics.scorers.action_safety import ActionSafetyScorer
from app.services.analytics.scorers.posture_v2 import PostureScorerV2
from app.services.dashboard.service import DashboardService

logger = get_logger(__name__)
T = TypeVar("T")


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self._dashboard = DashboardService(db)

    def _safe_build(self, fn: Callable[[], T], default: T) -> T:
        try:
            return fn()
        except Exception as e:
            logger.warning(f"分析服务构建失败 [{fn.__name__}]: {e}")
            return default

    def get_overview(self) -> AnalyticsOverviewSchema:
        overview = self._safe_build(
            self._dashboard._build_overview,
            self._dashboard._default_overview(),
        )
        posture = self._safe_build(lambda: self._compute_posture(overview), None)
        action_safety = self._safe_build(self._compute_action_safety, None)
        return AnalyticsOverviewSchema(
            pcap_total=overview.pcap_total,
            pcap_processing=overview.pcap_processing,
            pcap_24h_count=overview.pcap_24h_count,
            flow_total=overview.flow_total,
            flow_24h_count=overview.flow_24h_count,
            alert_total=overview.alert_total,
            alert_open_count=overview.alert_open_count,
            alert_by_severity=overview.alert_by_severity,
            dryrun_total=overview.dryrun_total,
            dryrun_avg_disruption_risk=overview.dryrun_avg_disruption_risk,
            scenario_total=overview.scenario_total,
            scenario_pass_rate=overview.scenario_pass_rate,
            posture_score=posture,
            action_safety_score=action_safety,
        )

    def get_posture_score(self) -> ScoreResultSchema:
        overview = self._safe_build(
            self._dashboard._build_overview,
            self._dashboard._default_overview(),
        )
        return self._compute_posture(overview)

    def get_action_safety_score(self) -> ScoreResultSchema:
        return self._safe_build(
            self._compute_action_safety,
            ActionSafetyScorer(self.db).compute(),
        )

    def get_trends(self) -> TrendsSchema:
        return self._safe_build(self._dashboard._build_trends, TrendsSchema(days=[]))

    def get_distributions(self) -> DistributionsSchema:
        return self._safe_build(
            self._dashboard._build_distributions, DistributionsSchema(items=[])
        )

    def get_topology_snapshot(self) -> TopologySnapshotSchema:
        return self._safe_build(
            self._dashboard._build_topology_snapshot,
            self._dashboard._default_topology(),
        )

    def get_recent_activity(self) -> list[ActivityEventSchema]:
        return self._safe_build(self._dashboard._build_recent_activity, [])

    def get_top_assets(self) -> TopAssetsSchema:
        topo = self.get_topology_snapshot()
        dist = self.get_distributions()

        top_nodes = [
            TopAssetItemSchema(
                id=n["id"], label=n["label"], risk=n["risk"], category="node"
            )
            for n in topo.top_risk_nodes[:10]
        ]
        top_edges = [
            TopAssetItemSchema(
                id=e["id"],
                label=f"{e['source']}→{e['target']}",
                risk=e["risk"],
                category="edge",
            )
            for e in topo.top_risk_edges[:10]
        ]
        top_alert_types = [
            {"type": item.type, "count": item.count}
            for item in sorted(dist.items, key=lambda x: x.count, reverse=True)[:10]
        ]

        return TopAssetsSchema(
            top_risk_nodes=top_nodes,
            top_risk_edges=top_edges,
            top_alert_types=top_alert_types,
        )

    def _compute_action_safety(self) -> ScoreResultSchema:
        latest_dryrun = (
            self.db.query(DryRun).order_by(DryRun.created_at.desc()).first()
        )

        if not latest_dryrun:
            return ActionSafetyScorer(self.db).compute()

        payload = json.loads(latest_dryrun.payload)
        impact = payload.get("impact", {})
        decision = payload.get("decision")

        kwargs: dict = {
            "service_disruption_risk": impact.get("service_disruption_risk"),
            "reachability_drop": impact.get("reachability_drop"),
            "impacted_nodes_count": impact.get("impacted_nodes_count"),
            "confidence": impact.get("confidence"),
        }

        topo = self._safe_build(
            self._dashboard._build_topology_snapshot,
            self._dashboard._default_topology(),
        )
        kwargs["total_node_count"] = (
            topo.node_count if hasattr(topo, "node_count") else len(topo.top_risk_nodes)
        )

        if decision:
            rec = decision.get("recommended_action", {})
            action = rec.get("action", {})
            kwargs["reversible"] = action.get("reversible")
            kwargs["recovery_cost"] = action.get("estimated_recovery_cost")

            rollback = decision.get("rollback_plan", {})
            if rollback and rollback.get("rollback_supported"):
                kwargs["rollback_complexity"] = rollback.get("rollback_complexity")
                kwargs["rollback_risk"] = rollback.get("rollback_risk")

        return ActionSafetyScorer(self.db).compute(**kwargs)

    def _compute_posture(self, overview) -> ScoreResultSchema:
        trends = self._safe_build(self._dashboard._build_trends, TrendsSchema(days=[]))
        topo = self._safe_build(
            self._dashboard._build_topology_snapshot,
            self._dashboard._default_topology(),
        )

        scorer = PostureScorerV2(self.db)
        return scorer.compute(
            alert_by_severity=overview.alert_by_severity,
            alert_total=overview.alert_total,
            alert_open_count=overview.alert_open_count,
            trend_days=trends.days,
            top_risk_nodes=topo.top_risk_nodes,
            dryrun_avg_disruption_risk=overview.dryrun_avg_disruption_risk,
            dryrun_total=overview.dryrun_total,
        )
