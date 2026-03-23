"""
PipelineTracker：基于上下文管理器的流水线阶段执行跟踪器。

将每个阶段包裹在计时上下文中，记录指标并将完整 PipelineRun 持久化到数据库。
同时通过 EventBus 发布事件，以支持 WebSocket 实时可观测。
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy.orm import Session

from app.core.logging import LoggerMixin, get_logger
from app.core.loop import get_main_loop
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.services.pipeline.models import (
    PipelineRun,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
    StageRecord,
)

logger = get_logger(__name__)


class _StageContext:
    """传入 ``with tracker.stage(...)`` 代码块的可变句柄。"""

    def __init__(self, record: StageRecord) -> None:
        self._record = record

    def record_metrics(self, metrics: dict[str, Any]) -> None:
        """将 *metrics* 合并到阶段的 key_metrics 字典中。"""
        self._record.key_metrics.update(metrics)

    def record_input(self, summary: dict[str, Any]) -> None:
        self._record.input_summary.update(summary)

    def record_output(self, summary: dict[str, Any]) -> None:
        self._record.output_summary.update(summary)

    def skip(self, reason: str = "") -> None:
        """将阶段标记为跳过（例如 mode != flows_and_detect）。"""
        self._record.status = "skipped"
        if reason:
            self._record.error_summary = reason


class PipelineTracker(LoggerMixin):
    """
    跟踪一次 PCAP 处理流水线在各阶段的执行情况。

    用法::

        tracker = PipelineTracker(pcap_id, db)
        with tracker.stage(PipelineStage.PARSE) as stg:
            flows = parser.parse(...)
            stg.record_metrics({"flow_count": len(flows)})
        # ... 其余阶段同理 ...
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
        # 预置 1-4 阶段记录（同步 PCAP 处理阶段）。
        # Agent 阶段（5-9）通过 `append_stage` 延迟追加。
        self._stage_map: dict[str, StageRecord] = {}

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------

    @contextmanager
    def stage(self, stage: PipelineStage | str) -> Generator[_StageContext, None, None]:
        """
        记录阶段耗时与状态的上下文管理器。

        若代码块抛出异常，则该阶段标记为 *failed*，并将异常继续抛出。
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
        追加外部构建的 StageRecord（例如来自 WorkflowEngine）。
        用于智能体阶段在跟踪器上下文外执行的场景。
        """
        self._stage_map[record.stage_name] = record
        self._sync_stages()

    def finish(self) -> PipelineRun:
        """
        将运行标记为完成并持久化到数据库。
        返回最终的 PipelineRun。
        """
        total = (time.monotonic() - self._t0) * 1000
        # 确定整体状态
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
        将整个运行标记为失败（例如不可恢复错误）。
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
        """当前流水线运行快照（只读）。"""
        self._sync_stages()
        return self._run

    @property
    def run_id(self) -> str:
        return self._run.id

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _sync_stages(self) -> None:
        """从可变映射重建 ``self._run.stages``，并保持阶段顺序。"""
        ordered: list[StageRecord] = []
        for ps in PIPELINE_STAGE_ORDER:
            if ps.value in self._stage_map:
                ordered.append(self._stage_map[ps.value])
        # 追加不在枚举中的自定义阶段（面向未来扩展）
        for name, rec in self._stage_map.items():
            if name not in {ps.value for ps in PIPELINE_STAGE_ORDER}:
                ordered.append(rec)
        self._run.stages = ordered

    def _persist(self) -> None:
        """将 PipelineRun 持久化到数据库。"""
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
        """通过 EventBus 以 fire-and-forget 方式发布阶段事件。"""
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
            # 使用保存的主事件循环引用，避免后台线程中 asyncio.get_event_loop() 失败
            loop = get_main_loop()
            if loop is None:
                return
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(get_event_bus().publish(event), loop)
        except Exception:
            pass  # 非关键路径 — 不因事件发布失败而中断 pipeline

    def _publish_run_event(self) -> None:
        """以 fire-and-forget 方式发布运行完成事件。"""
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
            # 使用保存的主事件循环引用，避免后台线程中 asyncio.get_event_loop() 失败
            loop = get_main_loop()
            if loop is None:
                return
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(get_event_bus().publish(event), loop)
        except Exception:
            pass  # 非关键路径 — 不因事件发布失败而中断 pipeline
