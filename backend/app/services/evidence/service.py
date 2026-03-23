"""
证据链服务。
为告警可视化构建证据链。
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
用于构建证据链的服务。

遵循 DOC B B4.8 规范。
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
        
        # 解析 JSON 字段
        evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
        
        # 添加 alert 节点
        alert_node_id = f"alert:{alert.id}"
        nodes.append(EvidenceNode(
            id=alert_node_id,
            type="alert",
            label=f"{alert.type} suspected ({alert.severity})",
        ))
        
        # 添加 flow 节点
        top_flows = evidence.get("top_flows", [])
        for flow_info in top_flows[:5]:  # 最多取前 5 条
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
        
        # 添加特征节点
        top_features = evidence.get("top_features", [])

        # --- 兜底：若 top_features 为空，则从 DB Flow 记录提取 ---
        if not top_features:
            top_features = self._extract_features_from_flows(
                evidence.get("flow_ids", [])
            )

        for feature in top_features[:5]:  # 最多取前 5 条
            feat_node_id = f"feat:{feature['name']}"
            nodes.append(EvidenceNode(
                id=feat_node_id,
                type="feature",
                label=f"{feature['name']}={feature['value']} ({feature['direction']})",
            ))
            
            # 将特征连接到首条 flow（简化策略）
            if top_flows:
                edges.append(EvidenceEdge(
                    source=feat_node_id,
                    target=f"flow:{top_flows[0]['flow_id']}",
                    type="explains",
                ))
        
        # 如存在，添加 investigation 节点
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
        
        # 如存在，添加 recommendation/action 节点
        recommendation_id = agent_data.get("recommendation_id")
        if recommendation_id:
            from app.models.recommendation import Recommendation
            rec = self.db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
            
            if rec:
                rec_data = json.loads(rec.payload) if isinstance(rec.payload, str) else rec.payload
                actions = rec_data.get("actions", [])
                
                for i, action in enumerate(actions[:3]):  # 最多取 3 个 action
                    action_node_id = f"act:{i+1}"
                    nodes.append(EvidenceNode(
                        id=action_node_id,
                        type="action",
                        label=action.get("title", "Unknown action")[:40],
                    ))
                    
                    # 若存在 hypothesis 则从其连出，否则从 alert 连出
                    source = f"hyp:{investigation_id[:8]}" if investigation_id else alert_node_id
                    edges.append(EvidenceEdge(
                        source=source,
                        target=action_node_id,
                        type="leads_to",
                    ))
        
        # 如存在，添加 dry-run 节点
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
                
                # 若存在 action，则从最后一个 action 连出
                action_nodes = [n for n in nodes if n.type == "action"]
                if action_nodes:
                    edges.append(EvidenceEdge(
                        source=action_nodes[-1].id,
                        target=dry_node_id,
                        type="simulated_by",
                    ))
        
        # 创建证据链
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
        
        # 缓存证据链
        chain_model = EvidenceChain(
            id=chain_id,
            created_at=now,
            alert_id=alert.id,
            payload=chain.model_dump_json(),
        )
        
        # 若存在旧链，则先删除
        self.db.query(EvidenceChain).filter(EvidenceChain.alert_id == alert.id).delete()
        self.db.add(chain_model)
        self.db.commit()
        
        logger.info(f"Built evidence chain {chain_id} for alert {alert.id}")
        return chain

    # ------------------------------------------------------------------
    # 兜底特征提取
    # ------------------------------------------------------------------

    # 值得展示的特征，按异常解释相关性排序
    _FEATURE_CANDIDATES = [
        "syn_count", "rst_ratio", "total_packets", "total_bytes",
        "bytes_per_packet", "flow_duration_ms", "iat_mean_ms", "iat_std_ms",
        "fwd_ratio_packets", "fwd_ratio_bytes", "psh_count", "fin_count",
        "avg_pkt_size_fwd", "avg_pkt_size_bwd", "syn_ratio", "rst_count",
    ]

    def _extract_features_from_flows(self, flow_ids: list[str]) -> list[dict]:
        """
        直接从 DB Flow 记录提取特征，并按绝对偏差选取前 3。
        当 AlertingService 未写入 top_features 时，作为证据链兜底。
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

        # 对候选特征聚合其最大绝对值
        agg: dict[str, float] = {}
        for flow in flows:
            feat_data = json.loads(flow.features) if isinstance(flow.features, str) else flow.features
            for name in self._FEATURE_CANDIDATES:
                val = feat_data.get(name)
                if isinstance(val, (int, float)):
                    agg[name] = max(agg.get(name, 0.0), abs(val))

        # 按聚合值降序取前 3
        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        result = []
        for name, value in ranked[:3]:
            result.append({
                "name": name,
                "value": round(value, 4),
                "direction": "high" if value > 0 else "low",
            })
        return result
