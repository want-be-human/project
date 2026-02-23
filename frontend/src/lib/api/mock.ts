import { 
  PcapFile, FlowRecord, Alert, GraphResponse, Investigation, 
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
        return graphSample as unknown as GraphResponse;
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
