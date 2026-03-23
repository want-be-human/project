"""
PlanCompilerService – orchestration layer.
Fetches required data from DB, invokes PlanCompiler, and persists the result
via TwinService.create_plan().
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
    Orchestrates recommendation → plan compilation.

    Usage:
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
        Compile a recommendation into a Twin ActionPlan.

        Args:
            alert_id: Alert to compile for.
            recommendation_id: Specific recommendation (latest if None).
            language: Language for reasoning summaries.

        Returns:
            CompilePlanResponse with the created plan and compilation metadata.

        Raises:
            ValueError: If alert or recommendation not found.
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
        compiled_actions, skipped = self._compiler.compile(
            alert=alert,
            recommendation=recommendation,
            investigation=investigation,
            evidence_chain=evidence_chain,
            language=language,
        )

        # 生成包含编译信息的 notes
        notes = (
            f"Auto-compiled from recommendation {recommendation.id}. "
            f"{len(compiled_actions)} actions compiled, {skipped} skipped."
        )

        # 通过 TwinService 创建 plan（复用既有持久化逻辑）
        twin_service = TwinService(self.db)
        plan = twin_service.create_plan(
            alert_id=alert_id,
            actions=compiled_actions,
            source="agent",
            notes=notes,
        )

        metadata = CompilationMetadata(
            recommendation_id=recommendation.id,
            rules_matched=len(compiled_actions),
            actions_skipped=skipped,
            compiler_version="1.0",
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
        """Load a specific or the latest recommendation for the alert."""
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
        """Load latest investigation for the alert (optional)."""
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
        """Load latest evidence chain for the alert (optional)."""
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
