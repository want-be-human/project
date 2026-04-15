from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

from app.core.logging import LoggerMixin, get_logger
from app.core.loop import get_main_loop
from app.core.utils import datetime_to_iso, utc_now
from app.services.scenarios.models import (
    FailureAttribution,
    ScenarioRunTimeline,
    ScenarioStage,
    ScenarioStageRecord,
    SCENARIO_STAGE_ORDER,
    TOTAL_STAGES,
)

logger = get_logger(__name__)


class _ScenarioStageContext:
    def __init__(self, record: ScenarioStageRecord) -> None:
        self._record = record

    def record_metrics(self, metrics: dict[str, Any]) -> None:
        self._record.key_metrics.update(metrics)

    def record_input(self, summary: dict[str, Any]) -> None:
        self._record.input_summary.update(summary)

    def record_output(self, summary: dict[str, Any]) -> None:
        self._record.output_summary.update(summary)

    def record_failure_attribution(self, attribution: FailureAttribution) -> None:
        self._record.failure_attribution = attribution

    def skip(self, reason: str = "") -> None:
        self._record.status = "skipped"
        if reason:
            self._record.error_summary = reason


class ScenarioRunTracker(LoggerMixin):
    def __init__(self, scenario_id: str, run_id: str, db: Any) -> None:
        self._scenario_id = scenario_id
        self._run_id = run_id
        self._db = db
        self._t0 = time.monotonic()
        self._stage_map: dict[str, ScenarioStageRecord] = {}
        self._timeline = ScenarioRunTimeline(
            id=run_id,
            scenario_id=scenario_id,
            status="running",
            started_at=datetime_to_iso(utc_now()),
        )
        # OTel 根 span 懒加载，避免 OTel 未初始化时崩溃
        self._root_span: Any = None
        self._init_otel_root_span()

    @contextmanager
    def stage(self, stage: ScenarioStage | str) -> Generator[_ScenarioStageContext, None, None]:
        name = stage.value if isinstance(stage, ScenarioStage) else stage
        idx = self._stage_index(name)

        record = ScenarioStageRecord(
            stage_name=name,
            status="running",
            started_at=datetime_to_iso(utc_now()),
        )
        self._stage_map[name] = record
        ctx = _ScenarioStageContext(record)
        t_start = time.monotonic()

        self._publish_stage_started(record, idx)
        child_span = self._start_stage_span(name)

        try:
            yield ctx
        except Exception as exc:
            elapsed = (time.monotonic() - t_start) * 1000
            if record.status != "skipped":
                record.status = "failed"
                record.error_summary = str(exc)[:500]
            record.latency_ms = round(elapsed, 2)
            record.completed_at = datetime_to_iso(utc_now())
            # 无结构化归因时自动生成 service_error
            if record.failure_attribution is None:
                record.failure_attribution = FailureAttribution(
                    check_name=name,
                    expected="stage_success",
                    actual=str(exc)[:200],
                    category="service_error",
                )
            self._sync_stages()
            self._publish_stage_event(record)
            self._publish_progress()
            self._finish_stage_span(child_span, record, exc)
            raise
        else:
            elapsed = (time.monotonic() - t_start) * 1000
            if record.status == "running":
                record.status = "completed"
            record.latency_ms = round(elapsed, 2)
            record.completed_at = datetime_to_iso(utc_now())
            self._sync_stages()
            self._publish_stage_event(record)
            self._publish_progress()
            self._finish_stage_span(child_span, record, None)

    def finish(self) -> ScenarioRunTimeline:
        total = (time.monotonic() - self._t0) * 1000
        statuses = {r.status for r in self._stage_map.values()}
        self._timeline.status = "failed" if "failed" in statuses else "completed"
        self._timeline.total_latency_ms = round(total, 2)
        self._timeline.completed_at = datetime_to_iso(utc_now())
        self._timeline.validation_latency_ms = self._calc_validation_latency()
        self._sync_stages()
        self._publish_run_done()
        self._finish_root_span(None)
        self.logger.info(
            "场景运行 %s (scenario=%s) 完成: %s (%.1f ms, %d 阶段)",
            self._run_id,
            self._scenario_id,
            self._timeline.status,
            total,
            len(self._timeline.stages),
        )
        return self._timeline

    def fail(self, error: str) -> ScenarioRunTimeline:
        total = (time.monotonic() - self._t0) * 1000
        self._timeline.status = "failed"
        self._timeline.total_latency_ms = round(total, 2)
        self._timeline.completed_at = datetime_to_iso(utc_now())
        self._timeline.validation_latency_ms = self._calc_validation_latency()
        self._sync_stages()
        self._publish_run_done()
        self._finish_root_span(Exception(error))
        self.logger.error(
            "场景运行 %s (scenario=%s) 失败: %s",
            self._run_id,
            self._scenario_id,
            error,
        )
        return self._timeline

    def set_pipeline_latency(self, latency_ms: float | None) -> None:
        self._timeline.pipeline_latency_ms = latency_ms

    @property
    def timeline(self) -> ScenarioRunTimeline:
        self._sync_stages()
        return self._timeline

    def _stage_index(self, name: str) -> int:
        for i, s in enumerate(SCENARIO_STAGE_ORDER):
            if s.value == name:
                return i
        return len(self._stage_map)

    def _sync_stages(self) -> None:
        ordered: list[ScenarioStageRecord] = []
        known = {ss.value for ss in SCENARIO_STAGE_ORDER}
        for ss in SCENARIO_STAGE_ORDER:
            if ss.value in self._stage_map:
                ordered.append(self._stage_map[ss.value])
        for name, rec in self._stage_map.items():
            if name not in known:
                ordered.append(rec)
        self._timeline.stages = ordered
        if self._timeline.failed_stage is not None:
            return
        for rec in ordered:
            if rec.status == "failed":
                self._timeline.failed_stage = rec.stage_name
                break

    def _calc_validation_latency(self) -> float | None:
        """阶段 1-8（不含 summarize_result）的 latency_ms 之和。"""
        total = 0.0
        has_value = False
        summarize = ScenarioStage.SUMMARIZE_RESULT.value
        for rec in self._stage_map.values():
            if rec.stage_name != summarize and rec.latency_ms is not None:
                total += rec.latency_ms
                has_value = True
        return round(total, 2) if has_value else None

    def _completed_count(self) -> int:
        return sum(
            1 for r in self._stage_map.values()
            if r.status in ("completed", "failed", "skipped")
        )

    def _fire(self, coro: Any) -> None:
        """协程 fire-and-forget 到主事件循环，忽略异常。"""
        try:
            import asyncio
            loop = get_main_loop()
            if loop is None or not loop.is_running():
                return
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            pass

    def _publish_stage_started(self, record: ScenarioStageRecord, stage_index: int) -> None:
        try:
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, SCENARIO_STAGE_STARTED
            event = make_event(SCENARIO_STAGE_STARTED, {
                "scenario_id": self._scenario_id,
                "run_id": self._run_id,
                "stage": record.stage_name,
                "stage_index": stage_index,
                "total_stages": TOTAL_STAGES,
            })
            self._fire(get_event_bus().publish(event))
        except Exception:
            pass

    def _publish_stage_event(self, record: ScenarioStageRecord) -> None:
        try:
            from app.core.events import get_event_bus
            from app.core.events.models import (
                make_event,
                SCENARIO_STAGE_COMPLETED,
                SCENARIO_STAGE_FAILED,
            )
            if record.status in ("completed", "skipped"):
                event_type = SCENARIO_STAGE_COMPLETED
                data: dict[str, Any] = {
                    "scenario_id": self._scenario_id,
                    "run_id": self._run_id,
                    "stage": record.stage_name,
                    "status": record.status,
                    "latency_ms": record.latency_ms,
                    "key_metrics": record.key_metrics,
                }
            else:
                event_type = SCENARIO_STAGE_FAILED
                data = {
                    "scenario_id": self._scenario_id,
                    "run_id": self._run_id,
                    "stage": record.stage_name,
                    "status": record.status,
                    "latency_ms": record.latency_ms,
                    "error_summary": record.error_summary,
                    "failure_attribution": (
                        record.failure_attribution.model_dump()
                        if record.failure_attribution else None
                    ),
                }
            self._fire(get_event_bus().publish(make_event(event_type, data)))
            self._record_stage_metric(record)
        except Exception:
            pass

    def _publish_progress(self) -> None:
        try:
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, SCENARIO_RUN_PROGRESS
            completed = self._completed_count()
            percent = round(completed / TOTAL_STAGES * 100, 1)
            event = make_event(SCENARIO_RUN_PROGRESS, {
                "scenario_id": self._scenario_id,
                "run_id": self._run_id,
                "completed_stages": completed,
                "total_stages": TOTAL_STAGES,
                "percent": percent,
            })
            self._fire(get_event_bus().publish(event))
        except Exception:
            pass

    def _publish_run_done(self) -> None:
        try:
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, SCENARIO_RUN_DONE
            event = make_event(SCENARIO_RUN_DONE, {
                "scenario_id": self._scenario_id,
                "run_id": self._run_id,
                "status": self._timeline.status,
                "total_latency_ms": self._timeline.total_latency_ms,
                "validation_latency_ms": self._timeline.validation_latency_ms,
                "pipeline_latency_ms": self._timeline.pipeline_latency_ms,
                "failed_stage": self._timeline.failed_stage,
                "stages": [s.model_dump() for s in self._timeline.stages],
            })
            self._fire(get_event_bus().publish(event))
            self._record_run_metric()
        except Exception:
            pass

    # OTel 埋点：懒加载，未初始化时静默跳过

    def _init_otel_root_span(self) -> None:
        try:
            from app.core.observability import get_scenario_tracer
            tracer = get_scenario_tracer()
            self._root_span = tracer.start_span("scenario.run")
            self._root_span.set_attribute("scenario.id", self._scenario_id)
            self._root_span.set_attribute("run.id", self._run_id)
        except Exception:
            self._root_span = None

    def _start_stage_span(self, name: str) -> Any:
        try:
            from opentelemetry import trace
            from app.core.observability import get_scenario_tracer
            tracer = get_scenario_tracer()
            ctx = trace.set_span_in_context(self._root_span) if self._root_span else None
            span = tracer.start_span(f"scenario.stage.{name}", context=ctx)
            span.set_attribute("scenario.id", self._scenario_id)
            span.set_attribute("run.id", self._run_id)
            span.set_attribute("stage.name", name)
            return span
        except Exception:
            return None

    def _finish_stage_span(
        self, span: Any, record: ScenarioStageRecord, exc: Exception | None
    ) -> None:
        if span is None:
            return
        try:
            from opentelemetry.trace import StatusCode
            span.set_attribute("stage.status", record.status)
            if record.latency_ms is not None:
                span.set_attribute("stage.latency_ms", record.latency_ms)
            if exc is not None:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc)[:200])
            else:
                span.set_status(StatusCode.OK)
            span.end()
        except Exception:
            pass

    def _finish_root_span(self, exc: Exception | None) -> None:
        if self._root_span is None:
            return
        try:
            from opentelemetry.trace import StatusCode
            self._root_span.set_attribute("run.status", self._timeline.status)
            if self._timeline.total_latency_ms is not None:
                self._root_span.set_attribute("run.total_latency_ms", self._timeline.total_latency_ms)
            if exc is not None:
                self._root_span.record_exception(exc)
                self._root_span.set_status(StatusCode.ERROR, str(exc)[:200])
            else:
                self._root_span.set_status(StatusCode.OK)
            self._root_span.end()
        except Exception:
            pass

    def _record_stage_metric(self, record: ScenarioStageRecord) -> None:
        try:
            from app.core.observability import get_scenario_meter
            meter = get_scenario_meter()
            hist = meter.create_histogram("scenario_stage_latency_ms")
            if record.latency_ms is not None:
                hist.record(
                    record.latency_ms,
                    {"stage": record.stage_name, "status": record.status},
                )
        except Exception:
            pass

    def _record_run_metric(self) -> None:
        try:
            from app.core.observability import get_scenario_meter
            meter = get_scenario_meter()
            run_total = meter.create_counter("scenario_run_total")
            run_total.add(1, {"status": self._timeline.status})
            if self._timeline.status == "failed":
                failed_total = meter.create_counter("scenario_run_failed_total")
                failed_total.add(1)
            if self._timeline.validation_latency_ms is not None:
                val_hist = meter.create_histogram("scenario_validation_latency_ms")
                val_hist.record(self._timeline.validation_latency_ms)
        except Exception:
            pass
