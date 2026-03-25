"""
PlanCompilerService 编排层。
从数据库获取所需数据，调用 PlanCompiler，并通过
TwinService.create_plan() 持久化结果。
"""

import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.evidence import EvidenceChain
from app.models.investigation import Investigation
from app.models.recommendation import Recommendation
from app.schemas.agent import InvestigationSchema, RecommendationSchema
from app.schemas.evidence import EvidenceChainSchema
from app.schemas.twin import (
    CompilePlanResponse,
    CompilationMetadata,
)
from app.services.plan_compiler.compiler import PlanCompiler
from app.services.twin.service import TwinService

logger = get_logger(__name__)


class PlanCompilerService:
    """
    负责编排 recommendation 到 plan 的编译流程。

    用法：
        service = PlanCompilerService(db)
        response = service.compile_for_alert(alert_id)
    """

    def __init__(self, db: Session):
        self.db = db
        self._compiler = PlanCompiler()

    def compile_for_alert(
        self,
        alert_id: str,
        recommendation_id: str | None = None,
        language: str = "en",
    ) -> CompilePlanResponse:
        """
        将 recommendation 编译为 Twin ActionPlan。

        参数：
            alert_id: 要编译的告警 ID。
            recommendation_id: 指定 recommendation（为空时取最新）。
            language: 推理摘要语言。

        返回：
            包含已创建计划及编译元数据的 CompilePlanResponse。

        异常：
            ValueError: 当 alert 或 recommendation 不存在时抛出。
        """
        # 获取 alert
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        # 获取 recommendation
        recommendation = self._load_recommendation(alert_id, recommendation_id)

        # 获取 investigation（可选）
        investigation = self._load_investigation(alert_id)

        # 获取 evidence chain（可选）
        evidence_chain = self._load_evidence_chain(alert_id)

        # 编译
        compiled_actions, skipped_details = self._compiler.compile(
            alert=alert,
            recommendation=recommendation,
            investigation=investigation,
            evidence_chain=evidence_chain,
            language=language,
        )

        # 生成包含编译信息的 notes
        notes = (
            f"Auto-compiled from recommendation {recommendation.id}. "
            f"{len(compiled_actions)} actions compiled, {len(skipped_details)} skipped."
        )

        # 通过 TwinService 创建 plan（复用既有持久化逻辑）
        twin_service = TwinService(self.db)
        plan = twin_service.create_plan(
            alert_id=alert_id,
            actions=compiled_actions,
            source="agent",
            notes=notes,
        )

        all_skipped = len(compiled_actions) == 0 and len(skipped_details) > 0
        empty_reason = None
        if all_skipped:
            if language == "zh":
                empty_reason = "所有推荐动作均为监控/建议类，无法编译为可执行操作。"
            else:
                empty_reason = (
                    "All recommended actions are monitoring/advisory type "
                    "and cannot be compiled into executable operations."
                )

        metadata = CompilationMetadata(
            recommendation_id=recommendation.id,
            rules_matched=len(compiled_actions),
            actions_skipped=len(skipped_details),
            compiler_version="1.1",
            skipped_actions=skipped_details,
            all_skipped=all_skipped,
            empty_reason=empty_reason,
        )

        logger.info(
            "Compiled plan %s for alert %s from recommendation %s",
            plan.id,
            alert_id,
            recommendation.id,
        )
        return CompilePlanResponse(plan=plan, compilation=metadata)

    def _load_recommendation(
        self, alert_id: str, recommendation_id: str | None
    ) -> RecommendationSchema:
        """加载指定或最新的 recommendation。"""
        if recommendation_id:
            rec = (
                self.db.query(Recommendation)
                .filter(Recommendation.id == recommendation_id)
                .first()
            )
        else:
            rec = (
                self.db.query(Recommendation)
                .filter(Recommendation.alert_id == alert_id)
                .order_by(Recommendation.created_at.desc())
                .first()
            )

        if not rec:
            raise ValueError(
                f"No recommendation found for alert {alert_id}"
                + (f" with id {recommendation_id}" if recommendation_id else "")
            )

        payload = json.loads(rec.payload) if isinstance(rec.payload, str) else rec.payload
        return RecommendationSchema(**payload)

    def _load_investigation(self, alert_id: str) -> InvestigationSchema | None:
        """加载该告警的最新 investigation（可选）。"""
        inv = (
            self.db.query(Investigation)
            .filter(Investigation.alert_id == alert_id)
            .order_by(Investigation.created_at.desc())
            .first()
        )
        if not inv:
            return None

        payload = json.loads(inv.payload) if isinstance(inv.payload, str) else inv.payload
        return InvestigationSchema(**payload)

    def _load_evidence_chain(self, alert_id: str) -> EvidenceChainSchema | None:
        """加载该告警的最新 evidence chain（可选）。"""
        ec = (
            self.db.query(EvidenceChain)
            .filter(EvidenceChain.alert_id == alert_id)
            .order_by(EvidenceChain.created_at.desc())
            .first()
        )
        if not ec:
            return None

        payload = json.loads(ec.payload) if isinstance(ec.payload, str) else ec.payload
        return EvidenceChainSchema(**payload)
