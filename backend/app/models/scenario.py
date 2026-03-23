"""
场景模型：Scenario 与 ScenarioRun。
遵循附录F第 10、11 节（scenarios 与 scenario_runs 表）。
"""

from sqlalchemy import String, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Scenario(BaseModel):
    """
    回归测试场景定义。

    对应 DOC C C4.1 Scenario schema。
    """

    __tablename__ = "scenarios"

    # 场景元数据
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 引用 pcap（拆分后便于 join）
    pcap_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pcap_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 完整 Scenario JSON 载荷（expectations、tags 等）
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联关系
    pcap = relationship("PcapFile", backref="scenarios")

    # 索引（附录F 10.2）
    __table_args__ = (
        UniqueConstraint("name", name="uq_scenario_name"),
        Index("idx_scenario_created", "created_at"),
        Index("idx_scenario_pcap", "pcap_id"),
    )

    def __repr__(self) -> str:
        return f"<Scenario(id={self.id}, name={self.name})>"


class ScenarioRun(BaseModel):
    """
    场景执行结果。

    对应 DOC C C4.2 ScenarioRunResult schema。
    """

    __tablename__ = "scenario_runs"

    # 指向 scenarios 的外键
    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 执行结果状态
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pass, fail

    # 完整 ScenarioRunResult JSON 载荷
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联关系
    scenario = relationship("Scenario", backref="runs")

    # 索引（附录F 11.2）
    __table_args__ = (
        Index("idx_run_scenario_created", "scenario_id", "created_at"),
        Index("idx_run_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ScenarioRun(id={self.id}, scenario_id={self.scenario_id}, status={self.status})>"
