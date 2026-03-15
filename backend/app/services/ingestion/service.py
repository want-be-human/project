"""
Ingestion service.
Handles PCAP file upload, storage, and management.
"""

from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, UnsupportedMediaError
from app.core.logging import get_logger
from app.core.utils import (
    generate_uuid,
    compute_file_hash,
    is_valid_pcap_filename,
    sanitize_filename,
    datetime_to_iso,
)
from app.models.pcap import PcapFile
from app.schemas.pcap import PcapFileSchema

logger = get_logger(__name__)


class IngestionService:
    """Service for PCAP file ingestion and management."""

    def __init__(self, db: Session):
        self.db = db

    def save_pcap(self, file: BinaryIO, filename: str) -> PcapFileSchema:
        """
        Save uploaded PCAP file.
        
        Args:
            file: File-like object containing PCAP data
            filename: Original filename
            
        Returns:
            PcapFileSchema with file metadata
            
        Raises:
            UnsupportedMediaError: If file is not a valid PCAP
        """
        # Validate filename
        if not is_valid_pcap_filename(filename):
            raise UnsupportedMediaError(
                message=f"Invalid file extension. Expected .pcap or .pcapng, got: {filename}",
                details={"filename": filename},
            )

        # Generate unique ID and storage path
        pcap_id = generate_uuid()
        safe_filename = sanitize_filename(filename)
        storage_path = settings.PCAP_DIR / f"{pcap_id}.pcap"

        # Write file to disk
        content = file.read()
        size_bytes = len(content)

        # Basic PCAP magic number validation
        if not self._is_valid_pcap_magic(content):
            raise UnsupportedMediaError(
                message="File does not appear to be a valid PCAP file (invalid magic number)",
                details={"filename": filename},
            )

        storage_path.write_bytes(content)
        logger.info(f"Saved PCAP file: {pcap_id} ({size_bytes} bytes)")

        # Compute hash (optional but useful)
        file_hash = compute_file_hash(storage_path)

        # Create database record
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
        """
        Get PCAP file by ID.
        
        Args:
            pcap_id: UUID of the PCAP file
            
        Returns:
            PcapFileSchema
            
        Raises:
            NotFoundError: If PCAP not found
        """
        pcap = self.db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            raise NotFoundError(
                message=f"PCAP file not found: {pcap_id}",
                details={"pcap_id": pcap_id},
            )
        return self._to_schema(pcap)

    def list_pcaps(self, limit: int = 50, offset: int = 0) -> list[PcapFileSchema]:
        """
        List PCAP files with pagination.
        
        Args:
            limit: Maximum number of results
            offset: Number of records to skip
            
        Returns:
            List of PcapFileSchema
        """
        pcaps = (
            self.db.query(PcapFile)
            .order_by(PcapFile.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_schema(p) for p in pcaps]

    def get_pcap_model(self, pcap_id: str) -> PcapFile:
        """
        Get raw PcapFile model for internal use.
        
        Args:
            pcap_id: UUID of the PCAP file
            
        Returns:
            PcapFile model
            
        Raises:
            NotFoundError: If PCAP not found
        """
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
        """
        Update PCAP processing status.
        
        Args:
            pcap_id: UUID of the PCAP file
            status: New status
            progress: Processing progress (0-100)
            flow_count: Number of flows extracted
            alert_count: Number of alerts generated
            error_message: Error message if failed
            
        Returns:
            Updated PcapFileSchema
        """
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
        """Convert ORM model to Pydantic schema."""
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

    def _is_valid_pcap_magic(self, content: bytes) -> bool:
        """
        Check if content starts with valid PCAP magic number.
        
        PCAP: 0xa1b2c3d4 or 0xd4c3b2a1 (little/big endian)
        PCAPNG: 0x0a0d0d0a
        """
        if len(content) < 4:
            return False

        magic = content[:4]
        valid_magics = [
            b"\xa1\xb2\xc3\xd4",  # PCAP big endian
            b"\xd4\xc3\xb2\xa1",  # PCAP little endian
            b"\xa1\xb2\x3c\x4d",  # PCAP-NG big endian (modified)
            b"\x4d\x3c\xb2\xa1",  # PCAP-NG little endian (modified)
            b"\x0a\x0d\x0d\x0a",  # PCAP-NG Section Header Block
        ]
        return magic in valid_magics
