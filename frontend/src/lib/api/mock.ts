import { 
  PcapFile, FlowRecord, Alert, GraphResponse, GraphNode, GraphEdge, Investigation, 
  Recommendation, ActionPlan, DryRunResult, Scenario, ScenarioRunResult,
  EvidenceChain, CompilePlanRequest, CompilePlanResponse, CompiledAction
} from './types';
import { wsClient } from '../ws';

// Static imports for contract sample data
import flowSample from '../../../../contract/samples/flow.sample.json';
import alertSample from '../../../../contract/samples/alert.sample.json';
import graphSample from '../../../../contract/samples/graph.sample.json';
import investigationSample from '../../../../contract/samples/investigation.sample.json';
import recommendationSample from '../../../../contract/samples/recommendation.sample.json';
import actionPlanSample from '../../../../contract/samples/actionplan.sample.json';
import dryRunSample from '../../../../contract/samples/dryrun.sample.json';
import evidenceChainSample from '../../../../contract/samples/evidencechain.sample.json';
import scenarioSample from '../../../../contract/samples/scenario.sample.json';
import scenarioRunResultSample from '../../../../contract/samples/scenario_run_result.sample.json';

// ── Per-alert variation data ──
const ALERT_VARIATIONS: Array<{
    type: string;
    srcIp: string;
    dstIp: string;
    service: { proto: string; dst_port: number };
    hypothesis: string;
    triageSummary: string;
    whyReasons: string[];
    actionTitle: string;
    actionType: string;
    impactedNodes: number;
    reachabilityDrop: number;
    disruptionRisk: number;
    warnings: string[];
    altPath: { from: string; to: string; path: string[] };
    explain: string[];
    nodeRiskDeltas: Record<string, number>;
    edgeWeightDeltas: Record<string, number>;
}> = [
    {
        type: 'bruteforce',
        srcIp: '192.0.2.10', dstIp: '198.51.100.20',
        service: { proto: 'TCP', dst_port: 22 },
        hypothesis: 'SSH brute-force attack from external source 192.0.2.10',
        triageSummary: 'Automated triage: High-volume SSH brute-force detected from 192.0.2.10 targeting 198.51.100.20:22. 120 SYN packets in 5 min window.',
        whyReasons: ['120 TCP SYN packets to port 22 in 5 min', 'Source IP has no prior communication history', 'Inter-arrival time ~50ms consistent with automated tooling'],
        actionTitle: 'Block source IP 192.0.2.10',
        actionType: 'block_ip',
        impactedNodes: 2, reachabilityDrop: 0.18, disruptionRisk: 0.62,
        warnings: ['May isolate admin host 198.51.100.20', 'Blocking 192.0.2.10 affects 3 active connections'],
        altPath: { from: 'ip:192.0.2.10', to: 'ip:198.51.100.20', path: ['ip:192.0.2.10','ip:10.0.0.1','ip:198.51.100.20'] },
        explain: ['Blocking ip:192.0.2.10 removes 2 edges from graph', 'Reachability reduced for 18% of nodes', 'Alternative path via gateway 10.0.0.1'],
        nodeRiskDeltas: { 'ip:192.0.2.10': 0.15, 'ip:198.51.100.20': 0.10 },
        edgeWeightDeltas: { 'e1': 0, 'e5': 2 },
    },
    {
        type: 'port_scan',
        srcIp: '10.0.0.100', dstIp: '192.0.2.50',
        service: { proto: 'TCP', dst_port: 443 },
        hypothesis: 'Internal port scan from compromised host 10.0.0.100',
        triageSummary: 'Automated triage: Port scan activity detected. Host 10.0.0.100 probing 192.0.2.50 across multiple ports (22,80,443,3389).',
        whyReasons: ['Connections to 4+ distinct ports in 2 min window', '10.0.0.100 not typically a scanner', 'Behavioural deviation score 0.89'],
        actionTitle: 'Isolate host 10.0.0.100',
        actionType: 'isolate_host',
        impactedNodes: 3, reachabilityDrop: 0.25, disruptionRisk: 0.45,
        warnings: ['Isolating 10.0.0.100 affects 2 outbound connections', 'Host may be running legitimate monitoring'],
        altPath: { from: 'ip:10.0.0.100', to: 'ip:192.0.2.50', path: ['ip:10.0.0.100','ip:10.0.0.1','ip:198.51.100.1','ip:192.0.2.50'] },
        explain: ['Isolating ip:10.0.0.100 removes 2 edges (e5, e7)', 'Nodes 192.0.2.10 and 198.51.100.20 lose one inbound path each', 'Low service disruption — host is not a gateway'],
        nodeRiskDeltas: { 'ip:10.0.0.100': 0.10, 'ip:192.0.2.10': 0.50, 'ip:198.51.100.20': 0.12 },
        edgeWeightDeltas: { 'e5': 0, 'e7': 0 },
    },
    {
        type: 'data_exfiltration',
        srcIp: '192.0.2.50', dstIp: '203.0.113.5',
        service: { proto: 'TCP', dst_port: 443 },
        hypothesis: 'Possible data exfiltration via encrypted channel from server 192.0.2.50',
        triageSummary: 'Automated triage: Anomalous outbound data volume from server 192.0.2.50 to external 203.0.113.5 over HTTPS. Payload size 3x historical baseline.',
        whyReasons: ['Outbound volume 340MB in 30 min (baseline 110MB)', 'Destination 203.0.113.5 first seen today', 'Encrypted channel prevents payload inspection'],
        actionTitle: 'Rate-limit outbound to 203.0.113.5',
        actionType: 'rate_limit_service',
        impactedNodes: 1, reachabilityDrop: 0.05, disruptionRisk: 0.20,
        warnings: ['Rate-limiting may slow legitimate HTTPS traffic from server'],
        altPath: { from: 'ip:192.0.2.50', to: 'ip:203.0.113.5', path: ['ip:192.0.2.50','ip:198.51.100.1','ip:203.0.113.5'] },
        explain: ['Rate-limiting ip:192.0.2.50→ip:203.0.113.5 reduces edge weight', 'Minimal reachability impact (5%)', 'Alternative path via gateway exists for critical traffic'],
        nodeRiskDeltas: { 'ip:192.0.2.50': 0.20 },
        edgeWeightDeltas: { 'e2': 1, 'e4': 4 },
    },
    {
        type: 'lateral_movement',
        srcIp: '10.0.0.100', dstIp: '198.51.100.20',
        service: { proto: 'TCP', dst_port: 3389 },
        hypothesis: 'Lateral movement via RDP from internal host 10.0.0.100 to 198.51.100.20',
        triageSummary: 'Automated triage: Suspicious RDP session from 10.0.0.100 to 198.51.100.20. Source host flagged in prior port scan alert.',
        whyReasons: ['RDP session to admin host from non-admin source', '10.0.0.100 was source of earlier port scan', 'Connection timing correlates with scan completion +2 min'],
        actionTitle: 'Block RDP from 10.0.0.100',
        actionType: 'block_ip',
        impactedNodes: 2, reachabilityDrop: 0.12, disruptionRisk: 0.55,
        warnings: ['May block legitimate admin RDP if 10.0.0.100 is dual-use', 'Consider disabling RDP service globally'],
        altPath: { from: 'ip:10.0.0.100', to: 'ip:198.51.100.20', path: ['ip:10.0.0.100','ip:10.0.0.1','ip:198.51.100.20'] },
        explain: ['Blocking RDP from ip:10.0.0.100 removes edge e7', 'Admin host 198.51.100.20 retains SSH access from other sources', 'Alternative admin path exists via gateway 10.0.0.1'],
        nodeRiskDeltas: { 'ip:10.0.0.100': 0.25, 'ip:198.51.100.20': 0.08 },
        edgeWeightDeltas: { 'e5': 5, 'e7': 0 },
    },
    {
        type: 'c2_beacon',
        srcIp: '192.0.2.10', dstIp: '203.0.113.5',
        service: { proto: 'TCP', dst_port: 443 },
        hypothesis: 'Command-and-control beacon from compromised host 192.0.2.10',
        triageSummary: 'Automated triage: Periodic HTTPS beaconing from 192.0.2.10 to external 203.0.113.5 at ~60s intervals. Pattern matches known C2 framework.',
        whyReasons: ['Periodic outbound connections every 58-62 seconds', 'Packet sizes consistent with C2 heartbeat (64-128 bytes)', 'Destination IP in threat intelligence feed (confidence 0.85)'],
        actionTitle: 'Block all traffic to 203.0.113.5',
        actionType: 'block_ip',
        impactedNodes: 1, reachabilityDrop: 0.08, disruptionRisk: 0.15,
        warnings: ['Blocking C2 destination may trigger failover to backup C2 channel'],
        altPath: { from: 'ip:192.0.2.10', to: 'ip:203.0.113.5', path: ['ip:192.0.2.10','ip:10.0.0.1','ip:203.0.113.5'] },
        explain: ['Blocking ip:203.0.113.5 severs C2 channel', 'Minimal network disruption — host is not a hub', 'Recommend additional host forensics on 192.0.2.10'],
        nodeRiskDeltas: { 'ip:203.0.113.5': 0.02 },
        edgeWeightDeltas: { 'e2': 0 },
    },
];

// Per-alert edges that carry alert_ids (different edges for different alert types)
const ALERT_EDGE_INDICES: number[][] = [
    [0, 4],    // alert-0 (bruteforce): e1 (192.0.2.10→198.51.100.20) + e5 (10.0.0.100→192.0.2.10)
    [4, 6],    // alert-1 (port_scan): e5 (10.0.0.100→192.0.2.10) + e7 (10.0.0.100→198.51.100.20) — note e7 is index 6
    [1, 3],    // alert-2 (data_exfil): e2 (192.0.2.10→203.0.113.5) + e4 (192.0.2.50→198.51.100.1)
    [4, 6],    // alert-3 (lateral_mvmt): e5 + e7
    [1],       // alert-4 (c2_beacon): e2 (192.0.2.10→203.0.113.5)
];

// ── In-memory store (survives SPA navigation, resets on full page reload) ──

function initAlertStore(): Alert[] {
    const base = alertSample as unknown as Alert;
    return Array.from({ length: 5 }).map((_, i) => {
        const v = ALERT_VARIATIONS[i];
        return {
            ...base,
            id: `${base.id}-${i}`,
            type: v.type,
            severity: (['low', 'medium', 'high', 'critical'] as const)[i % 4] as any,
            status: (['new', 'triaged', 'investigating', 'resolved', 'false_positive'] as const)[i % 5] as any,
            created_at: new Date(new Date(base.created_at).getTime() + i * 60000).toISOString(),
            entities: {
                ...base.entities,
                primary_src_ip: v.srcIp,
                primary_dst_ip: v.dstIp,
                primary_service: v.service,
            },
        };
    });
}

function initFlowStore(): FlowRecord[] {
    const base = flowSample as unknown as FlowRecord;
    return Array.from({ length: 10 }).map((_, i) => ({
        ...base,
        id: `${base.id}-${i}`,
        src_port: base.src_port + i,
        anomaly_score: parseFloat((Math.random()).toFixed(2)),
        ts_start: new Date(new Date(base.ts_start).getTime() + i * 1000).toISOString(),
    }));
}

const store: {
    alerts: Alert[];
    flows: FlowRecord[];
    lastPlan: any;
    lastDryRun: any;
} = {
    alerts: initAlertStore(),
    flows: initFlowStore(),
    lastPlan: null,
    lastDryRun: null,
};

const mockPcap: PcapFile = {
    id: "11111111-2222-3333-4444-555555555555",
    created_at: new Date().toISOString(),
    filename: "demo.pcap",
    size_bytes: 1024 * 1024 * 5,
    status: "done",
    progress: 100,
    flow_count: 1000,
    alert_count: 5
};

export const mockApi = {
    uploadPcap: async (file: File): Promise<PcapFile> => {
        return { ...mockPcap, filename: file.name, status: 'uploaded', progress: 0 };
    },
    listPcaps: async (): Promise<PcapFile[]> => {
        return [mockPcap];
    },
    getPcapStatus: async (id: string): Promise<PcapFile> => {
        return mockPcap;
    },
    processPcap: async (id: string, body: any): Promise<{accepted: true}> => {
        // Simulate async processing with WS progress events
        const steps = [10, 30, 50, 70, 90, 100];
        steps.forEach((percent, i) => {
            setTimeout(() => {
                if (percent < 100) {
                    wsClient.simulateEvent('pcap.process.progress', { pcap_id: id, percent });
                } else {
                    wsClient.simulateEvent('pcap.process.done', { pcap_id: id, flow_count: 10, alert_count: 3 });
                }
            }, 500 * (i + 1));
        });
        return { accepted: true };
    },

    listFlows: async (params: any): Promise<FlowRecord[]> => {
        return store.flows;
    },
    getFlow: async (id: string): Promise<FlowRecord> => {
        return store.flows.find(f => f.id === id) || store.flows[0];
    },

    listAlerts: async (params: any): Promise<Alert[]> => {
        return store.alerts;
    },
    getAlert: async (id: string): Promise<Alert> => {
        return store.alerts.find(a => a.id === id) || store.alerts[0];
    },
    patchAlert: async (id: string, patch: Partial<Alert>): Promise<Alert> => {
        const idx = store.alerts.findIndex(a => a.id === id);
        if (idx !== -1) {
            store.alerts[idx] = { ...store.alerts[idx], ...patch };
            return store.alerts[idx];
        }
        return { ...store.alerts[0], ...patch };
    },

    getGraph: async (params: any): Promise<GraphResponse> => {
        const raw = graphSample as any;
        // Build per-edge alert_ids: each edge only belongs to alerts that reference it
        const edgeAlertMap = new Map<number, string[]>();
        store.alerts.forEach((a, i) => {
            const edgeIndices = ALERT_EDGE_INDICES[i] ?? [];
            for (const ei of edgeIndices) {
                const existing = edgeAlertMap.get(ei) ?? [];
                existing.push(a.id);
                edgeAlertMap.set(ei, existing);
            }
        });
        // Normalize edges: sample has proto/dst_port, types expect protocols/services
        const normalizeEdges = (edges: any[]): GraphEdge[] =>
            edges.map((e: any, idx: number) => ({
                id: e.id,
                source: e.source,
                target: e.target,
                weight: e.weight,
                protocols: e.protocols ?? (e.proto ? [e.proto] : []),
                services: e.services ?? (e.proto && e.dst_port ? [{ proto: e.proto, port: e.dst_port }] : []),
                alert_ids: edgeAlertMap.get(idx) ?? [],
                activeIntervals: e.activeIntervals ?? [],
            }));

        const mode = params?.mode ?? 'ip';
        if (mode === 'subnet') {
            // Aggregate IP nodes into /24 subnets
            const subnetOf = (id: string) => {
                const m = id.match(/(\d+\.\d+\.\d+)\.\d+/);
                return m ? `subnet:${m[1]}.0/24` : id;
            };
            const subnetMap = new Map<string, GraphNode>();
            for (const n of raw.nodes) {
                const sid = subnetOf(n.id);
                const existing = subnetMap.get(sid);
                subnetMap.set(sid, {
                    id: sid,
                    label: sid.replace('subnet:', ''),
                    type: 'subnet',
                    risk: existing ? Math.max(existing.risk, n.risk) : n.risk,
                });
            }
            // Remap edges
            const edgeKey = (s: string, t: string) => `${s}|${t}`;
            const edgeAgg = new Map<string, any>();
            for (const e of raw.edges) {
                const ss = subnetOf(e.source);
                const st = subnetOf(e.target);
                if (ss === st) continue; // skip intra-subnet
                const key = edgeKey(ss, st);
                // Use per-edge alert IDs from the map
                const eIdx = raw.edges.indexOf(e);
                const realAlertIds = edgeAlertMap.get(eIdx) ?? [];
                const existing = edgeAgg.get(key);
                if (existing) {
                    existing.weight += e.weight;
                    if (e.proto && !existing._protos.has(e.proto)) existing._protos.add(e.proto);
                    if (realAlertIds.length > 0) existing.alert_ids.push(...realAlertIds);
                    if (e.activeIntervals) existing.activeIntervals.push(...e.activeIntervals);
                    if (e.proto && e.dst_port) existing._services.set(`${e.proto}/${e.dst_port}`, { proto: e.proto, port: e.dst_port });
                } else {
                    const protos = new Set<string>();
                    if (e.proto) protos.add(e.proto);
                    const services = new Map<string, { proto: string; port: number }>();
                    if (e.proto && e.dst_port) services.set(`${e.proto}/${e.dst_port}`, { proto: e.proto, port: e.dst_port });
                    edgeAgg.set(key, {
                        id: `se-${edgeAgg.size + 1}`,
                        source: ss,
                        target: st,
                        weight: e.weight,
                        alert_ids: [...realAlertIds],
                        activeIntervals: [...(e.activeIntervals ?? [])],
                        _protos: protos,
                        _services: services,
                    });
                }
            }
            const subnetEdges: GraphEdge[] = Array.from(edgeAgg.values()).map(e => ({
                id: e.id,
                source: e.source,
                target: e.target,
                weight: e.weight,
                protocols: Array.from(e._protos),
                services: Array.from(e._services.values()),
                alert_ids: e.alert_ids,
                activeIntervals: e.activeIntervals,
            }));
            return {
                version: raw.version,
                nodes: Array.from(subnetMap.values()),
                edges: subnetEdges,
                meta: { ...raw.meta, mode: 'subnet' },
            };
        }

        // IP mode: return normalized data
        return {
            version: raw.version,
            nodes: raw.nodes as GraphNode[],
            edges: normalizeEdges(raw.edges),
            meta: raw.meta,
        };
    },

    triage: async (id: string, body: any): Promise<{triage_summary: string}> => {
        const idx = store.alerts.findIndex(a => a.id === id);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        const summary = v.triageSummary;
        // Persist to store so getAlert returns it on next call
        if (idx >= 0) {
            const prev = store.alerts[idx].agent;
            store.alerts[idx] = {
                ...store.alerts[idx],
                agent: {
                    triage_summary: summary,
                    investigation_id: prev?.investigation_id ?? null,
                    recommendation_id: prev?.recommendation_id ?? null,
                },
            };
        }
        return { triage_summary: summary };
    },
    investigate: async (id: string): Promise<Investigation> => {
        const base = investigationSample as any;
        const idx = store.alerts.findIndex(a => a.id === id);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        const invId = `inv-${id}`;
        const result = {
            ...base,
            id: invId,
            alert_id: id,
            hypothesis: v.hypothesis,
            why: v.whyReasons,
            impact: {
                scope: [`dst_ip:${v.dstIp}`, `service:${v.service.proto.toLowerCase()}/${v.service.dst_port}`],
                confidence: 0.65 + idx * 0.05,
            },
            next_steps: [
                `Verify logs on ${v.dstIp} for ${v.type} indicators`,
                `Check threat intelligence for ${v.srcIp}`,
                `Review firewall rules for ${v.service.proto}/${v.service.dst_port}`,
                `Consider implementing rate limiting`,
            ],
            threat_context: {
                techniques: [
                    {
                        technique_id: 'T1595',
                        technique_name: 'Active Scanning',
                        tactic_id: 'TA0043',
                        tactic_name: 'Reconnaissance',
                        confidence: 0.92,
                        description: `Network scanning activity detected from ${v.srcIp}`,
                        intel_refs: ['https://attack.mitre.org/techniques/T1595/'],
                    },
                    {
                        technique_id: 'T1046',
                        technique_name: 'Network Service Discovery',
                        tactic_id: 'TA0007',
                        tactic_name: 'Discovery',
                        confidence: 0.78,
                        description: 'Service enumeration behavior observed',
                        intel_refs: ['https://attack.mitre.org/techniques/T1046/'],
                    },
                ],
                tactics: ['Reconnaissance', 'Discovery'],
                enrichment_confidence: 0.85,
                enrichment_source: 'local_mitre_v1',
            },
        } as unknown as Investigation;
        // Persist to store
        if (idx >= 0) {
            const prev = store.alerts[idx].agent;
            store.alerts[idx] = {
                ...store.alerts[idx],
                agent: {
                    triage_summary: prev?.triage_summary ?? null,
                    investigation_id: invId,
                    recommendation_id: prev?.recommendation_id ?? null,
                },
            };
        }
        return result;
    },
    recommend: async (id: string): Promise<Recommendation> => {
        const base = recommendationSample as any;
        const idx = store.alerts.findIndex(a => a.id === id);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        const recId = `rec-${id}`;
        const result = {
            ...base,
            id: recId,
            alert_id: id,
            actions: [
                {
                    ...base.actions[0],
                    title: v.actionTitle,
                    steps: [`Apply ${v.actionType} on ${v.srcIp}`, 'Verify action is active'],
                    risk: `May affect legitimate traffic from ${v.srcIp}`,
                },
                ...(base.actions.slice(1) || []),
            ],
            threat_context: {
                techniques: [
                    {
                        technique_id: 'T1595',
                        technique_name: 'Active Scanning',
                        tactic_id: 'TA0043',
                        tactic_name: 'Reconnaissance',
                        confidence: 0.92,
                        description: `Recommended mitigation for scanning from ${v.srcIp}`,
                        intel_refs: ['https://attack.mitre.org/techniques/T1595/'],
                    },
                ],
                tactics: ['Reconnaissance'],
                enrichment_confidence: 0.88,
                enrichment_source: 'local_mitre_v1',
            },
        } as unknown as Recommendation;
        // Persist to store
        if (idx >= 0) {
            const prev = store.alerts[idx].agent;
            store.alerts[idx] = {
                ...store.alerts[idx],
                agent: {
                    triage_summary: prev?.triage_summary ?? null,
                    investigation_id: prev?.investigation_id ?? null,
                    recommendation_id: recId,
                },
            };
        }
        return result;
    },

    getInvestigation: async (id: string): Promise<Investigation> => {
        // Re-use the investigate mock logic keyed by alert id embedded in inv id
        const alertId = id.startsWith('inv-') ? id.slice(4) : id;
        const base = investigationSample as any;
        const idx = store.alerts.findIndex(a => a.id === alertId);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        return {
            ...base,
            id,
            alert_id: alertId,
            hypothesis: v.hypothesis,
            why: v.whyReasons,
            impact: {
                scope: [`dst_ip:${v.dstIp}`, `service:${v.service.proto.toLowerCase()}/${v.service.dst_port}`],
                confidence: 0.65 + (idx >= 0 ? idx : 0) * 0.05,
            },
            next_steps: [
                `Verify logs on ${v.dstIp} for ${v.type} indicators`,
                `Check threat intelligence for ${v.srcIp}`,
                `Review firewall rules for ${v.service.proto}/${v.service.dst_port}`,
                `Consider implementing rate limiting`,
            ],
        } as unknown as Investigation;
    },
    getRecommendation: async (id: string): Promise<Recommendation> => {
        const alertId = id.startsWith('rec-') ? id.slice(4) : id;
        const base = recommendationSample as any;
        const idx = store.alerts.findIndex(a => a.id === alertId);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        return {
            ...base,
            id,
            alert_id: alertId,
            actions: [
                {
                    ...base.actions[0],
                    title: v.actionTitle,
                    steps: [`Apply ${v.actionType} on ${v.srcIp}`, 'Verify action is active'],
                    risk: `May affect legitimate traffic from ${v.srcIp}`,
                },
                ...(base.actions.slice(1) || []),
            ],
        } as unknown as Recommendation;
    },

    getEvidenceChain: async (id: string): Promise<EvidenceChain> => {
        const base = evidenceChainSample as any;
        const idx = store.alerts.findIndex(a => a.id === id);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        return {
            ...base,
            id: `ec-${id}`,
            alert_id: id,
            nodes: base.nodes.map((n: any) => ({
                ...n,
                label: n.type === 'alert' ? `${v.type} alert` :
                       n.type === 'hypothesis' ? v.hypothesis.substring(0, 40) + '...' :
                       n.label,
            })),
        } as unknown as EvidenceChain;
    },

    compilePlan: async (alertId: string, body?: CompilePlanRequest): Promise<CompilePlanResponse> => {
        const idx = store.alerts.findIndex(a => a.id === alertId);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        const alert = store.alerts[idx >= 0 ? idx : 0];
        const planId = `plan-${alertId}-${Date.now()}`;
        const recId = body?.recommendation_id || `rec-${alertId}`;

        const rollbackMap: Record<string, { action_type: string; params: Record<string, any> }> = {
            block_ip: { action_type: 'unblock_ip', params: { ip: v.srcIp } },
            isolate_host: { action_type: 'restore_host', params: { host: v.srcIp } },
            segment_subnet: { action_type: 'unsegment_subnet', params: { subnet: v.srcIp } },
            rate_limit_service: { action_type: 'remove_rate_limit', params: { proto: v.service.proto, port: v.service.dst_port } },
        };

        const compiledAction: CompiledAction = {
            action_type: v.actionType as CompiledAction['action_type'],
            target: { type: 'ip', value: v.srcIp },
            params: { duration_minutes: 60, ip: v.srcIp },
            rollback: rollbackMap[v.actionType] || null,
            confidence: 0.80 + (idx >= 0 ? idx : 0) * 0.03,
            derived_from_evidence: [
                `alert:${alert.id}`,
                `flow:${alertId}-flow-0`,
                `feat:syn_count`,
            ],
            reasoning_summary: `Compiled from recommendation "${v.actionTitle}" (priority: high) for ${alert.severity} ${v.type} alert. Action: ${v.actionType}. Confidence: ${(0.80 + (idx >= 0 ? idx : 0) * 0.03).toFixed(2)}.`,
        };

        const plan: ActionPlan = {
            version: '1.1',
            id: planId,
            created_at: new Date().toISOString(),
            alert_id: alertId,
            source: 'agent',
            actions: [compiledAction],
            notes: `Auto-compiled from recommendation ${recId}. 1 actions compiled, 1 skipped.`,
        };

        store.lastPlan = plan as any;

        return {
            plan,
            compilation: {
                recommendation_id: recId,
                rules_matched: 1,
                actions_skipped: 1,
                compiler_version: '1.0',
            },
        };
    },

    createPlan: async (body: any): Promise<ActionPlan> => {
        const base = actionPlanSample as any;
        const alertId = body?.alert_id || store.alerts[0].id;
        const planId = `plan-${alertId}-${Date.now()}`;
        // Store the plan so dry-run can reference it
        const plan = {
            ...base,
            id: planId,
            alert_id: alertId,
            created_at: new Date().toISOString(),
            actions: body?.actions || base.actions,
        };
        // Save to store for later dry-run reference
        store.lastPlan = plan as any;
        return plan as unknown as ActionPlan;
    },
    dryRunPlan: async (planId: string, body?: any): Promise<DryRunResult> => {
        const base = dryRunSample as any;
        // Find which alert this plan belongs to
        const alertId = store.lastPlan?.alert_id || store.alerts[0].id;
        const idx = store.alerts.findIndex(a => a.id === alertId);
        const v = ALERT_VARIATIONS[idx >= 0 ? idx : 0];
        const result: any = {
            ...base,
            id: `dr-${planId}-${Date.now()}`,
            alert_id: alertId,
            plan_id: planId,
            created_at: new Date().toISOString(),
            impact: {
                ...base.impact,
                impacted_nodes_count: v.impactedNodes,
                reachability_drop: v.reachabilityDrop,
                service_disruption_risk: v.disruptionRisk,
                warnings: v.warnings,
                node_risk_deltas: v.nodeRiskDeltas,
                edge_weight_deltas: v.edgeWeightDeltas,
            },
            alternative_paths: [v.altPath],
            explain: v.explain,
        };
        // Store result for topology page retrieval
        store.lastDryRun = result;

        // Simulate lightweight WS event (mirrors real backend twin.dryrun.created event)
        // Payload is intentionally minimal: { dry_run_id, alert_id, risk }
        // The DryRunPanel WS handler will fetch the full result by dry_run_id
        setTimeout(() => {
            wsClient.simulateEvent('twin.dryrun.created', {
                dry_run_id: result.id,
                alert_id: alertId,
                risk: v.disruptionRisk,
            });
        }, 800);

        return result as DryRunResult;
    },
    listDryRuns: async (params: any): Promise<DryRunResult[]> => {
        if (store.lastDryRun) return [store.lastDryRun as DryRunResult];
        return [dryRunSample as unknown as DryRunResult];
    },
    getDryRun: async (id: string): Promise<DryRunResult> => {
        if (store.lastDryRun && (store.lastDryRun as any).id === id) {
            return store.lastDryRun as DryRunResult;
        }
        return { ...(dryRunSample as any), id } as unknown as DryRunResult;
    },

    createScenario: async (body: any): Promise<Scenario> => {
        return scenarioSample as unknown as Scenario;
    },
    listScenarios: async (params: any): Promise<Scenario[]> => {
        const scenario2 = {
            ...scenarioSample,
            id: 'c9d0e1f2-a3b4-5678-2345-901234567890',
            name: 'scan_demo',
            description: 'Regression scenario for port scan detection.',
            tags: ['regression', 'demo', 'scan', 'network']
        };
        return [
            scenarioSample as unknown as Scenario,
            scenario2 as unknown as Scenario
        ];
    },
    runScenario: async (id: string): Promise<ScenarioRunResult> => {
        // Return matching result or default
        const result = {
            ...scenarioRunResultSample,
            id: `run-${Date.now()}`,
            scenario_id: id,
            created_at: new Date().toISOString()
        };
        
        // Simulate WS event after 1.5s
        setTimeout(() => {
            wsClient.simulateEvent('scenario.run.done', {
                scenario_id: id,
                run_id: result.id,
                status: 'pass'
            });
        }, 1500);

        // API immediately returns the result (or we can simulate a delay if the API blocks, but let's just use a promise with delay)
        return new Promise(resolve => {
            setTimeout(() => {
                resolve(result as unknown as ScenarioRunResult);
            }, 1000);
        });
    },
    getLatestScenarioRun: async (scenarioId: string): Promise<ScenarioRunResult> => {
        return {
            ...scenarioRunResultSample,
            id: `run-latest-${scenarioId}`,
            scenario_id: scenarioId,
            created_at: new Date().toISOString(),
        } as unknown as ScenarioRunResult;
    },
};
