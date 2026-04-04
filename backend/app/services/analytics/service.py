"""
标准化分析服务。
组合 DashboardService 的聚合逻辑，叠加评分层，
为 /api/v1/analytics/* 端点提供数据。
"""

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
from app.schemas.dashboard import TrendsSchema
from app.services.analytics.scorers.action_safety import ActionSafetyScorer
from app.services.analytics.scorers.posture_v2 import PostureScorerV2
from app.services.dashboard.service import DashboardService

logger = get_logger(__name__)
T = TypeVar("T")


class AnalyticsService:
    """
    标准化分析服务。
    内部持有 DashboardService 实例，复用其聚合方法，叠加评分逻辑。
    """

    def __init__(self, db: Session):
        self.db = db
        self._dashboard = DashboardService(db)

    # ------------------------------------------------------------------
    # 容错包装（复用同一模式）
    # ------------------------------------------------------------------

    def _safe_build(self, fn: Callable[[], T], default: T) -> T:
        """容错包装：捕获异常并返回默认值。"""
        try:
            return fn()
        except Exception as e:
            logger.warning(f"分析服务构建失败 [{fn.__name__}]: {e}")
            return default

    # ------------------------------------------------------------------
    # 总览（含评分）
    # ------------------------------------------------------------------

    def get_overview(self) -> AnalyticsOverviewSchema:
        """获取统一总览数据，内嵌态势评分和行动安全评分。"""
        overview = self._safe_build(
            self._dashboard._build_overview,
            self._dashboard._default_overview(),
        )
        posture = self._safe_build(
            lambda: self._compute_posture(overview), None
        )
        action_safety = self._safe_build(
            self._compute_action_safety, None
        )
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

    # ------------------------------------------------------------------
    # 独立评分 API
    # ------------------------------------------------------------------

    def get_posture_score(self) -> ScoreResultSchema:
        """获取安全态势评分（含因子分解与解释）。"""
        overview = self._safe_build(
            self._dashboard._build_overview,
            self._dashboard._default_overview(),
        )
        return self._compute_posture(overview)

    def get_action_safety_score(self) -> ScoreResultSchema:
        """获取行动安全评分（含因子分解与解释）。"""
        return self._safe_build(
            self._compute_action_safety,
            ActionSafetyScorer(self.db).compute(),
        )

    # ------------------------------------------------------------------
    # 委托方法（薄包装 + _safe_build 容错）
    # ------------------------------------------------------------------

    def get_trends(self) -> TrendsSchema:
        """获取告警趋势时序数据。"""
        return self._safe_build(
            self._dashboard._build_trends, TrendsSchema(days=[])
        )

    def get_distributions(self) -> DistributionsSchema:
        """获取告警类型/严重程度分布。"""
        return self._safe_build(
            self._dashboard._build_distributions, DistributionsSchema(items=[])
        )

    def get_topology_snapshot(self) -> TopologySnapshotSchema:
        """获取拓扑摘要快照。"""
        return self._safe_build(
            self._dashboard._build_topology_snapshot,
            self._dashboard._default_topology(),
        )

    def get_recent_activity(self) -> list[ActivityEventSchema]:
        """获取最近活动事件。"""
        return self._safe_build(self._dashboard._build_recent_activity, [])

    def get_top_assets(self) -> TopAssetsSchema:
        """获取高风险资产排行：复用拓扑快照 + 告警分布数据。"""
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
            for item in sorted(dist.items, key=lambda x: x.count, reverse=True)[
                :10
            ]
        ]

        return TopAssetsSchema(
            top_risk_nodes=top_nodes,
            top_risk_edges=top_edges,
            top_alert_types=top_alert_types,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _compute_action_safety(self) -> ScoreResultSchema:
        """从最新 dry-run 结果和决策数据计算行动安全评分。"""
        # 查询最新 dry-run 记录
        latest_dryrun = (
            self.db.query(DryRun)
            .order_by(DryRun.created_at.desc())
            .first()
        )

        if not latest_dryrun:
            # 无 dry-run 数据：所有组件不可用，返回满分（无动作 = 安全）
            return ActionSafetyScorer(self.db).compute()

        # 解析 payload JSON
        payload = json.loads(latest_dryrun.payload)
        impact = payload.get("impact", {})
        decision = payload.get("decision")

        # 提取 dry-run 影响数据
        kwargs: dict = {
            "service_disruption_risk": impact.get("service_disruption_risk"),
            "reachability_drop": impact.get("reachability_drop"),
            "impacted_nodes_count": impact.get("impacted_nodes_count"),
            "confidence": impact.get("confidence"),
        }

        # 提取拓扑节点总数（用于计算影响范围比例）
        topo = self._safe_build(
            self._dashboard._build_topology_snapshot,
            self._dashboard._default_topology(),
        )
        kwargs["total_node_count"] = topo.node_count if hasattr(topo, "node_count") else len(topo.top_risk_nodes)

        # 提取决策数据（可逆性 + 回退复杂度）
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
        """从 overview + 趋势 + 拓扑数据计算态势评分（v2 归一化风险指数）。"""
        # 获取趋势数据（容错）
        trends = self._safe_build(
            self._dashboard._build_trends, TrendsSchema(days=[])
        )
        # 获取拓扑快照（容错）
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
