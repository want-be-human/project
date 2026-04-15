from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnsupportedMediaError
from app.core.logging import get_logger
from app.core.utils import (
    generate_uuid,
    stream_save_and_hash,
    is_valid_pcap_filename,
    sanitize_filename,
    datetime_to_iso,
    utc_now,
)
from app.models.pcap import PcapFile
from app.models.flow import Flow
from app.models.alert import Alert, alert_flows
from app.models.pipeline import PipelineRunModel
from app.models.batch import BatchFile, Batch
from app.schemas.pcap import PcapFileSchema

logger = get_logger(__name__)

_VALID_PCAP_MAGICS = [
    b"\xa1\xb2\xc3\xd4",
    b"\xd4\xc3\xb2\xa1", 
    b"\xa1\xb2\x3c\x4d",  
    b"\x4d\x3c\xb2\xa1", 
    b"\x0a\x0d\x0d\x0a",  
]


class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def save_pcap(self, file: BinaryIO, filename: str) -> PcapFileSchema:
        if not is_valid_pcap_filename(filename):
            raise UnsupportedMediaError(
                message=f"Invalid file extension. Expected .pcap or .pcapng, got: {filename}",
                details={"filename": filename},
            )

        pcap_id = generate_uuid()
        safe_filename = sanitize_filename(filename)
        storage_path = settings.PCAP_DIR / f"{pcap_id}.pcap"

        size_bytes, file_hash, magic = stream_save_and_hash(file, storage_path)

        if not self._is_valid_pcap_magic(magic):
            storage_path.unlink(missing_ok=True)
            raise UnsupportedMediaError(
                message="File does not appear to be a valid PCAP file (invalid magic number)",
                details={"filename": filename},
            )

        logger.info(f"已保存 PCAP 文件: {pcap_id} ({size_bytes} 字节)")

        pcap_record = PcapFile(
            id=pcap_id,
            filename=safe_filename,
            storage_path=str(storage_path),
            sha256=file_hash,
            size_bytes=size_bytes,
            status="uploaded",
            progress=0,
            flow_count=0,
            alert_count=0,
        )

        self.db.add(pcap_record)
        self.db.commit()
        self.db.refresh(pcap_record)

        return self._to_schema(pcap_record)

    def get_pcap(self, pcap_id: str) -> PcapFileSchema:
        pcap = self.db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            raise NotFoundError(
                message=f"PCAP file not found: {pcap_id}",
                details={"pcap_id": pcap_id},
            )
        return self._to_schema(pcap)

    def list_pcaps(self, limit: int = 50, offset: int = 0) -> list[PcapFileSchema]:
        pcaps = (
            self.db.query(PcapFile)
            .order_by(PcapFile.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_schema(p) for p in pcaps]

    def get_pcap_model(self, pcap_id: str) -> PcapFile:
        pcap = self.db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            raise NotFoundError(
                message=f"PCAP file not found: {pcap_id}",
                details={"pcap_id": pcap_id},
            )
        return pcap

    def update_status(
        self,
        pcap_id: str,
        status: str,
        progress: int | None = None,
        flow_count: int | None = None,
        alert_count: int | None = None,
        error_message: str | None = None,
    ) -> PcapFileSchema:
        pcap = self.get_pcap_model(pcap_id)

        pcap.status = status
        if progress is not None:
            pcap.progress = progress
        if flow_count is not None:
            pcap.flow_count = flow_count
        if alert_count is not None:
            pcap.alert_count = alert_count
        if error_message is not None:
            pcap.error_message = error_message

        self.db.commit()
        self.db.refresh(pcap)

        return self._to_schema(pcap)

    def _to_schema(self, pcap: PcapFile) -> PcapFileSchema:
        return PcapFileSchema(
            version=pcap.version,
            id=pcap.id,
            created_at=datetime_to_iso(pcap.created_at),
            filename=pcap.filename,
            size_bytes=pcap.size_bytes,
            status=pcap.status,  # type: ignore[arg-type]
            progress=pcap.progress,
            flow_count=pcap.flow_count,
            alert_count=pcap.alert_count,
            error_message=pcap.error_message,
        )

    @staticmethod
    def _is_valid_pcap_magic(magic: bytes) -> bool:
        if len(magic) < 4:
            return False
        return magic[:4] in _VALID_PCAP_MAGICS

    def _find_orphan_alerts(self, flow_ids: list[str]) -> list[str]:
      
        related_alert_ids = [
            aid for (aid,) in
            self.db.execute(
                select(alert_flows.c.alert_id)
                .where(alert_flows.c.flow_id.in_(flow_ids))
                .distinct()
            ).all()
        ]

        if not related_alert_ids:
            return []

        orphan_ids = []
        for aid in related_alert_ids:
            other_flow_count = self.db.execute(
                select(func.count())
                .select_from(alert_flows)
                .where(
                    alert_flows.c.alert_id == aid,
                    ~alert_flows.c.flow_id.in_(flow_ids),
                )
            ).scalar()
            if other_flow_count == 0:
                orphan_ids.append(aid)

        return orphan_ids

    def _remove_disk_file(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            path.unlink()
            logger.info(f"已删除 PCAP 磁盘文件: {storage_path}")
        else:
            logger.warning(f"PCAP 磁盘文件不存在（可能已删除）: {storage_path}")

    def delete_pcap(self, pcap_id: str) -> None:
        """Delete PCAP and all associated data; disk file is removed after commit."""
        pcap = self.db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            raise NotFoundError(
                message=f"PCAP file not found: {pcap_id}",
                details={"pcap_id": pcap_id},
            )
        if pcap.status == "processing":
            raise ConflictError(
                message=f"Cannot delete PCAP {pcap_id}: currently processing",
                details={"pcap_id": pcap_id, "status": pcap.status},
            )

        storage_path = pcap.storage_path

        try:
            related_alert_ids = [
                aid for (aid,) in
                self.db.execute(
                    select(alert_flows.c.alert_id).distinct().where(
                        alert_flows.c.flow_id.in_(
                            select(Flow.id).where(Flow.pcap_id == pcap_id)
                        )
                    )
                ).all()
            ]


            self.db.query(PipelineRunModel).filter(
                PipelineRunModel.pcap_id == pcap_id
            ).delete(synchronize_session=False)

            affected_batch_ids: set[str] = set()
            for bf in self.db.query(BatchFile).filter(
                BatchFile.pcap_id == pcap_id
            ).all():
                affected_batch_ids.add(bf.batch_id)
                bf.status = "failed"
                bf.error_message = "原始文件已删除"
                bf.pcap_id = None

            for bid in affected_batch_ids:
                batch = self.db.query(Batch).filter(Batch.id == bid).first()
                if not batch:
                    continue
                files = self.db.query(BatchFile).filter(
                    BatchFile.batch_id == bid
                ).all()
                batch.total_files = len(files)
                batch.completed_files = sum(1 for f in files if f.status == "done")
                batch.failed_files = sum(1 for f in files if f.status == "failed")
                batch.total_flow_count = sum(f.flow_count for f in files)
                batch.total_alert_count = sum(f.alert_count for f in files)
                actionable = batch.total_files - sum(
                    1 for f in files if f.status in ("rejected", "duplicate")
                )
                if actionable > 0 and (
                    batch.completed_files + batch.failed_files
                ) >= actionable:
                    batch.completed_at = utc_now()
                    batch.status = (
                        "completed" if batch.failed_files == 0
                        else "failed" if batch.completed_files == 0
                        else "partial_failure"
                    )

            self.db.execute(
                text("DELETE FROM pcap_files WHERE id = :pid"),
                {"pid": pcap_id},
            )
            self.db.flush()

            if related_alert_ids:
                orphan_aids = [
                    aid for aid in related_alert_ids
                    if self.db.execute(
                        select(alert_flows.c.alert_id)
                        .where(alert_flows.c.alert_id == aid)
                        .limit(1)
                    ).first() is None
                ]
                if orphan_aids:
                    self.db.query(Alert).filter(Alert.id.in_(orphan_aids)).delete(
                        synchronize_session=False
                    )

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self._remove_disk_file(storage_path)
