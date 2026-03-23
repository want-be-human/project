"""
Services module.
Export all service classes per DOC B B4.
"""

from app.services.ingestion.service import IngestionService
from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.service import DetectionService
from app.services.alerting.service import AlertingService
from app.services.topology.service import TopologyService
from app.services.agent.service import AgentService
from app.services.evidence.service import EvidenceService
from app.services.twin.service import TwinService
from app.services.plan_compiler.service import PlanCompilerService
from app.services.scenarios.service import ScenariosService
from app.services.threat_enrichment.service import ThreatEnrichmentService
from app.services.stream import (
    get_connection_manager,
    broadcast_pcap_progress,
    broadcast_pcap_done,
    broadcast_alert_created,
    broadcast_alert_updated,
    broadcast_dryrun_created,
    broadcast_scenario_done,
    get_event_bus,
)

__all__ = [
    # B4.1 数据摄取
    "IngestionService",
    # B4.2 解析
    "ParsingService",
    # B4.3 特征提取
    "FeaturesService",
    # B4.4 检测
    "DetectionService",
    # B4.5 告警
    "AlertingService",
    # B4.6 拓扑
    "TopologyService",
    # B4.7 智能体
    "AgentService",
    # B4.8 证据
    "EvidenceService",
    # B4.9 数字孪生
    "TwinService",
    # B4.9b 方案编译器
    "PlanCompilerService",
    # B4.10 场景
    "ScenariosService",
    # B4.12 威胁增强（模块 E）
    "ThreatEnrichmentService",
    # B4.11 流式处理与事件总线
    "get_connection_manager",
    "broadcast_pcap_progress",
    "broadcast_pcap_done",
    "broadcast_alert_created",
    "broadcast_alert_updated",
    "broadcast_dryrun_created",
    "broadcast_scenario_done",
    "get_event_bus",
]
