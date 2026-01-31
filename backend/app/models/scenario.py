"""
Scenario Models: Scenario and ScenarioRun.
Follows 附录F Section 10 & 11 - scenarios and scenario_runs tables.
"""

from sqlalchemy import String, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Scenario(BaseModel):
    """
    Scenario definition for regression testing.
    
    Maps to DOC C C4.1 Scenario schema.
    """

    __tablename__ = "scenarios"

    # Scenario metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Reference to pcap (拆分出来便于 join)
    pcap_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pcap_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Full Scenario JSON payload (expectations, tags, etc.)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationship
    pcap = relationship("PcapFile", backref="scenarios")

    # Indexes (附录F 10.2)
    __table_args__ = (
        UniqueConstraint("name", name="uq_scenario_name"),
        Index("idx_scenario_created", "created_at"),
        Index("idx_scenario_pcap", "pcap_id"),
    )

    def __repr__(self) -> str:
        return f"<Scenario(id={self.id}, name={self.name})>"


class ScenarioRun(BaseModel):
    """
    Scenario execution result.
    
    Maps to DOC C C4.2 ScenarioRunResult schema.
    """

    __tablename__ = "scenario_runs"

    # Foreign key to scenarios
    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Result status
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pass, fail

    # Full ScenarioRunResult JSON payload
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationship
    scenario = relationship("Scenario", backref="runs")

    # Indexes (附录F 11.2)
    __table_args__ = (
        Index("idx_run_scenario_created", "scenario_id", "created_at"),
        Index("idx_run_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ScenarioRun(id={self.id}, scenario_id={self.scenario_id}, status={self.status})>"
