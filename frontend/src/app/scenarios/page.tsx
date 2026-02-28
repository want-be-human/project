'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Scenario } from '@/lib/api/types';
import ScenarioList from '@/components/scenarios/ScenarioList';
import ScenarioRunPanel from '@/components/scenarios/ScenarioRunPanel';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | undefined>();

  useEffect(() => {
    const fetchScenarios = async () => {
      try {
        setLoading(true);
        const data = await api.listScenarios({});
        setScenarios(data);
        if (data.length > 0) {
          setSelectedScenario(data[0]);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load scenarios');
      } finally {
        setLoading(false);
      }
    };
    fetchScenarios();
  }, []);

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Security Scenarios</h1>
          <p className="text-gray-500 text-sm mt-1">Regression testing and dry-run validation pipelines.</p>
        </div>
      </div>

      {error ? (
        <div key="error" className="p-4 bg-red-50 text-red-700 rounded flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div key="loading" className="flex-1 flex items-center justify-center text-gray-400">
          <RefreshCw className="w-6 h-6 animate-spin mr-2" />
          <span>Loading scenarios...</span>
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 h-full min-h-0">
          {/* Left: List */}
          <div className="lg:col-span-1 flex flex-col min-h-0">
            <ScenarioList 
              scenarios={scenarios} 
              onSelect={setSelectedScenario}
              selectedId={selectedScenario?.id}
              runningId={runningScenarioId}
            />
          </div>
          
          {/* Right: Panel */}
          <div className="lg:col-span-2 flex flex-col min-h-0">
            <ScenarioRunPanel 
              scenario={selectedScenario}
              onRunStatusChange={setRunningScenarioId}
            />
          </div>
        </div>
      )}
    </div>
  );
}
