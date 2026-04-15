"""场景模型：Scenario 与 ScenarioRun（附录F 第 10、11 节）。"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Scenario(BaseModel):
    """回归测试场景定义（DOC C C4.1 Scenario schema）。"""

    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active | archived

    pcap_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pcap_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 完整 Scenario JSON 载荷（expectations、tags 等）
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    pcap = relationship("PcapFile", backref="scenarios")

    __table_args__ = (
        UniqueConstraint("name", name="uq_scenario_name"),
        Index("idx_scenario_created", "created_at"),
        Index("idx_scenario_pcap", "pcap_id"),
        Index("idx_scenario_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Scenario(id={self.id}, name={self.name})>"


class ScenarioRun(BaseModel):
    """场景执行结果（DOC C C4.2 ScenarioRunResult schema）。"""

    __tablename__ = "scenario_runs"

    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pass, fail
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    stages_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    validation_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pipeline_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    scenario = relationship("Scenario", backref="runs")

    __table_args__ = (
        Index("idx_run_scenario_created", "scenario_id", "created_at"),
        Index("idx_run_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ScenarioRun(id={self.id}, scenario_id={self.scenario_id}, status={self.status})>"
