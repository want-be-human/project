"""
Pydantic Schemas for API responses.
All schemas strictly follow DOC C v1.1 specifications.
"""

from app.schemas.common import (
    ApiResponse,
    ErrorDetail,
    PaginationParams,
    HealthStatus,
)
from app.schemas.pcap import (
    PcapFileSchema,
    PcapProcessRequest,
    PcapProcessResponse,
)
from app.schemas.flow import (
    FlowRecordSchema,
    FlowQueryParams,
)
from app.schemas.alert import (
    AlertSchema,
    AlertUpdateRequest,
    AlertQueryParams,
    TimeWindow,
    AlertEntities,
    AlertEvidence,
    AlertAggregation,
    AlertAgent,
    AlertTwin,
)
from app.schemas.agent import (
    InvestigationSchema,
    RecommendationSchema,
    TriageRequest,
    TriageResponse,
)
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    CreatePlanRequest,
    DryRunRequest,
    DryRunQueryParams,
    PlanAction,
)
from app.schemas.topology import (
    GraphResponseSchema,
    GraphNode,
    GraphEdge,
    GraphMeta,
    TopologyQueryParams,
)
from app.schemas.evidence import (
    EvidenceChainSchema,
    EvidenceNode,
    EvidenceEdge,
)
from app.schemas.scenario import (
    ScenarioSchema,
    ScenarioRunResultSchema,
    CreateScenarioRequest,
    ScenarioQueryParams,
)
from app.schemas.pipeline import (
    PipelineRunSchema,
    StageRecordSchema,
)

__all__ = [
    # Common
    "ApiResponse",
    "ErrorDetail",
    "PaginationParams",
    "HealthStatus",
    # PCAP
    "PcapFileSchema",
    "PcapProcessRequest",
    "PcapProcessResponse",
    # Flow
    "FlowRecordSchema",
    "FlowQueryParams",
    # Alert
    "AlertSchema",
    "AlertUpdateRequest",
    "AlertQueryParams",
    "TimeWindow",
    "AlertEntities",
    "AlertEvidence",
    "AlertAggregation",
    "AlertAgent",
    "AlertTwin",
    # Agent
    "InvestigationSchema",
    "RecommendationSchema",
    "TriageRequest",
    "TriageResponse",
    # Twin
    "ActionPlanSchema",
    "DryRunResultSchema",
    "CreatePlanRequest",
    "DryRunRequest",
    "DryRunQueryParams",
    "PlanAction",
    # Topology
    "GraphResponseSchema",
    "GraphNode",
    "GraphEdge",
    "GraphMeta",
    "TopologyQueryParams",
    # Evidence
    "EvidenceChainSchema",
    "EvidenceNode",
    "EvidenceEdge",
    # Scenario
    "ScenarioSchema",
    "ScenarioRunResultSchema",
    "CreateScenarioRequest",
    "ScenarioQueryParams",
    # Pipeline
    "PipelineRunSchema",
    "StageRecordSchema",
]
