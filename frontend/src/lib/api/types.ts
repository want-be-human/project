
export type API_MODE_TYPE = 'mock' | 'real';

export interface PcapFile {
  id: string; // uuid
  created_at: string; // ISO8601
  filename: string;
  size: number;
  status: 'uploaded' | 'processing' | 'done' | 'failed';
  progress?: number; // 0-100
  flow_count?: number;
  alert_count?: number;
}

export interface FlowRecord {
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
  status: 'new' | 'triaged' | 'resolved' | 'false_positive';
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
    };
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
    why: string;
    confidence: number;
    next_steps: string[];
}

export interface Recommendation {
    actions: Array<{
        title: string;
        type: string;
        target: string;
        params: any;
        risk: string;
        rollback: string;
    }>
}

export interface ActionPlan {
    id: string;
    alert_id: string;
    actions: any[]; 
    source: 'agent' | 'manual';
    created_at: string;
}

export interface DryRunResult {
    id: string;
    plan_id: string;
    impact: any; 
    warnings: string[];
    reachability_drop: number;
    service_disruption_risk: number;
}

export interface Scenario {
    id: string;
    name: string;
    description?: string;
    tags?: string[];
    pcap_ref: {
        pcap_id: string;
    };
    min_alerts: number;
    dry_run_required: boolean;
}

export interface ScenarioRunResult {
    id: string;
    scenario_id: string;
    status: 'pass' | 'fail';
    checks: Array<{
        name: string;
        pass: boolean;
        details?: string;
    }>;
    metrics: {
        alert_count: number;
        high_severity_count: number;
        avg_dry_run_risk: number;
        [key: string]: number;
    };
}
