import { 
  PcapFile, FlowRecord, Alert, GraphResponse, GraphNode, GraphEdge, Investigation, 
  Recommendation, ActionPlan, DryRunResult, Scenario, ScenarioRunResult,
  EvidenceChain
} from './types';

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

// ── In-memory store (survives SPA navigation, resets on full page reload) ──

function initAlertStore(): Alert[] {
    const base = alertSample as unknown as Alert;
    return Array.from({ length: 5 }).map((_, i) => ({
        ...base,
        id: `${base.id}-${i}`,
        severity: (['low', 'medium', 'high', 'critical'] as const)[i % 4] as any,
        status: (['new', 'triaged', 'investigating', 'resolved', 'false_positive'] as const)[i % 5] as any,
        created_at: new Date(new Date(base.created_at).getTime() + i * 60000).toISOString(),
    }));
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

const store = {
    alerts: initAlertStore(),
    flows: initFlowStore(),
};

const mockPcap: PcapFile = {
    id: "11111111-2222-3333-4444-555555555555",
    created_at: new Date().toISOString(),
    filename: "demo.pcap",
    size: 1024 * 1024 * 5,
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
        await new Promise(resolve => setTimeout(resolve, 1500)); // Simulate delay
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
        // Normalize edges: sample has proto/dst_port, types expect protocols/services
        const normalizeEdges = (edges: any[]): GraphEdge[] =>
            edges.map((e: any) => ({
                id: e.id,
                source: e.source,
                target: e.target,
                weight: e.weight,
                protocols: e.protocols ?? (e.proto ? [e.proto] : []),
                services: e.services ?? (e.proto && e.dst_port ? [{ proto: e.proto, port: e.dst_port }] : []),
                alert_ids: e.alert_ids ?? [],
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
                const existing = edgeAgg.get(key);
                if (existing) {
                    existing.weight += e.weight;
                    if (e.proto && !existing._protos.has(e.proto)) existing._protos.add(e.proto);
                    if (e.alert_ids) existing.alert_ids.push(...e.alert_ids);
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
                        alert_ids: [...(e.alert_ids ?? [])],
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
        return { triage_summary: "Automated triage: This looks like a brute force attack." };
    },
    investigate: async (id: string): Promise<Investigation> => {
        return investigationSample as unknown as Investigation;
    },
    recommend: async (id: string): Promise<Recommendation> => {
        return recommendationSample as unknown as Recommendation;
    },

    getEvidenceChain: async (id: string): Promise<EvidenceChain> => {
        return evidenceChainSample as unknown as EvidenceChain;
    },

    createPlan: async (body: any): Promise<ActionPlan> => {
        return actionPlanSample as unknown as ActionPlan;
    },
    dryRunPlan: async (planId: string, body?: any): Promise<DryRunResult> => {
        return dryRunSample as unknown as DryRunResult;
    },
    listDryRuns: async (params: any): Promise<DryRunResult[]> => {
        return [dryRunSample as unknown as DryRunResult];
    },

    createScenario: async (body: any): Promise<Scenario> => {
        return scenarioSample as unknown as Scenario;
    },
    listScenarios: async (params: any): Promise<Scenario[]> => {
        return [scenarioSample as unknown as Scenario];
    },
    runScenario: async (id: string): Promise<ScenarioRunResult> => {
        return scenarioRunResultSample as unknown as ScenarioRunResult;
    }
};
