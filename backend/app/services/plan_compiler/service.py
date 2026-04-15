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

_EMPTY_REASON = {
    "zh": "所有推荐动作均为监控/建议类，无法编译为可执行操作。",
    "en": (
        "All recommended actions are monitoring/advisory type "
        "and cannot be compiled into executable operations."
    ),
}


class PlanCompilerService:
    def __init__(self, db: Session):
        self.db = db
        self._compiler = PlanCompiler()

    def compile_for_alert(
        self,
        alert_id: str,
        recommendation_id: str | None = None,
        language: str = "en",
    ) -> CompilePlanResponse:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        recommendation = self._load_recommendation(alert_id, recommendation_id)
        investigation = self._load_investigation(alert_id)
        evidence_chain = self._load_evidence_chain(alert_id)

        compiled, skipped = self._compiler.compile(
            alert=alert,
            recommendation=recommendation,
            investigation=investigation,
            evidence_chain=evidence_chain,
            language=language,
        )

        notes = (
            f"Auto-compiled from recommendation {recommendation.id}. "
            f"{len(compiled)} actions compiled, {len(skipped)} skipped."
        )

        twin_service = TwinService(self.db)
        plan = twin_service.create_plan(
            alert_id=alert_id,
            actions=compiled,
            source="agent",
            notes=notes,
        )

        all_skipped = len(compiled) == 0 and len(skipped) > 0
        empty_reason = (
            _EMPTY_REASON["zh" if language == "zh" else "en"] if all_skipped else None
        )

        metadata = CompilationMetadata(
            recommendation_id=recommendation.id,
            rules_matched=len(compiled),
            actions_skipped=len(skipped),
            compiler_version="1.1",
            skipped_actions=skipped,
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
            suffix = f" with id {recommendation_id}" if recommendation_id else ""
            raise ValueError(f"No recommendation found for alert {alert_id}{suffix}")

        payload = json.loads(rec.payload) if isinstance(rec.payload, str) else rec.payload
        return RecommendationSchema(**payload)

    def _load_investigation(self, alert_id: str) -> InvestigationSchema | None:
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
