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
    # B4.1 Ingestion
    "IngestionService",
    # B4.2 Parsing
    "ParsingService",
    # B4.3 Features
    "FeaturesService",
    # B4.4 Detection
    "DetectionService",
    # B4.5 Alerting
    "AlertingService",
    # B4.6 Topology
    "TopologyService",
    # B4.7 Agent
    "AgentService",
    # B4.8 Evidence
    "EvidenceService",
    # B4.9 Twin
    "TwinService",
    # B4.9b Plan Compiler
    "PlanCompilerService",
    # B4.10 Scenarios
    "ScenariosService",
    # B4.12 Threat Enrichment (Module E)
    "ThreatEnrichmentService",
    # B4.11 Stream & EventBus
    "get_connection_manager",
    "broadcast_pcap_progress",
    "broadcast_pcap_done",
    "broadcast_alert_created",
    "broadcast_alert_updated",
    "broadcast_dryrun_created",
    "broadcast_scenario_done",
    "get_event_bus",
]
