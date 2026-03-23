"""
数据摄取服务。
负责 PCAP 文件上传、存储与管理。
"""

from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnsupportedMediaError
from app.core.logging import get_logger
from app.core.utils import (
    generate_uuid,
    compute_file_hash,
    is_valid_pcap_filename,
    sanitize_filename,
    datetime_to_iso,
)
from app.models.pcap import PcapFile
from app.models.flow import Flow
from app.models.alert import Alert, alert_flows
from app.models.pipeline import PipelineRunModel
from app.models.scenario import Scenario, ScenarioRun
from app.schemas.pcap import PcapFileSchema

logger = get_logger(__name__)


class IngestionService:
    """PCAP 文件摄取与管理服务。"""

    def __init__(self, db: Session):
        self.db = db

    def save_pcap(self, file: BinaryIO, filename: str) -> PcapFileSchema:
        """
        保存上传的 PCAP 文件。

        参数：
            file: 包含 PCAP 数据的类文件对象
            filename: 原始文件名

        返回：
            包含文件元数据的 PcapFileSchema

        异常：
            UnsupportedMediaError: 当文件不是有效 PCAP 时抛出
        """
        # 校验文件名
        if not is_valid_pcap_filename(filename):
            raise UnsupportedMediaError(
                message=f"Invalid file extension. Expected .pcap or .pcapng, got: {filename}",
                details={"filename": filename},
            )

        # 生成唯一 ID 与存储路径
        pcap_id = generate_uuid()
        safe_filename = sanitize_filename(filename)
        storage_path = settings.PCAP_DIR / f"{pcap_id}.pcap"

        # 写入磁盘
        content = file.read()
        size_bytes = len(content)

        # 基础 PCAP 魔数校验
        if not self._is_valid_pcap_magic(content):
            raise UnsupportedMediaError(
                message="File does not appear to be a valid PCAP file (invalid magic number)",
                details={"filename": filename},
            )

        storage_path.write_bytes(content)
        logger.info(f"Saved PCAP file: {pcap_id} ({size_bytes} bytes)")

        # 计算哈希（可选但有帮助）
        file_hash = compute_file_hash(storage_path)

        # 创建数据库记录
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
        根据 ID 获取 PCAP 文件。

        参数：
            pcap_id: PCAP 文件 UUID

        返回：
            PcapFileSchema

        异常：
            NotFoundError: 当 PCAP 不存在时抛出
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
        分页列出 PCAP 文件。

        参数：
            limit: 最大返回数量
            offset: 跳过的记录数

        返回：
            PcapFileSchema 列表
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
        获取内部使用的原始 PcapFile 模型。

        参数：
            pcap_id: PCAP 文件 UUID

        返回：
            PcapFile 模型

        异常：
            NotFoundError: 当 PCAP 不存在时抛出
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
        更新 PCAP 处理状态。

        参数：
            pcap_id: PCAP 文件 UUID
            status: 新状态
            progress: 处理进度（0-100）
            flow_count: 提取到的流数量
            alert_count: 生成的告警数量
            error_message: 失败时的错误信息

        返回：
            更新后的 PcapFileSchema
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
        """将 ORM 模型转换为 Pydantic Schema。"""
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
        检查内容是否以有效的 PCAP 魔数开头。

        PCAP: 0xa1b2c3d4 或 0xd4c3b2a1（小端/大端）
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


    def _find_orphan_alerts(self, flow_ids: list[str]) -> list[str]:
        """
        找出仅通过给定 flow_ids 关联的 alerts。
        即：alert 的所有关联 flow 都在 flow_ids 列表中，
        没有其他 PCAP 的 flow 与之关联。
        """
        from sqlalchemy import func, select

        # 找出与这些 flow 关联的所有 alert_id
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

        # 对每个 alert，检查是否还有关联到其他 PCAP 的 flow
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
        """删除磁盘文件，文件不存在时记录警告日志。"""
        from pathlib import Path
        path = Path(storage_path)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted PCAP disk file: {storage_path}")
        else:
            logger.warning(f"PCAP disk file not found (already removed?): {storage_path}")


    def delete_pcap(self, pcap_id: str) -> None:
        """
        删除 PCAP 文件及所有关联数据。

        删除顺序：alert_flows → alerts → flows → pipeline_runs → pcap_files
        事务成功后删除磁盘文件。

        Raises:
            NotFoundError: PCAP 不存在
            ConflictError: PCAP 正在处理中
        """
        # 1. 查询并校验
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

        # 2. 在事务中按顺序删除关联数据
        try:
            # 获取该 PCAP 的所有 flow_id
            flow_ids = [fid for (fid,) in
                        self.db.query(Flow.id).filter(Flow.pcap_id == pcap_id).all()]

            if flow_ids:
                # 先找出仅属于该 PCAP 的 alerts（必须在删除 alert_flows 之前查询）
                alert_ids_to_delete = self._find_orphan_alerts(flow_ids)

                # 删除 alert_flows 关联记录
                self.db.execute(
                    alert_flows.delete().where(alert_flows.c.flow_id.in_(flow_ids))
                )

                # 删除孤立 alerts
                if alert_ids_to_delete:
                    self.db.query(Alert).filter(Alert.id.in_(alert_ids_to_delete)).delete(
                        synchronize_session=False
                    )

                # 删除 flows
                self.db.query(Flow).filter(Flow.pcap_id == pcap_id).delete(
                    synchronize_session=False
                )

            # 删除 pipeline_runs
            self.db.query(PipelineRunModel).filter(
                PipelineRunModel.pcap_id == pcap_id
            ).delete(synchronize_session=False)

            # 删除 scenario_runs 和 scenarios
            scenario_ids = [
                sid for (sid,) in
                self.db.query(Scenario.id).filter(Scenario.pcap_id == pcap_id).all()
            ]
            if scenario_ids:
                self.db.query(ScenarioRun).filter(
                    ScenarioRun.scenario_id.in_(scenario_ids)
                ).delete(synchronize_session=False)
                self.db.query(Scenario).filter(
                    Scenario.pcap_id == pcap_id
                ).delete(synchronize_session=False)

            # 删除 pcap_files 主记录
            self.db.delete(pcap)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        # 3. 事务成功后删除磁盘文件
        self._remove_disk_file(storage_path)



