from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.utils import utc_now, datetime_to_iso, is_valid_pcap_filename, stream_save_and_hash
from app.models.batch import Batch, BatchFile, Job
from app.models.pcap import PcapFile
from app.schemas.batch import (
    BatchSchema,
    BatchDetailSchema,
    BatchFileSchema,
    JobSchema,
    BatchStartResponse,
    BatchRetryResponse,
)

logger = get_logger(__name__)

# PCAP 魔数列表（与 IngestionService 一致）
_VALID_PCAP_MAGICS = [
    b"\xa1\xb2\xc3\xd4",
    b"\xd4\xc3\xb2\xa1",
    b"\xa1\xb2\x3c\x4d",
    b"\x4d\x3c\xb2\xa1",
    b"\x0a\x0d\x0d\x0a",
]


class BatchService:
    def __init__(self, db: Session):
        self.db = db

    def create_batch(
        self,
        name: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
    ) -> BatchSchema:
        now = utc_now()
        batch_name = name or f"Batch-{now.strftime('%Y%m%d-%H%M%S')}"

        batch = Batch(
            name=batch_name,
            source=source or "web_upload",
            tags=tags,
            status="created",
        )
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)

        logger.info(f"批次已创建: {batch.id} ({batch_name})")
        return self._to_batch(batch)

    def get_batch(self, batch_id: str) -> BatchSchema:
        return self._to_batch(self._get_or_404(batch_id))

    def get_batch_detail(self, batch_id: str) -> BatchDetailSchema:
        batch = self._get_or_404(batch_id)
        files = (
            self.db.query(BatchFile)
            .filter(BatchFile.batch_id == batch_id)
            .order_by(BatchFile.sequence)
            .all()
        )
        return BatchDetailSchema(
            **self._to_batch(batch).model_dump(),
            files=[self._to_file(f) for f in files],
        )

    def list_batches(
        self, limit: int = 50, offset: int = 0, status: str | None = None,
    ) -> list[BatchSchema]:
        query = self.db.query(Batch).order_by(Batch.created_at.desc())
        if status:
            query = query.filter(Batch.status == status)
        batches = query.offset(offset).limit(limit).all()
        return [self._to_batch(b) for b in batches]

    def upload_files(
        self,
        batch_id: str,
        files: list[tuple[str, BinaryIO]],
    ) -> list[BatchFileSchema]:
        # 每个文件：扩展名校验 → 流式保存并算 sha256 → 魔数校验 → 批次内+全局去重
        batch = self._get_or_404(batch_id)
        if batch.status not in ("created", "uploading"):
            raise ConflictError(
                message=f"批次 {batch_id} 状态为 {batch.status}，无法上传文件",
                details={"batch_id": batch_id, "status": batch.status},
            )

        batch.status = "uploading"
        existing_hashes = set(
            h for (h,) in
            self.db.query(BatchFile.sha256)
            .filter(BatchFile.batch_id == batch_id, BatchFile.sha256.isnot(None))
            .all()
        )
        seq = batch.total_files
        results: list[BatchFileSchema] = []
        staging_dir = settings.DATA_DIR / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        for filename, file_obj in files:
            seq += 1
            bf = BatchFile(
                batch_id=batch_id,
                original_filename=filename,
                sequence=seq,
                status="accepted",
            )

            if not is_valid_pcap_filename(filename):
                bf.status = "rejected"
                bf.reject_reason = f"不支持的文件扩展名: {filename}"
                self.db.add(bf)
                self.db.flush()
                results.append(self._to_file(bf))
                continue

            # 先分配 ID，再流式写入暂存区并同步算 SHA256（内存固定 ~64KB）
            self.db.add(bf)
            self.db.flush()

            staging_path = staging_dir / f"{bf.id}.pcap"
            try:
                size_bytes, sha256, magic = stream_save_and_hash(file_obj, staging_path)
            except Exception as exc:
                bf.status = "rejected"
                bf.reject_reason = f"文件读取失败: {str(exc)[:200]}"
                staging_path.unlink(missing_ok=True)
                self.db.flush()
                results.append(self._to_file(bf))
                continue

            bf.size_bytes = size_bytes
            bf.sha256 = sha256

            if len(magic) < 4 or magic[:4] not in _VALID_PCAP_MAGICS:
                bf.status = "rejected"
                bf.reject_reason = "无效的 PCAP 文件（魔数校验失败）"
                staging_path.unlink(missing_ok=True)
                self.db.flush()
                results.append(self._to_file(bf))
                continue

            if sha256 in existing_hashes:
                bf.status = "duplicate"
                bf.reject_reason = "批次内重复文件"
                staging_path.unlink(missing_ok=True)
                self.db.flush()
                results.append(self._to_file(bf))
                continue

            global_dup = self.db.query(PcapFile).filter(
                PcapFile.sha256 == sha256
            ).first()
            if global_dup:
                bf.status = "duplicate"
                bf.reject_reason = f"与已有文件重复 (pcap_id={global_dup.id})"
                staging_path.unlink(missing_ok=True)
                self.db.flush()
                results.append(self._to_file(bf))
                continue

            existing_hashes.add(sha256)
            results.append(self._to_file(bf))

        batch.total_files = seq
        batch.total_size_bytes = sum(
            f.size_bytes for f in
            self.db.query(BatchFile).filter(BatchFile.batch_id == batch_id).all()
        )
        self.db.commit()

        logger.info(f"批次 {batch_id} 上传 {len(files)} 个文件，"
                     f"accepted={sum(1 for r in results if r.status == 'accepted')}")
        return results

    def start_batch(self, batch_id: str) -> tuple[BatchStartResponse, list[str]]:
        # 返回 (response, job_ids)，调用方负责将 job_ids 入队
        batch = self._get_or_404(batch_id)
        if batch.status not in ("created", "uploading"):
            raise ConflictError(
                message=f"批次 {batch_id} 状态为 {batch.status}，无法启动",
                details={"batch_id": batch_id, "status": batch.status},
            )

        accepted = (
            self.db.query(BatchFile)
            .filter(BatchFile.batch_id == batch_id, BatchFile.status == "accepted")
            .order_by(BatchFile.sequence)
            .all()
        )
        skipped = (
            self.db.query(BatchFile)
            .filter(
                BatchFile.batch_id == batch_id,
                BatchFile.status.in_(["rejected", "duplicate"]),
            )
            .count()
        )

        if not accepted:
            raise ValidationError(
                message="批次中没有可处理的文件",
                details={"batch_id": batch_id, "skipped": skipped},
            )

        job_ids: list[str] = []
        for bf in accepted:
            bf.status = "queued"
            job = Job(
                batch_id=batch_id,
                batch_file_id=bf.id,
                pcap_id=None,  # store 阶段后填充
                status="pending",
                idempotency_key=f"{bf.id}:{bf.retry_count}",
                retry_count=bf.retry_count,
            )
            self.db.add(job)
            self.db.flush()
            job_ids.append(job.id)

        batch.status = "processing"
        batch.started_at = utc_now()
        self.db.commit()

        logger.info(f"批次 {batch_id} 已启动，创建 {len(job_ids)} 个作业")
        return (
            BatchStartResponse(
                batch_id=batch_id,
                jobs_created=len(job_ids),
                skipped_files=skipped,
            ),
            job_ids,
        )

    def cancel_batch(
        self, batch_id: str, reason: str | None = None,
    ) -> BatchSchema:
        batch = self._get_or_404(batch_id)
        if batch.status in ("completed", "failed", "cancelled"):
            raise ConflictError(
                message=f"批次 {batch_id} 已结束，无法取消",
                details={"batch_id": batch_id, "status": batch.status},
            )

        batch.status = "cancelled"
        batch.error_message = reason or "用户取消"
        batch.completed_at = utc_now()
        if batch.started_at:
            batch.total_latency_ms = (
                (batch.completed_at - batch.started_at).total_seconds() * 1000
            )

        active_jobs = (
            self.db.query(Job)
            .filter(Job.batch_id == batch_id, Job.status.in_(["pending", "running"]))
            .all()
        )
        now = utc_now()
        for job in active_jobs:
            job.status = "cancelled"
            job.cancelled_at = now
            job.completed_at = now

        # 将所有未完成的文件标记为 failed（排除已完成和已拒绝的）
        incomplete = (
            self.db.query(BatchFile)
            .filter(
                BatchFile.batch_id == batch_id,
                BatchFile.status.notin_(["done", "rejected", "duplicate", "failed"]),
            )
            .all()
        )
        for bf in incomplete:
            bf.status = "failed"
            bf.error_message = "批次已取消"
            bf.completed_at = now

        self.db.commit()
        logger.info(f"批次 {batch_id} 已取消")
        return self._to_batch(batch)

    def retry_batch(self, batch_id: str) -> tuple[BatchRetryResponse, list[str]]:
        batch = self._get_or_404(batch_id)
        if batch.status not in ("partial_failure", "failed", "cancelled"):
            raise ConflictError(
                message=f"批次 {batch_id} 状态为 {batch.status}，无需重试",
                details={"batch_id": batch_id, "status": batch.status},
            )

        # 排除 rejected/duplicate（reject_reason 不为空的）
        failed = (
            self.db.query(BatchFile)
            .filter(
                BatchFile.batch_id == batch_id,
                BatchFile.status == "failed",
                BatchFile.reject_reason.is_(None),
            )
            .all()
        )

        if not failed:
            raise ValidationError(
                message="没有可重试的失败文件",
                details={"batch_id": batch_id},
            )

        job_ids: list[str] = []
        for bf in failed:
            bf.retry_count += 1
            bf.status = "queued"
            bf.error_message = None
            bf.started_at = None
            bf.completed_at = None
            bf.latency_ms = None

            # 若 store 阶段之后失败，从 PCAP_DIR 重新复制到暂存区
            staging_path = settings.DATA_DIR / "staging" / f"{bf.id}.pcap"
            if not staging_path.exists() and bf.pcap_id:
                pcap = self.db.query(PcapFile).filter(PcapFile.id == bf.pcap_id).first()
                if pcap and Path(pcap.storage_path).exists():
                    staging_dir = settings.DATA_DIR / "staging"
                    staging_dir.mkdir(parents=True, exist_ok=True)
                    staging_path.write_bytes(Path(pcap.storage_path).read_bytes())

            job = Job(
                batch_id=batch_id,
                batch_file_id=bf.id,
                pcap_id=bf.pcap_id,
                status="pending",
                idempotency_key=f"{bf.id}:{bf.retry_count}",
                retry_count=bf.retry_count,
            )
            self.db.add(job)
            self.db.flush()
            job_ids.append(job.id)

        batch.status = "processing"
        batch.failed_files = 0
        batch.started_at = utc_now()
        batch.completed_at = None
        batch.total_latency_ms = None
        batch.error_message = None
        self.db.commit()

        logger.info(f"批次 {batch_id} 重试 {len(job_ids)} 个文件")
        return (
            BatchRetryResponse(
                batch_id=batch_id,
                jobs_created=len(job_ids),
                files_retried=len(failed),
            ),
            job_ids,
        )

    def retry_file(
        self, batch_id: str, file_id: str,
    ) -> tuple[JobSchema, str]:
        batch = self._get_or_404(batch_id)
        bf = self.db.query(BatchFile).filter(
            BatchFile.id == file_id, BatchFile.batch_id == batch_id,
        ).first()
        if not bf:
            raise NotFoundError(
                message=f"文件不存在: {file_id}",
                details={"batch_id": batch_id, "file_id": file_id},
            )
        if bf.status != "failed":
            raise ConflictError(
                message=f"文件 {file_id} 状态为 {bf.status}，无法重试",
                details={"file_id": file_id, "status": bf.status},
            )

        bf.retry_count += 1
        bf.status = "queued"
        bf.error_message = None
        bf.started_at = None
        bf.completed_at = None
        bf.latency_ms = None

        staging_path = settings.DATA_DIR / "staging" / f"{bf.id}.pcap"
        if not staging_path.exists() and bf.pcap_id:
            pcap = self.db.query(PcapFile).filter(PcapFile.id == bf.pcap_id).first()
            if pcap and Path(pcap.storage_path).exists():
                staging_dir = settings.DATA_DIR / "staging"
                staging_dir.mkdir(parents=True, exist_ok=True)
                staging_path.write_bytes(Path(pcap.storage_path).read_bytes())

        job = Job(
            batch_id=batch_id,
            batch_file_id=bf.id,
            pcap_id=bf.pcap_id,
            status="pending",
            idempotency_key=f"{bf.id}:{bf.retry_count}",
            retry_count=bf.retry_count,
        )
        self.db.add(job)

        # 批次已结束时，重新设为 processing
        if batch.status in ("partial_failure", "failed", "cancelled"):
            batch.status = "processing"
            batch.completed_at = None
            batch.total_latency_ms = None

        self.db.commit()
        self.db.refresh(job)

        return self._to_job(job), job.id

    def list_batch_files(
        self, batch_id: str, limit: int = 50, offset: int = 0,
        status: str | None = None,
    ) -> list[BatchFileSchema]:
        self._get_or_404(batch_id)
        query = (
            self.db.query(BatchFile)
            .filter(BatchFile.batch_id == batch_id)
            .order_by(BatchFile.sequence)
        )
        if status:
            query = query.filter(BatchFile.status == status)
        files = query.offset(offset).limit(limit).all()
        return [self._to_file(f) for f in files]

    def list_file_jobs(
        self, batch_id: str, file_id: str,
    ) -> list[JobSchema]:
        bf = self.db.query(BatchFile).filter(
            BatchFile.id == file_id, BatchFile.batch_id == batch_id,
        ).first()
        if not bf:
            raise NotFoundError(
                message=f"文件不存在: {file_id}",
                details={"batch_id": batch_id, "file_id": file_id},
            )
        jobs = (
            self.db.query(Job)
            .filter(Job.batch_file_id == file_id)
            .order_by(Job.created_at.desc())
            .all()
        )
        return [self._to_job(j) for j in jobs]

    def delete_batch(self, batch_id: str) -> tuple[list[str], list[Path]]:
        # 删除顺序：取消 running job → 收集 pcap_id → 删除 jobs → batch_files → 批次主记录
        # 返回 (pcap_ids, staging_paths) 供调用方异步清理
        batch = self._get_or_404(batch_id)
        if batch.status == "processing":
            raise ConflictError(
                message=f"批次 {batch_id} 正在处理中，请先取消",
                details={"batch_id": batch_id, "status": batch.status},
            )

        batch_files = (
            self.db.query(BatchFile)
            .filter(BatchFile.batch_id == batch_id)
            .all()
        )
        pcap_ids = [bf.pcap_id for bf in batch_files if bf.pcap_id]
        staging_dir = settings.DATA_DIR / "staging"
        staging_paths = [staging_dir / f"{bf.id}.pcap" for bf in batch_files]

        # 手动删除 jobs（cascade 在某些配置下不生效）
        try:
            for bf in batch_files:
                self.db.query(Job).filter(Job.batch_file_id == bf.id).delete(
                    synchronize_session=False
                )
            self.db.query(BatchFile).filter(
                BatchFile.batch_id == batch_id
            ).delete(synchronize_session=False)
            self.db.delete(batch)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        logger.info(f"批次 {batch_id} 记录已删除（待清理 {len(pcap_ids)} 个 PCAP）")
        return pcap_ids, staging_paths

    def _get_or_404(self, batch_id: str) -> Batch:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise NotFoundError(
                message=f"批次不存在: {batch_id}",
                details={"batch_id": batch_id},
            )
        return batch

    def _to_batch(self, batch: Batch) -> BatchSchema:
        return BatchSchema(
            version=batch.version,
            id=batch.id,
            created_at=datetime_to_iso(batch.created_at),
            name=batch.name,
            status=batch.status,
            source=batch.source,
            tags=batch.tags,
            total_files=batch.total_files,
            completed_files=batch.completed_files,
            failed_files=batch.failed_files,
            total_flow_count=batch.total_flow_count,
            total_alert_count=batch.total_alert_count,
            total_size_bytes=batch.total_size_bytes,
            started_at=datetime_to_iso(batch.started_at) if batch.started_at else None,
            completed_at=datetime_to_iso(batch.completed_at) if batch.completed_at else None,
            total_latency_ms=batch.total_latency_ms,
            error_message=batch.error_message,
        )

    def _to_file(self, bf: BatchFile) -> BatchFileSchema:
        return BatchFileSchema(
            version=bf.version,
            id=bf.id,
            created_at=datetime_to_iso(bf.created_at),
            batch_id=bf.batch_id,
            pcap_id=bf.pcap_id,
            original_filename=bf.original_filename,
            size_bytes=bf.size_bytes,
            sha256=bf.sha256,
            status=bf.status,
            sequence=bf.sequence,
            flow_count=bf.flow_count,
            alert_count=bf.alert_count,
            error_message=bf.error_message,
            reject_reason=bf.reject_reason,
            started_at=datetime_to_iso(bf.started_at) if bf.started_at else None,
            completed_at=datetime_to_iso(bf.completed_at) if bf.completed_at else None,
            latency_ms=bf.latency_ms,
            retry_count=bf.retry_count,
        )

    def _to_job(self, job: Job) -> JobSchema:
        return JobSchema(
            version=job.version,
            id=job.id,
            created_at=datetime_to_iso(job.created_at),
            batch_id=job.batch_id,
            batch_file_id=job.batch_file_id,
            pcap_id=job.pcap_id,
            status=job.status,
            current_stage=job.current_stage,
            stages_log=job.stages_log if isinstance(job.stages_log, list) else None,
            retry_count=job.retry_count,
            started_at=datetime_to_iso(job.started_at) if job.started_at else None,
            completed_at=datetime_to_iso(job.completed_at) if job.completed_at else None,
            latency_ms=job.latency_ms,
            error_message=job.error_message,
        )
