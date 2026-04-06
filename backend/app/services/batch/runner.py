"""
批量接入作业执行器。

单机异步 Job Runner，使用 asyncio.Queue + 线程池执行同步 pipeline 阶段。
通过 get_job_runner() 获取全局单例，在 app lifespan 中启动/停止。
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.deps import SessionLocal
from app.core.config import settings
from app.core.events import get_event_bus
from app.core.events.models import (
    make_event,
    BATCH_FILE_STATUS,
    BATCH_JOB_STARTED,
    BATCH_JOB_STAGE_STARTED,
    BATCH_JOB_STAGE_COMPLETED,
    BATCH_JOB_STAGE_FAILED,
    BATCH_JOB_COMPLETED,
    BATCH_JOB_FAILED,
    BATCH_COMPLETED,
    BATCH_FAILED,
    ALERT_CREATED,
)
from app.core.logging import get_logger
from app.core.loop import get_main_loop
from app.core.utils import utc_now, datetime_to_iso, generate_uuid
from app.models.batch import Batch, BatchFile, Job
from app.models.pipeline import PipelineRunModel
from app.services.batch.stages import (
    STAGE_ORDER,
    STAGE_TO_FILE_STATUS,
    stage_validate,
    stage_store,
    stage_parse,
    stage_featurize,
    stage_detect,
    stage_aggregate,
    stage_persist_result,
)

logger = get_logger(__name__)


def _publish_event(event_type: str, data: dict) -> None:
    """在后台线程中通过 EventBus 发布事件（fire-and-forget）。"""
    try:
        loop = get_main_loop()
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(
            get_event_bus().publish(make_event(event_type, data)), loop
        )
    except Exception:
        pass  # 非关键路径，不因事件发布失败中断处理


class JobRunner:
    """
    单机异步作业执行器。

    使用 asyncio.Queue 作为内部队列，
    在后台线程池中执行同步 pipeline 阶段。
    """

    _instance: "JobRunner | None" = None

    def __init__(self, concurrency: int = 2):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._concurrency = concurrency
        self._cancel_set: set[str] = set()  # 待取消的 job_id 集合
        self._cancel_batch_set: set[str] = set()  # 待取消的 batch_id 集合
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=concurrency)

    async def start(self) -> None:
        """启动 worker 协程。在 app lifespan 中调用。"""
        if self._running:
            return
        self._running = True
        # 确保暂存目录存在
        staging_dir = settings.DATA_DIR / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        # 启动 worker
        for i in range(self._concurrency):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info(f"JobRunner 已启动，并发数: {self._concurrency}")

    async def stop(self) -> None:
        """优雅停止所有 worker。"""
        if not self._running:
            return
        self._running = False
        # 向每个 worker 发送哨兵值
        for _ in self._workers:
            await self._queue.put("")
        # 等待所有 worker 结束（带超时保护）
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            # 超时则取消所有 worker
            for task in self._workers:
                task.cancel()
        self._workers.clear()
        self._executor.shutdown(wait=False)
        logger.info("JobRunner 已停止")

    async def enqueue(self, job_id: str) -> None:
        """将 job_id 放入队列。"""
        await self._queue.put(job_id)

    async def cancel_job(self, job_id: str) -> None:
        """标记 job 为待取消。"""
        self._cancel_set.add(job_id)

    async def cancel_batch(self, batch_id: str) -> None:
        """取消批次下所有 pending/running 的 job。"""
        self._cancel_batch_set.add(batch_id)

    def _is_cancelled(self, job_id: str, batch_id: str) -> bool:
        """检查 job 或其所属 batch 是否已被取消。"""
        return job_id in self._cancel_set or batch_id in self._cancel_batch_set

    async def _worker(self, worker_id: int) -> None:
        """
        Worker 主循环：
        1. 从队列取 job_id
        2. 检查幂等性
        3. 检查取消标记
        4. 在线程池中执行各阶段
        5. 更新聚合计数
        """
        logger.info(f"Worker-{worker_id} 已启动")
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                job_id = await self._queue.get()
                # 哨兵值：空字符串表示停止
                if not job_id:
                    break

                # 在线程池中执行同步处理
                await loop.run_in_executor(
                    self._executor, self._execute_job_sync, job_id
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"Worker-{worker_id} 异常: {exc}")

        logger.info(f"Worker-{worker_id} 已停止")

    def _execute_job_sync(self, job_id: str) -> None:
        """
        在线程池中同步执行的作业主体。
        调用现有 service 完成各阶段。
        """
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.error(f"Job 不存在: {job_id}")
                return

            batch_file = db.query(BatchFile).filter(
                BatchFile.id == job.batch_file_id
            ).first()
            if not batch_file:
                logger.error(f"BatchFile 不存在: {job.batch_file_id}")
                return

            # 幂等检查：同一 idempotency_key 是否已有 completed 记录
            existing = db.query(Job).filter(
                Job.idempotency_key == job.idempotency_key,
                Job.status == "completed",
                Job.id != job.id,
            ).first()
            if existing:
                logger.info(f"幂等跳过: {job.idempotency_key} 已有完成记录")
                job.status = "completed"
                batch_file.status = "done"
                db.commit()
                self._update_batch_stats(db, job.batch_id)
                return

            # 取消检查
            if self._is_cancelled(job_id, job.batch_id):
                self._mark_cancelled(db, job, batch_file)
                return

            # 标记开始
            now = utc_now()
            job.status = "running"
            job.started_at = now
            batch_file.started_at = now
            job.stages_log = []
            db.commit()

            _publish_event(BATCH_JOB_STARTED, {
                "batch_id": job.batch_id,
                "job_id": job.id,
                "batch_file_id": batch_file.id,
                "pcap_id": job.pcap_id or "",
            })

            # 暂存文件路径
            staging_path = Path(settings.DATA_DIR) / "staging" / f"{batch_file.id}.pcap"

            # 中间数据（跨阶段传递）
            flow_dicts: list[dict] = []
            alert_dicts: list[dict] = []

            # 依次执行各阶段
            for stage_name in STAGE_ORDER:
                # 取消检查
                if self._is_cancelled(job_id, job.batch_id):
                    self._mark_cancelled(db, job, batch_file)
                    return

                # 更新状态
                file_status = STAGE_TO_FILE_STATUS.get(stage_name, batch_file.status)
                job.current_stage = stage_name
                batch_file.status = file_status
                db.commit()

                _publish_event(BATCH_JOB_STAGE_STARTED, {
                    "batch_id": job.batch_id,
                    "job_id": job.id,
                    "stage": stage_name,
                })
                _publish_event(BATCH_FILE_STATUS, {
                    "batch_id": job.batch_id,
                    "batch_file_id": batch_file.id,
                    "filename": batch_file.original_filename,
                    "status": file_status,
                })

                stage_start = time.monotonic()
                try:
                    result = self._run_stage(
                        db, job, batch_file, stage_name,
                        staging_path, flow_dicts, alert_dicts,
                    )
                    # 收集跨阶段数据
                    if stage_name == "parse":
                        flow_dicts = result
                    elif stage_name == "featurize":
                        flow_dicts = result
                    elif stage_name == "detect":
                        flow_dicts = result
                    elif stage_name == "aggregate":
                        alert_dicts = result
                    elif stage_name == "persist_result":
                        batch_file.flow_count = result["flow_count"]
                        batch_file.alert_count = result["alert_count"]

                except Exception as exc:
                    # 阶段失败
                    stage_ms = (time.monotonic() - stage_start) * 1000
                    self._record_stage(db, job, stage_name, "failed", stage_ms, str(exc))
                    self._mark_failed(db, job, batch_file, stage_name, str(exc)[:500])
                    _publish_event(BATCH_JOB_STAGE_FAILED, {
                        "batch_id": job.batch_id,
                        "job_id": job.id,
                        "stage": stage_name,
                        "error": str(exc)[:500],
                    })
                    return
                else:
                    # 阶段成功
                    stage_ms = (time.monotonic() - stage_start) * 1000
                    self._record_stage(db, job, stage_name, "completed", stage_ms)
                    db.commit()
                    _publish_event(BATCH_JOB_STAGE_COMPLETED, {
                        "batch_id": job.batch_id,
                        "job_id": job.id,
                        "stage": stage_name,
                        "latency_ms": round(stage_ms, 2),
                    })

            # 全部阶段完成
            now = utc_now()
            job.status = "completed"
            job.completed_at = now
            job.latency_ms = (
                (now - job.started_at).total_seconds() * 1000
                if job.started_at else None
            )
            batch_file.status = "done"
            batch_file.completed_at = now
            batch_file.latency_ms = job.latency_ms
            db.commit()

            # 同步写入 pipeline_runs（供 Pipeline API / Dashboard / 场景回归使用）
            self._sync_pipeline_run(db, job)

            _publish_event(BATCH_JOB_COMPLETED, {
                "batch_id": job.batch_id,
                "job_id": job.id,
                "batch_file_id": batch_file.id,
                "flow_count": batch_file.flow_count,
                "alert_count": batch_file.alert_count,
                "latency_ms": round(job.latency_ms or 0, 2),
            })
            _publish_event(BATCH_FILE_STATUS, {
                "batch_id": job.batch_id,
                "batch_file_id": batch_file.id,
                "filename": batch_file.original_filename,
                "status": "done",
                "flow_count": batch_file.flow_count,
                "alert_count": batch_file.alert_count,
            })

            # 发布 alert.created 事件（与现有单文件处理一致）
            for ad in alert_dicts:
                _publish_event(ALERT_CREATED, {
                    "alert_id": ad["id"],
                    "severity": ad["severity"],
                })

            # 更新批次聚合统计
            self._update_batch_stats(db, job.batch_id)

        except Exception as exc:
            logger.exception(f"Job {job_id} 执行异常: {exc}")
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                batch_file = db.query(BatchFile).filter(
                    BatchFile.id == job.batch_file_id
                ).first() if job else None
                if job and batch_file:
                    self._mark_failed(db, job, batch_file, "unknown", str(exc)[:500])
            except Exception:
                pass
        finally:
            db.close()

    def _run_stage(
        self, db: Session, job: Job, batch_file: BatchFile,
        stage_name: str, staging_path: Path,
        flow_dicts: list[dict], alert_dicts: list[dict],
    ):
        """分发到具体阶段函数。"""
        if stage_name == "validate":
            return stage_validate(db, job, batch_file, staging_path)
        elif stage_name == "store":
            return stage_store(db, job, batch_file, staging_path)
        elif stage_name == "parse":
            return stage_parse(db, job, batch_file)
        elif stage_name == "featurize":
            return stage_featurize(db, job, batch_file, flow_dicts)
        elif stage_name == "detect":
            return stage_detect(db, job, batch_file, flow_dicts)
        elif stage_name == "aggregate":
            return stage_aggregate(db, job, batch_file, flow_dicts)
        elif stage_name == "persist_result":
            return stage_persist_result(db, job, batch_file, flow_dicts, alert_dicts)
        else:
            raise ValueError(f"未知阶段: {stage_name}")

    def _record_stage(
        self, db: Session, job: Job,
        stage_name: str, status: str, latency_ms: float,
        error: str | None = None,
    ) -> None:
        """记录阶段执行结果到 stages_log。"""
        log_entry = {
            "stage": stage_name,
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "completed_at": datetime_to_iso(utc_now()),
        }
        if error:
            log_entry["error"] = error

        # stages_log 是 JSON 列，需要重新赋值触发 ORM 变更检测
        current_log = list(job.stages_log or [])
        current_log.append(log_entry)
        job.stages_log = current_log

    def _mark_failed(
        self, db: Session, job: Job, batch_file: BatchFile,
        stage: str, error: str,
    ) -> None:
        """标记 job 和 batch_file 为失败。"""
        # PostgreSQL 要求在事务错误后先 rollback 才能继续操作
        try:
            db.rollback()
        except Exception:
            pass

        now = utc_now()
        job.status = "failed"
        job.error_message = f"[{stage}] {error}"
        job.completed_at = now
        if job.started_at:
            job.latency_ms = (now - job.started_at).total_seconds() * 1000

        batch_file.status = "failed"
        batch_file.error_message = f"[{stage}] {error}"
        batch_file.completed_at = now
        if batch_file.started_at:
            batch_file.latency_ms = (now - batch_file.started_at).total_seconds() * 1000
        db.commit()

        # 失败时也同步 pipeline_runs（场景回归需要看到失败阶段）
        self._sync_pipeline_run(db, job)

        _publish_event(BATCH_JOB_FAILED, {
            "batch_id": job.batch_id,
            "job_id": job.id,
            "batch_file_id": batch_file.id,
            "error": error,
            "retry_count": job.retry_count,
        })
        _publish_event(BATCH_FILE_STATUS, {
            "batch_id": job.batch_id,
            "batch_file_id": batch_file.id,
            "filename": batch_file.original_filename,
            "status": "failed",
            "error": error,
        })

        # 更新批次聚合统计
        self._update_batch_stats(db, job.batch_id)

    # 批次阶段名 → pipeline 阶段名映射
    _STAGE_MAP = {
        "validate": "parse", "store": "parse", "parse": "parse",
        "featurize": "feature_extract",
        "detect": "detect",
        "aggregate": "aggregate", "persist_result": "aggregate",
    }

    def _sync_pipeline_run(self, db: Session, job: Job) -> None:
        """将 Job.stages_log 同步写入 pipeline_runs 表。

        转换批次阶段格式为 pipeline 阶段格式（合并子阶段、统一字段名），
        供 Pipeline API、Dashboard、场景回归第 8 阶段使用。
        """
        if not job.pcap_id:
            return

        import json

        raw_stages: list[dict] = job.stages_log if isinstance(job.stages_log, list) else []
        merged: dict[str, dict] = {}
        for entry in raw_stages:
            batch_name = entry.get("stage") or ""
            pipe_name = self._STAGE_MAP.get(batch_name, batch_name)

            if pipe_name not in merged:
                merged[pipe_name] = {
                    "stage_name": pipe_name,
                    "status": entry.get("status", "completed"),
                    "latency_ms": entry.get("latency_ms"),
                    "completed_at": entry.get("completed_at"),
                    "key_metrics": {},
                    "output_summary": {},
                }
            else:
                rec = merged[pipe_name]
                if entry.get("latency_ms") and rec["latency_ms"] is not None:
                    rec["latency_ms"] += entry["latency_ms"]
                elif entry.get("latency_ms"):
                    rec["latency_ms"] = entry["latency_ms"]
                if entry.get("completed_at"):
                    rec["completed_at"] = entry["completed_at"]
                if entry.get("status") == "failed":
                    rec["status"] = "failed"

        pipeline_stages = list(merged.values())
        status = "failed" if any(s["status"] == "failed" for s in pipeline_stages) else "completed"

        try:
            run = PipelineRunModel(
                id=generate_uuid(),
                pcap_id=job.pcap_id,
                status=status,
                completed_at=job.completed_at,
                total_latency_ms=job.latency_ms,
                stages_log=json.dumps(pipeline_stages, ensure_ascii=False),
            )
            db.add(run)
            db.commit()
        except Exception as exc:
            logger.warning("同步 pipeline_run 失败（非关键）: %s", exc)
            db.rollback()

    def _mark_cancelled(
        self, db: Session, job: Job, batch_file: BatchFile,
    ) -> None:
        """标记 job 为已取消。"""
        now = utc_now()
        job.status = "cancelled"
        job.cancelled_at = now
        job.completed_at = now
        batch_file.status = "failed"
        batch_file.error_message = "已取消"
        batch_file.completed_at = now
        db.commit()

        # 清理取消标记
        self._cancel_set.discard(job.id)

        _publish_event(BATCH_FILE_STATUS, {
            "batch_id": job.batch_id,
            "batch_file_id": batch_file.id,
            "filename": batch_file.original_filename,
            "status": "failed",
            "error": "已取消",
        })

        self._update_batch_stats(db, job.batch_id)

    def _update_batch_stats(self, db: Session, batch_id: str) -> None:
        """更新批次聚合统计并检查是否完成。"""
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return

        # 已取消的批次不再更新状态（防止 running job 完成后覆盖 cancelled）
        if batch.status == "cancelled":
            db.commit()
            return

        # 统计各状态文件数
        files = db.query(BatchFile).filter(BatchFile.batch_id == batch_id).all()
        done_count = sum(1 for f in files if f.status == "done")
        failed_count = sum(1 for f in files if f.status == "failed")
        skipped_count = sum(1 for f in files if f.status in ("rejected", "duplicate"))
        total_actionable = batch.total_files - skipped_count

        batch.completed_files = done_count
        batch.failed_files = failed_count
        batch.total_flow_count = sum(f.flow_count for f in files)
        batch.total_alert_count = sum(f.alert_count for f in files)

        # 检查批次是否完成
        if total_actionable > 0 and (done_count + failed_count) >= total_actionable:
            now = utc_now()
            batch.completed_at = now
            if batch.started_at:
                batch.total_latency_ms = (now - batch.started_at).total_seconds() * 1000

            if failed_count == 0:
                batch.status = "completed"
            elif done_count == 0:
                batch.status = "failed"
            else:
                batch.status = "partial_failure"

            db.commit()

            # 发布批次完成/失败事件
            if batch.status == "failed":
                _publish_event(BATCH_FAILED, {
                    "batch_id": batch.id,
                    "error": "所有文件处理失败",
                    "failed_files": failed_count,
                })
            else:
                _publish_event(BATCH_COMPLETED, {
                    "batch_id": batch.id,
                    "status": batch.status,
                    "total_flow_count": batch.total_flow_count,
                    "total_alert_count": batch.total_alert_count,
                    "total_latency_ms": round(batch.total_latency_ms or 0, 2),
                })

            # 清理 batch 取消标记
            self._cancel_batch_set.discard(batch_id)
        else:
            db.commit()


# ── 单例管理 ──────────────────────────────────────────────────

_runner_instance: JobRunner | None = None


def get_job_runner(concurrency: int = 2) -> JobRunner:
    """返回全局 JobRunner 单例。"""
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = JobRunner(concurrency=concurrency)
    return _runner_instance


def reset_job_runner() -> None:
    """重置单例（便于测试）。"""
    global _runner_instance
    _runner_instance = None
