'use client';

import { Scenario, ScenarioRunResult } from '@/lib/api/types';
import { api } from '@/lib/api';
import { wsClient } from '@/lib/ws';
import { useState, useEffect } from 'react';
import { Play, CheckCircle2, XCircle, Clock, Activity, ShieldAlert, BarChart3, RefreshCw } from 'lucide-react';

interface Props {
  scenario: Scenario | null;
  onRunStatusChange: (scenarioId: string | undefined) => void;
}

export default function ScenarioRunPanel({ scenario, onRunStatusChange }: Props) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ScenarioRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Clear result when selecting a new scenario
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [scenario?.id]);

  useEffect(() => {
    const unsub = wsClient.onEvent('scenario.run.done', (payload) => {
      // In a real app we might fetch the result here or just use what we get back from the POST request. 
      // Since it's mockup, the POST request already returns the result. We just use this for potential toast notification
      // console.log('WS: scenario.run.done', payload);
    });
    return unsub;
  }, []);

  const handleRun = async () => {
    if (!scenario) return;
    setRunning(true);
    setError(null);
    setResult(null);
    onRunStatusChange(scenario.id);

    try {
      const res = await api.runScenario(scenario.id);
      setResult(res);
    } catch (e: any) {
      setError(e.message || 'Error running scenario');
    } finally {
      setRunning(false);
      onRunStatusChange(undefined);
    }
  };

  if (!scenario) {
    return (
      <div className="bg-white rounded-lg shadow border border-gray-200 h-full flex items-center justify-center text-gray-400 p-8 text-center flex-col">
        <Activity className="w-12 h-12 mb-4 text-gray-300" />
        <p>Select a scenario from the list to view details and execute regression testing.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-start bg-gray-50 rounded-t-lg">
        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-1">{scenario.name}</h2>
          <p className="text-sm text-gray-500">{scenario.description || 'No description provided.'}</p>
        </div>
        {running ? (
          <button
            key="running"
            disabled
            className="flex items-center gap-2 px-4 py-2 rounded-md font-medium bg-gray-300 text-gray-500 cursor-not-allowed"
          >
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Running...</span>
          </button>
        ) : (
          <button
            key="idle"
            onClick={handleRun}
            className="flex items-center gap-2 px-4 py-2 rounded-md font-medium bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors"
          >
            <Play className="w-4 h-4" />
            <span>Run Scenario</span>
          </button>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6 bg-gray-50/50">
        
        {/* Pre-run state */}
        {!result && !running && !error && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <p>Ready to run regression test.</p>
            <p className="text-sm mt-2">Click "Run Scenario" to execute.</p>
          </div>
        )}

        {/* Loading state */}
        {running && (
          <div className="flex flex-col items-center justify-center h-40">
            <p className="text-indigo-600 font-medium animate-pulse mb-2">Executing scenario pipeline...</p>
            <p className="text-sm text-gray-500">Processing PCAP, evaluating detections, checking dry-run metrics.</p>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md">
            <p className="font-bold flex items-center gap-2"><XCircle className="w-5 h-5"/> <span>Error</span></p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Result state */}
        {result && !running && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
            
            {/* Status Banner */}
            <div className={`p-4 rounded-lg flex items-center gap-3 border ${
              result.status === 'pass' 
                ? 'bg-green-50 border-green-200 text-green-800' 
                : 'bg-red-50 border-red-200 text-red-800'
            }`}>
              {result.status === 'pass' ? <CheckCircle2 className="w-8 h-8" /> : <XCircle className="w-8 h-8" />}
              <div>
                <h3 className="font-bold text-lg capitalize">Scenario {result.status}ed</h3>
                <p className="opacity-80 text-sm">Completed at {new Date((result as any).created_at || Date.now()).toLocaleString()}</p>
              </div>
            </div>

            {/* Metrics */}
            {result.metrics && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" /> Metrics Dashboard
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <MetricCard label="Total Alerts" value={result.metrics.alert_count} />
                  <MetricCard label="High Severity" value={result.metrics.high_severity_count} color="text-red-600" />
                  <MetricCard label="Avg Risk" value={result.metrics.avg_dry_run_risk?.toFixed(2)} />
                  <MetricCard label="Processing Time" value={`${result.metrics.processing_time_ms} ms`} />
                </div>
              </div>
            )}

            {/* Checks Checklist */}
            {result.checks && result.checks.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4" /> Policy Checks
                </h3>
                <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                  <div className="grid grid-cols-12 bg-gray-50 border-b border-gray-200 p-3 text-xs font-semibold text-gray-500 uppercase">
                    <div className="col-span-1 text-center">Status</div>
                    <div className="col-span-4">Check Name</div>
                    <div className="col-span-7">Details</div>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {result.checks.map((check, idx) => (
                      <div key={idx} className="grid grid-cols-12 p-3 text-sm items-center">
                        <div className="col-span-1 flex justify-center">
                          {check.pass 
                            ? <CheckCircle2 className="w-5 h-5 text-green-500" /> 
                            : <XCircle className="w-5 h-5 text-red-500" />
                          }
                        </div>
                        <div className="col-span-4 font-medium text-gray-700">
                          {check.name}
                        </div>
                        <div className="col-span-7 text-gray-600 font-mono text-xs overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(check.details, null, 2)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, color = "text-gray-900" }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm flex flex-col justify-center">
      <div className="text-xs text-gray-500 font-medium mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value ?? '-'}</div>
    </div>
  );
}