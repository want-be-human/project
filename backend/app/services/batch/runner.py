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

# 批次阶段名 → pipeline 阶段名映射
_STAGE_MAP = {
    "validate": "parse", "store": "parse", "parse": "parse",
    "featurize": "feature_extract",
    "detect": "detect",
    "aggregate": "aggregate", "persist_result": "aggregate",
}


def _publish_event(event_type: str, data: dict) -> None:
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
    _instance: "JobRunner | None" = None

    def __init__(self, concurrency: int = 2):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._concurrency = concurrency
        self._cancel_set: set[str] = set()
        self._cancel_batch_set: set[str] = set()
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=concurrency)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        staging_dir = settings.DATA_DIR / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        for i in range(self._concurrency):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info(f"JobRunner 已启动，并发数: {self._concurrency}")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for _ in self._workers:
            await self._queue.put("")
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            for task in self._workers:
                task.cancel()
        self._workers.clear()
        self._executor.shutdown(wait=False)
        logger.info("JobRunner 已停止")

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def cancel_job(self, job_id: str) -> None:
        self._cancel_set.add(job_id)

    async def cancel_batch(self, batch_id: str) -> None:
        self._cancel_batch_set.add(batch_id)

    def _is_cancelled(self, job_id: str, batch_id: str) -> bool:
        return job_id in self._cancel_set or batch_id in self._cancel_batch_set

    async def _worker(self, worker_id: int) -> None:
        logger.info(f"Worker-{worker_id} 已启动")
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                job_id = await self._queue.get()
                if not job_id:  # 哨兵值
                    break
                await loop.run_in_executor(
                    self._executor, self._exec_sync, job_id
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"Worker-{worker_id} 异常: {exc}")

        logger.info(f"Worker-{worker_id} 已停止")

    def _exec_sync(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.error(f"Job 不存在: {job_id}")
                return

            bf = db.query(BatchFile).filter(
                BatchFile.id == job.batch_file_id
            ).first()
            if not bf:
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
                bf.status = "done"
                db.commit()
                self._update_batch_stats(db, job.batch_id)
                return

            if self._is_cancelled(job_id, job.batch_id):
                self._mark_cancelled(db, job, bf)
                return

            now = utc_now()
            job.status = "running"
            job.started_at = now
            bf.started_at = now
            job.stages_log = []
            db.commit()

            _publish_event(BATCH_JOB_STARTED, {
                "batch_id": job.batch_id,
                "job_id": job.id,
                "batch_file_id": bf.id,
                "pcap_id": job.pcap_id or "",
            })

            staging_path = Path(settings.DATA_DIR) / "staging" / f"{bf.id}.pcap"
            flow_dicts: list[dict] = []
            alert_dicts: list[dict] = []

            for stage in STAGE_ORDER:
                if self._is_cancelled(job_id, job.batch_id):
                    self._mark_cancelled(db, job, bf)
                    return

                file_status = STAGE_TO_FILE_STATUS.get(stage, bf.status)
                job.current_stage = stage
                bf.status = file_status
                db.commit()

                _publish_event(BATCH_JOB_STAGE_STARTED, {
                    "batch_id": job.batch_id,
                    "job_id": job.id,
                    "stage": stage,
                })
                _publish_event(BATCH_FILE_STATUS, {
                    "batch_id": job.batch_id,
                    "batch_file_id": bf.id,
                    "filename": bf.original_filename,
                    "status": file_status,
                })

                t0 = time.monotonic()
                try:
                    result = self._run_stage(
                        db, job, bf, stage,
                        staging_path, flow_dicts, alert_dicts,
                    )
                    if stage in ("parse", "featurize", "detect"):
                        flow_dicts = result
                    elif stage == "aggregate":
                        alert_dicts = result
                    elif stage == "persist_result":
                        bf.flow_count = result["flow_count"]
                        bf.alert_count = result["alert_count"]

                except Exception as exc:
                    ms = (time.monotonic() - t0) * 1000
                    self._record_stage(db, job, stage, "failed", ms, str(exc))
                    self._mark_failed(db, job, bf, stage, str(exc)[:500])
                    _publish_event(BATCH_JOB_STAGE_FAILED, {
                        "batch_id": job.batch_id,
                        "job_id": job.id,
                        "stage": stage,
                        "error": str(exc)[:500],
                    })
                    return
                else:
                    ms = (time.monotonic() - t0) * 1000
                    self._record_stage(db, job, stage, "completed", ms)
                    db.commit()
                    _publish_event(BATCH_JOB_STAGE_COMPLETED, {
                        "batch_id": job.batch_id,
                        "job_id": job.id,
                        "stage": stage,
                        "latency_ms": round(ms, 2),
                    })

            now = utc_now()
            job.status = "completed"
            job.completed_at = now
            job.latency_ms = (
                (now - job.started_at).total_seconds() * 1000
                if job.started_at else None
            )
            bf.status = "done"
            bf.completed_at = now
            bf.latency_ms = job.latency_ms
            db.commit()

            # 同步写入 pipeline_runs（供 Pipeline API / Dashboard / 场景回归使用）
            self._sync_pipeline_run(db, job)

            _publish_event(BATCH_JOB_COMPLETED, {
                "batch_id": job.batch_id,
                "job_id": job.id,
                "batch_file_id": bf.id,
                "flow_count": bf.flow_count,
                "alert_count": bf.alert_count,
                "latency_ms": round(job.latency_ms or 0, 2),
            })
            _publish_event(BATCH_FILE_STATUS, {
                "batch_id": job.batch_id,
                "batch_file_id": bf.id,
                "filename": bf.original_filename,
                "status": "done",
                "flow_count": bf.flow_count,
                "alert_count": bf.alert_count,
            })

            for ad in alert_dicts:
                _publish_event(ALERT_CREATED, {
                    "alert_id": ad["id"],
                    "severity": ad["severity"],
                })

            self._update_batch_stats(db, job.batch_id)

        except Exception as exc:
            logger.exception(f"Job {job_id} 执行异常: {exc}")
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                bf = db.query(BatchFile).filter(
                    BatchFile.id == job.batch_file_id
                ).first() if job else None
                if job and bf:
                    self._mark_failed(db, job, bf, "unknown", str(exc)[:500])
            except Exception:
                pass
        finally:
            db.close()

    def _run_stage(
        self, db: Session, job: Job, bf: BatchFile,
        stage: str, staging_path: Path,
        flow_dicts: list[dict], alert_dicts: list[dict],
    ):
        if stage == "validate":
            return stage_validate(db, job, bf, staging_path)
        if stage == "store":
            return stage_store(db, job, bf, staging_path)
        if stage == "parse":
            return stage_parse(db, job, bf)
        if stage == "featurize":
            return stage_featurize(db, job, bf, flow_dicts)
        if stage == "detect":
            return stage_detect(db, job, bf, flow_dicts)
        if stage == "aggregate":
            return stage_aggregate(db, job, bf, flow_dicts)
        if stage == "persist_result":
            return stage_persist_result(db, job, bf, flow_dicts, alert_dicts)
        raise ValueError(f"未知阶段: {stage}")

    def _record_stage(
        self, db: Session, job: Job,
        stage: str, status: str, latency_ms: float,
        error: str | None = None,
    ) -> None:
        entry = {
            "stage": stage,
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "completed_at": datetime_to_iso(utc_now()),
        }
        if error:
            entry["error"] = error

        # stages_log 是 JSON 列，需重新赋值以触发 ORM 变更检测
        log = list(job.stages_log or [])
        log.append(entry)
        job.stages_log = log

    def _mark_failed(
        self, db: Session, job: Job, bf: BatchFile,
        stage: str, error: str,
    ) -> None:
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

        bf.status = "failed"
        bf.error_message = f"[{stage}] {error}"
        bf.completed_at = now
        if bf.started_at:
            bf.latency_ms = (now - bf.started_at).total_seconds() * 1000
        db.commit()

        # 失败也同步 pipeline_runs（场景回归需要看到失败阶段）
        self._sync_pipeline_run(db, job)

        _publish_event(BATCH_JOB_FAILED, {
            "batch_id": job.batch_id,
            "job_id": job.id,
            "batch_file_id": bf.id,
            "error": error,
            "retry_count": job.retry_count,
        })
        _publish_event(BATCH_FILE_STATUS, {
            "batch_id": job.batch_id,
            "batch_file_id": bf.id,
            "filename": bf.original_filename,
            "status": "failed",
            "error": error,
        })

        self._update_batch_stats(db, job.batch_id)

    def _sync_pipeline_run(self, db: Session, job: Job) -> None:
        # 将批次阶段合并为 pipeline 阶段格式，供 Pipeline API / Dashboard / 场景回归第 8 阶段使用
        if not job.pcap_id:
            return

        import json

        raw_stages: list[dict] = job.stages_log if isinstance(job.stages_log, list) else []
        merged: dict[str, dict] = {}
        for entry in raw_stages:
            batch_name = entry.get("stage") or ""
            pipe_name = _STAGE_MAP.get(batch_name, batch_name)

            if pipe_name not in merged:
                merged[pipe_name] = {
                    "stage_name": pipe_name,
                    "status": entry.get("status", "completed"),
                    "latency_ms": entry.get("latency_ms"),
                    "completed_at": entry.get("completed_at"),
                    "key_metrics": {},
                    "output_summary": {},
                }
                continue

            rec = merged[pipe_name]
            if entry.get("latency_ms") and rec["latency_ms"] is not None:
                rec["latency_ms"] += entry["latency_ms"]
            elif entry.get("latency_ms"):
                rec["latency_ms"] = entry["latency_ms"]
            if entry.get("completed_at"):
                rec["completed_at"] = entry["completed_at"]
            if entry.get("status") == "failed":
                rec["status"] = "failed"

        stages = list(merged.values())
        status = "failed" if any(s["status"] == "failed" for s in stages) else "completed"

        try:
            run = PipelineRunModel(
                id=generate_uuid(),
                pcap_id=job.pcap_id,
                status=status,
                completed_at=job.completed_at,
                total_latency_ms=job.latency_ms,
                stages_log=json.dumps(stages, ensure_ascii=False),
            )
            db.add(run)
            db.commit()
        except Exception as exc:
            logger.warning("同步 pipeline_run 失败（非关键）: %s", exc)
            db.rollback()

    def _mark_cancelled(
        self, db: Session, job: Job, bf: BatchFile,
    ) -> None:
        now = utc_now()
        job.status = "cancelled"
        job.cancelled_at = now
        job.completed_at = now
        bf.status = "failed"
        bf.error_message = "已取消"
        bf.completed_at = now
        db.commit()

        self._cancel_set.discard(job.id)

        _publish_event(BATCH_FILE_STATUS, {
            "batch_id": job.batch_id,
            "batch_file_id": bf.id,
            "filename": bf.original_filename,
            "status": "failed",
            "error": "已取消",
        })

        self._update_batch_stats(db, job.batch_id)

    def _update_batch_stats(self, db: Session, batch_id: str) -> None:
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return

        # 已取消批次不再更新状态（防止 running job 完成后覆盖 cancelled）
        if batch.status == "cancelled":
            db.commit()
            return

        files = db.query(BatchFile).filter(BatchFile.batch_id == batch_id).all()
        done = sum(1 for f in files if f.status == "done")
        failed = sum(1 for f in files if f.status == "failed")
        skipped = sum(1 for f in files if f.status in ("rejected", "duplicate"))
        actionable = batch.total_files - skipped

        batch.completed_files = done
        batch.failed_files = failed
        batch.total_flow_count = sum(f.flow_count for f in files)
        batch.total_alert_count = sum(f.alert_count for f in files)

        if not (actionable > 0 and (done + failed) >= actionable):
            db.commit()
            return

        now = utc_now()
        batch.completed_at = now
        if batch.started_at:
            batch.total_latency_ms = (now - batch.started_at).total_seconds() * 1000

        if failed == 0:
            batch.status = "completed"
        elif done == 0:
            batch.status = "failed"
        else:
            batch.status = "partial_failure"

        db.commit()

        if batch.status == "failed":
            _publish_event(BATCH_FAILED, {
                "batch_id": batch.id,
                "error": "所有文件处理失败",
                "failed_files": failed,
            })
        else:
            _publish_event(BATCH_COMPLETED, {
                "batch_id": batch.id,
                "status": batch.status,
                "total_flow_count": batch.total_flow_count,
                "total_alert_count": batch.total_alert_count,
                "total_latency_ms": round(batch.total_latency_ms or 0, 2),
            })

        self._cancel_batch_set.discard(batch_id)


_runner_instance: JobRunner | None = None


def get_job_runner(concurrency: int = 2) -> JobRunner:
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = JobRunner(concurrency=concurrency)
    return _runner_instance


def reset_job_runner() -> None:
    global _runner_instance
    _runner_instance = None
