
export type API_MODE_TYPE = 'mock' | 'real';

export interface PcapFile {
  version?: string;
  id: string; // uuid
  created_at: string; // ISO8601
  filename: string;
  size_bytes: number;
  status: 'uploaded' | 'processing' | 'done' | 'failed';
  progress?: number; // 0-100
  flow_count?: number;
  alert_count?: number;
}

export interface FlowRecord {
  version?: string;
  id: string;
  created_at: string;
  pcap_id: string;
  ts_start: string;
  ts_end: string;
  src_ip: string;
  src_port: number;
  dst_ip: string;
  dst_port: number;
  proto: string;
  packets_fwd: number;
  packets_bwd: number;
  bytes_fwd: number;
  bytes_bwd: number;
  features: Record<string, any>;
  anomaly_score: number;
  label?: string | null;
}

export interface Alert {
  version: string;
  id: string;
  created_at: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'new' | 'triaged' | 'investigating' | 'resolved' | 'false_positive';
  type: string;
  time_window: {
    start: string;
    end: string;
  };
  entities: {
    primary_src_ip: string;
    primary_dst_ip?: string;
    primary_service?: {
      proto: string;
      dst_port: number;
    };
  };
  evidence: {
    flow_ids: string[];
    top_flows: Array<{
      flow_id: string;
      anomaly_score: number;
      summary: string;
    }>;
    top_features: Array<{
      name: string;
      value: number | string;
      direction?: string;
    }>;
    pcap_ref: {
      pcap_id: string;
      offset_hint?: number | null;
    };
  };
  aggregation?: {
    rule: string;
    group_key: string;
    count_flows: number;
  };
  agent?: {
    triage_summary: string | null;
    investigation_id: string | null;
    recommendation_id: string | null;
  };
  twin?: {
    plan_id: string | null;
    dry_run_id: string | null;
  };
  tags?: string[];
  notes?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  risk: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  weight: number;
  protocols: string[];
  services: Array<{proto: string, port: number}>;
  alert_ids: string[];
  activeIntervals: [string, string][];
}

export interface GraphResponse {
  version: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: {
    start: string;
    end: string;
    mode: string;
  };
}

export interface EvidenceChainNode {
  id: string;
  type: 'alert' | 'flow' | 'feature' | 'hypothesis' | 'action' | 'dryrun';
  label: string;
}

export interface EvidenceChainEdge {
  source: string;
  target: string;
  type: 'supports' | 'explains' | 'inferred_as' | 'leads_to' | 'simulated_by';
}

export interface EvidenceChain {
  version: string;
  id: string;
  created_at: string;
  alert_id: string;
  nodes: EvidenceChainNode[];
  edges: EvidenceChainEdge[];
}

export interface Investigation {
    version: string;
    id: string;
    created_at: string;
    alert_id: string;
    hypothesis: string;
    why: string[];
    impact: {
        scope: string[];
        confidence: number;
    };
    next_steps: string[];
    safety_note?: string;
}

export interface Recommendation {
    version: string;
    id: string;
    created_at: string;
    alert_id: string; // Add missing fields
    actions: Array<{
        title: string;
        type: string;
        target: any; // Can be complex object or string
        params: any;
        risk: string;
        rollback: any;
    }>
}

export interface ActionPlan {
    version?: string;
    id: string;
    created_at: string;
    alert_id: string;
    source: 'agent' | 'manual';
    actions: any[]; 
    notes?: string;
}

export interface DryRunResult {
    version?: string;
    id: string;
    created_at?: string;
    alert_id: string;
    plan_id: string;
    impact: {
        impacted_nodes_count?: number;
        reachability_drop?: number;
        service_disruption_risk?: number;
        warnings?: string[];
        /** Per-node risk score changes: nodeId → new risk after action */
        node_risk_deltas?: Record<string, number>;
        /** Per-edge weight changes: edgeId → new weight after action */
        edge_weight_deltas?: Record<string, number>;
        [key: string]: any;
    };
    alternative_paths?: Array<{
        from: string;
        to: string;
        path: string[];
    }>;
    explain?: string[];
}

export interface Scenario {
    version?: string;
    id: string;
    created_at?: string;
    name: string;
    description?: string;
    tags?: string[];
    pcap_ref: {
        pcap_id: string;
    };
    expectations: {
        min_alerts: number;
        must_have?: Array<{ type: string; severity_at_least?: string }>;
        evidence_chain_contains?: string[];
        dry_run_required: boolean;
    };
}

export interface ScenarioRunResult {
    version?: string;
    id: string;
    created_at?: string;
    scenario_id: string;
    status: 'pass' | 'fail';
    checks: Array<{
        name: string;
        pass: boolean;
        details?: any;
    }>;
    metrics: {
        alert_count: number;
        high_severity_count: number;
        avg_dry_run_risk: number;
        processing_time_ms?: number;
        [key: string]: number | undefined;
    };
}
