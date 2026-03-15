"""
PipelineTracker — context-manager based tracker for pipeline stage execution.

Wraps each stage in a timing context, records metrics, and persists
the full PipelineRun to the database.  Publishes events via EventBus
for real-time observability through WebSocket.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import LoggerMixin, get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.services.pipeline.models import (
    PipelineRun,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
    StageRecord,
)

logger = get_logger(__name__)


class _StageContext:
    """Mutable handle passed into a ``with tracker.stage(...)`` block."""

    def __init__(self, record: StageRecord) -> None:
        self._record = record

    def record_metrics(self, metrics: dict[str, Any]) -> None:
        """Merge *metrics* into the stage's key_metrics dict."""
        self._record.key_metrics.update(metrics)

    def record_input(self, summary: dict[str, Any]) -> None:
        self._record.input_summary.update(summary)

    def record_output(self, summary: dict[str, Any]) -> None:
        self._record.output_summary.update(summary)

    def skip(self, reason: str = "") -> None:
        """Mark stage as skipped (e.g. mode != flows_and_detect)."""
        self._record.status = "skipped"
        if reason:
            self._record.error_summary = reason


class PipelineTracker(LoggerMixin):
    """
    Track a PCAP processing pipeline run across all stages.

    Usage::

        tracker = PipelineTracker(pcap_id, db)
        with tracker.stage(PipelineStage.PARSE) as stg:
            flows = parser.parse(...)
            stg.record_metrics({"flow_count": len(flows)})
        # ... more stages ...
        tracker.finish()  # persist to DB
    """

    def __init__(self, pcap_id: str, db: Session, *, run_id: str | None = None) -> None:
        self._pcap_id = pcap_id
        self._db = db
        self._t0 = time.monotonic()
        self._run = PipelineRun(
            id=run_id or generate_uuid(),
            pcap_id=pcap_id,
            status="running",
            started_at=datetime_to_iso(utc_now()),
            created_at=datetime_to_iso(utc_now()),
        )
        # Build stage records for stages 1-4 (synchronous PCAP processing).
        # Agent stages (5-9) are added lazily via `append_stage`.
        self._stage_map: dict[str, StageRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def stage(self, stage: PipelineStage | str) -> Generator[_StageContext, None, None]:
        """
        Context manager that records timing and status for a stage.

        If the body raises, the stage is marked *failed* and the
        exception is re-raised without suppression.
        """
        name = stage.value if isinstance(stage, PipelineStage) else stage
        record = StageRecord(
            stage_name=name,
            status="running",
            started_at=datetime_to_iso(utc_now()),
        )
        self._stage_map[name] = record
        ctx = _StageContext(record)
        t_start = time.monotonic()

        try:
            yield ctx
        except Exception as exc:
            elapsed = (time.monotonic() - t_start) * 1000
            if record.status != "skipped":
                record.status = "failed"
                record.error_summary = str(exc)[:500]
            record.latency_ms = round(elapsed, 2)
            record.completed_at = datetime_to_iso(utc_now())
            self._sync_stages()
            self._publish_stage_event(record)
            raise
        else:
            elapsed = (time.monotonic() - t_start) * 1000
            if record.status == "running":
                record.status = "completed"
            record.latency_ms = round(elapsed, 2)
            record.completed_at = datetime_to_iso(utc_now())
            self._sync_stages()
            self._publish_stage_event(record)

    def append_stage_record(self, record: StageRecord) -> None:
        """
        Append an externally-built StageRecord (e.g. from WorkflowEngine).
        Used when agent stages are executed outside the tracker context.
        """
        self._stage_map[record.stage_name] = record
        self._sync_stages()

    def finish(self) -> PipelineRun:
        """
        Mark the run as complete and persist to the database.
        Returns the finalised PipelineRun.
        """
        total = (time.monotonic() - self._t0) * 1000
        # Determine overall status
        statuses = {r.status for r in self._stage_map.values()}
        if "failed" in statuses:
            self._run.status = "failed"
        else:
            self._run.status = "completed"
        self._run.total_latency_ms = round(total, 2)
        self._run.completed_at = datetime_to_iso(utc_now())
        self._sync_stages()
        self._persist()
        self._publish_run_event()
        self.logger.info(
            "Pipeline run %s for PCAP %s finished: %s (%.1f ms, %d stages)",
            self._run.id,
            self._pcap_id,
            self._run.status,
            total,
            len(self._run.stages),
        )
        return self._run

    def fail(self, error: str) -> PipelineRun:
        """
        Mark the entire run as failed (e.g. unrecoverable error).
        """
        self._run.status = "failed"
        self._run.completed_at = datetime_to_iso(utc_now())
        total = (time.monotonic() - self._t0) * 1000
        self._run.total_latency_ms = round(total, 2)
        self._sync_stages()
        self._persist()
        self.logger.error(
            "Pipeline run %s failed for PCAP %s: %s",
            self._run.id,
            self._pcap_id,
            error,
        )
        return self._run

    @property
    def run(self) -> PipelineRun:
        """Current snapshot of the pipeline run (read-only)."""
        self._sync_stages()
        return self._run

    @property
    def run_id(self) -> str:
        return self._run.id

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _sync_stages(self) -> None:
        """Rebuild ``self._run.stages`` from the mutable map, preserving stage order."""
        ordered: list[StageRecord] = []
        for ps in PIPELINE_STAGE_ORDER:
            if ps.value in self._stage_map:
                ordered.append(self._stage_map[ps.value])
        # Include any custom stages not in the enum (future proof)
        for name, rec in self._stage_map.items():
            if name not in {ps.value for ps in PIPELINE_STAGE_ORDER}:
                ordered.append(rec)
        self._run.stages = ordered

    def _persist(self) -> None:
        """Persist the PipelineRun to the database."""
        from app.models.pipeline import PipelineRunModel

        existing = (
            self._db.query(PipelineRunModel)
            .filter(PipelineRunModel.id == self._run.id)
            .first()
        )
        stages_json = json.dumps(
            [s.model_dump() for s in self._run.stages], ensure_ascii=False
        )
        if existing:
            existing.status = self._run.status
            existing.completed_at = utc_now() if self._run.completed_at else None
            existing.total_latency_ms = self._run.total_latency_ms
            existing.stages_log = stages_json
        else:
            model = PipelineRunModel(
                id=self._run.id,
                pcap_id=self._pcap_id,
                status=self._run.status,
                completed_at=utc_now() if self._run.completed_at else None,
                total_latency_ms=self._run.total_latency_ms,
                stages_log=stages_json,
            )
            self._db.add(model)
        try:
            self._db.flush()
        except Exception:
            self.logger.warning("Failed to persist pipeline run %s", self._run.id, exc_info=True)

    def _publish_stage_event(self, record: StageRecord) -> None:
        """Fire-and-forget stage event via the EventBus."""
        try:
            import asyncio
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, PIPELINE_STAGE_COMPLETED, PIPELINE_STAGE_FAILED

            event_type = (
                PIPELINE_STAGE_COMPLETED
                if record.status == "completed"
                else PIPELINE_STAGE_FAILED
            )
            event = make_event(event_type, {
                "run_id": self._run.id,
                "pcap_id": self._pcap_id,
                "stage": record.stage_name,
                "status": record.status,
                "latency_ms": record.latency_ms,
            })
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(get_event_bus().publish(event), loop)
        except Exception:
            pass  # non-critical — don't break pipeline for event failures

    def _publish_run_event(self) -> None:
        """Fire-and-forget run completion event."""
        try:
            import asyncio
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, PIPELINE_RUN_DONE

            event = make_event(PIPELINE_RUN_DONE, {
                "run_id": self._run.id,
                "pcap_id": self._pcap_id,
                "status": self._run.status,
                "total_latency_ms": self._run.total_latency_ms,
                "stage_count": len(self._run.stages),
            })
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(get_event_bus().publish(event), loop)
        except Exception:
            pass
