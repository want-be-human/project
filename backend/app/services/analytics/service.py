"""
标准化分析服务。
组合 DashboardService 的聚合逻辑，叠加评分层，
为 /api/v1/analytics/* 端点提供数据。
"""

from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.core.logging import get_logger
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
from app.services.analytics.scorers.posture import PostureScorer
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
        """获取统一总览数据，内嵌态势评分。"""
        overview = self._safe_build(
            self._dashboard._build_overview,
            self._dashboard._default_overview(),
        )
        posture = self._safe_build(
            lambda: self._compute_posture(overview), None
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
        """获取行动安全评分（占位）。"""
        scorer = ActionSafetyScorer(self.db)
        return scorer.compute()

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

    def _compute_posture(self, overview) -> ScoreResultSchema:
        """从 overview 数据计算态势评分，供 get_overview 和 get_posture_score 共享。"""
        scorer = PostureScorer(self.db)
        return scorer.compute(
            critical_count=overview.alert_by_severity.get("critical", 0),
            high_count=overview.alert_by_severity.get("high", 0),
            open_count=overview.alert_open_count,
            avg_disruption_risk=overview.dryrun_avg_disruption_risk,
        )
