"""
Evidence chain service.
Build evidence chain for alert visualization.
"""

import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.alert import Alert
from app.models.evidence import EvidenceChain
from app.schemas.evidence import EvidenceChainSchema, EvidenceNode, EvidenceEdge

logger = get_logger(__name__)


class EvidenceService:
    """
    Service for building evidence chains.
    
    Follows DOC B B4.8 specification.
    """

    def __init__(self, db: Session):
        self.db = db

    def build_evidence_chain(self, alert: Alert) -> EvidenceChainSchema:
        """
        Build evidence chain for an alert.
        
        Args:
            alert: Alert model instance
            
        Returns:
            EvidenceChain schema
        """
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []
        
        # Parse JSON fields
        evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
        
        # Add alert node
        alert_node_id = f"alert:{alert.id}"
        nodes.append(EvidenceNode(
            id=alert_node_id,
            type="alert",
            label=f"{alert.type} suspected ({alert.severity})",
        ))
        
        # Add flow nodes
        top_flows = evidence.get("top_flows", [])
        for flow_info in top_flows[:5]:  # Limit to top 5
            flow_node_id = f"flow:{flow_info['flow_id']}"
            nodes.append(EvidenceNode(
                id=flow_node_id,
                type="flow",
                label=f"{flow_info['summary']} score={flow_info['anomaly_score']:.2f}",
            ))
            edges.append(EvidenceEdge(
                source=flow_node_id,
                target=alert_node_id,
                type="supports",
            ))
        
        # Add feature nodes
        top_features = evidence.get("top_features", [])

        # --- Fallback: if top_features empty, extract from DB Flow records ---
        if not top_features:
            top_features = self._extract_features_from_flows(
                evidence.get("flow_ids", [])
            )

        for feature in top_features[:5]:  # Limit to top 5
            feat_node_id = f"feat:{feature['name']}"
            nodes.append(EvidenceNode(
                id=feat_node_id,
                type="feature",
                label=f"{feature['name']}={feature['value']} ({feature['direction']})",
            ))
            
            # Link features to first flow (simplified)
            if top_flows:
                edges.append(EvidenceEdge(
                    source=feat_node_id,
                    target=f"flow:{top_flows[0]['flow_id']}",
                    type="explains",
                ))
        
        # Add investigation node if exists
        investigation_id = agent_data.get("investigation_id")
        if investigation_id:
            from app.models.investigation import Investigation
            inv = self.db.query(Investigation).filter(Investigation.id == investigation_id).first()
            
            if inv:
                inv_data = json.loads(inv.payload) if isinstance(inv.payload, str) else inv.payload
                hyp_node_id = f"hyp:{investigation_id[:8]}"
                nodes.append(EvidenceNode(
                    id=hyp_node_id,
                    type="hypothesis",
                    label=inv_data.get("hypothesis", "Unknown hypothesis")[:50],
                ))
                edges.append(EvidenceEdge(
                    source=alert_node_id,
                    target=hyp_node_id,
                    type="inferred_as",
                ))
        
        # Add recommendation/action nodes if exists
        recommendation_id = agent_data.get("recommendation_id")
        if recommendation_id:
            from app.models.recommendation import Recommendation
            rec = self.db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
            
            if rec:
                rec_data = json.loads(rec.payload) if isinstance(rec.payload, str) else rec.payload
                actions = rec_data.get("actions", [])
                
                for i, action in enumerate(actions[:3]):  # Limit to 3 actions
                    action_node_id = f"act:{i+1}"
                    nodes.append(EvidenceNode(
                        id=action_node_id,
                        type="action",
                        label=action.get("title", "Unknown action")[:40],
                    ))
                    
                    # Link from hypothesis if exists, otherwise from alert
                    source = f"hyp:{investigation_id[:8]}" if investigation_id else alert_node_id
                    edges.append(EvidenceEdge(
                        source=source,
                        target=action_node_id,
                        type="leads_to",
                    ))
        
        # Add dry-run node if exists
        dry_run_id = twin_data.get("dry_run_id")
        if dry_run_id:
            from app.models.twin import DryRun
            dry_run = self.db.query(DryRun).filter(DryRun.id == dry_run_id).first()
            
            if dry_run:
                dry_data = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                impact = dry_data.get("impact", {})
                
                dry_node_id = f"dry:{dry_run_id[:8]}"
                nodes.append(EvidenceNode(
                    id=dry_node_id,
                    type="dryrun",
                    label=f"risk={impact.get('service_disruption_risk', 0):.2f} reach_drop={impact.get('reachability_drop', 0):.2f}",
                ))
                
                # Link from last action if exists
                action_nodes = [n for n in nodes if n.type == "action"]
                if action_nodes:
                    edges.append(EvidenceEdge(
                        source=action_nodes[-1].id,
                        target=dry_node_id,
                        type="simulated_by",
                    ))
        
        # Create evidence chain
        chain_id = generate_uuid()
        now = utc_now()
        
        chain = EvidenceChainSchema(
            version="1.1",
            id=chain_id,
            created_at=datetime_to_iso(now),
            alert_id=alert.id,
            nodes=nodes,
            edges=edges,
        )
        
        # Cache the chain
        chain_model = EvidenceChain(
            id=chain_id,
            created_at=now,
            alert_id=alert.id,
            payload=chain.model_dump_json(),
        )
        
        # Remove old chain if exists
        self.db.query(EvidenceChain).filter(EvidenceChain.alert_id == alert.id).delete()
        self.db.add(chain_model)
        self.db.commit()
        
        logger.info(f"Built evidence chain {chain_id} for alert {alert.id}")
        return chain

    # ------------------------------------------------------------------
    # Fallback feature extraction
    # ------------------------------------------------------------------

    # Features worth surfacing, ordered by relevance for anomaly explanation
    _FEATURE_CANDIDATES = [
        "syn_count", "rst_ratio", "total_packets", "total_bytes",
        "bytes_per_packet", "flow_duration_ms", "iat_mean_ms", "iat_std_ms",
        "fwd_ratio_packets", "fwd_ratio_bytes", "psh_count", "fin_count",
        "avg_pkt_size_fwd", "avg_pkt_size_bwd", "syn_ratio", "rst_count",
    ]

    def _extract_features_from_flows(self, flow_ids: list[str]) -> list[dict]:
        """
        Pull features directly from DB Flow records and pick the top-3
        by absolute deviation.  Used as evidence-chain fallback when
        AlertingService stored no top_features.
        """
        if not flow_ids:
            return []

        from app.models.flow import Flow

        flows = (
            self.db.query(Flow)
            .filter(Flow.id.in_(flow_ids[:10]))
            .all()
        )
        if not flows:
            return []

        # Aggregate max absolute value per candidate feature
        agg: dict[str, float] = {}
        for flow in flows:
            feat_data = json.loads(flow.features) if isinstance(flow.features, str) else flow.features
            for name in self._FEATURE_CANDIDATES:
                val = feat_data.get(name)
                if isinstance(val, (int, float)):
                    agg[name] = max(agg.get(name, 0.0), abs(val))

        # Sort descending by aggregated value, take top 3
        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        result = []
        for name, value in ranked[:3]:
            result.append({
                "name": name,
                "value": round(value, 4),
                "direction": "high" if value > 0 else "low",
            })
        return result
