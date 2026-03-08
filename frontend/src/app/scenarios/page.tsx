'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { Scenario, PcapFile } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import ScenarioList from '@/components/scenarios/ScenarioList';
import ScenarioRunPanel from '@/components/scenarios/ScenarioRunPanel';
import { AlertCircle, RefreshCw, Plus, X } from 'lucide-react';

export default function ScenariosPage() {
  const t = useTranslations('scenarios');
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | undefined>();

  // Create dialog state
  const [showCreate, setShowCreate] = useState(false);
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [creating, setCreating] = useState(false);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formPcapId, setFormPcapId] = useState('');
  const [formMinAlerts, setFormMinAlerts] = useState(1);
  const [formDryRun, setFormDryRun] = useState(true);
  const [formTags, setFormTags] = useState('regression,demo');

  const fetchScenarios = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listScenarios({});
      setScenarios(data);
      if (data.length > 0 && !selectedScenario) {
        setSelectedScenario(data[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load scenarios');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchScenarios(); }, [fetchScenarios]);

  const openCreate = async () => {
    setShowCreate(true);
    try {
      const list = await api.listPcaps({ limit: 100 });
      setPcaps(list.filter(p => p.status === 'done'));
      if (list.length > 0 && !formPcapId) setFormPcapId(list.find(p => p.status === 'done')?.id || '');
    } catch { /* ignore */ }
  };

  const handleCreate = async () => {
    if (!formName || !formPcapId) return;
    setCreating(true);
    try {
      await api.createScenario({
        name: formName,
        description: formDesc,
        pcap_ref: { pcap_id: formPcapId },
        expectations: {
          min_alerts: formMinAlerts,
          must_have: [{ type: 'anomaly', severity_at_least: 'medium' }],
          evidence_chain_contains: [],
          dry_run_required: formDryRun,
        },
        tags: formTags.split(',').map(s => s.trim()).filter(Boolean),
      });
      setShowCreate(false);
      setFormName(''); setFormDesc('');
      await fetchScenarios();
    } catch (e: any) {
      alert(e.message || 'Failed to create scenario');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
          <p className="text-gray-500 text-sm mt-1">{t('description')}</p>
        </div>
        <button
          onClick={openCreate}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md text-sm font-medium flex items-center gap-2 shadow-sm"
        >
          <Plus className="w-4 h-4" /> {t('createBtn')}
        </button>
      </div>

      {/* Create Scenario Dialog */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-gray-900">{t('createTitle')}</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('nameLabel')}</label>
                <input type="text" value={formName} onChange={e => setFormName(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="e.g. bruteforce_demo" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('descLabel')}</label>
                <input type="text" value={formDesc} onChange={e => setFormDesc(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('pcapLabel')}</label>
                <select value={formPcapId} onChange={e => setFormPcapId(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm">
                  {pcaps.length === 0 && <option value="">{t('noPcaps')}</option>}
                  {pcaps.map(p => (
                    <option key={p.id} value={p.id}>{p.filename} ({p.flow_count} flows, {p.alert_count} alerts)</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('minAlerts')}</label>
                  <input type="number" min={0} value={formMinAlerts} onChange={e => setFormMinAlerts(Number(e.target.value))}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
                </div>
                <div className="flex items-end pb-2">
                  <label className="flex items-center gap-2 text-sm text-gray-700">
                    <input type="checkbox" checked={formDryRun} onChange={e => setFormDryRun(e.target.checked)} className="rounded" />
                    {t('dryRunRequired')}
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('tagsLabel')}</label>
                <input type="text" value={formTags} onChange={e => setFormTags(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="regression,demo" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">{t('cancel')}</button>
              <button onClick={handleCreate} disabled={creating || !formName || !formPcapId}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md text-sm font-medium disabled:opacity-50">
                {creating ? t('creatingBtn') : t('createBtn')}
              </button>
            </div>
          </div>
        </div>
      )}

      {error ? (
        <div key="error" className="p-4 bg-red-50 text-red-700 rounded flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <div key="loading" className="flex-1 flex items-center justify-center text-gray-400">
          <RefreshCw className="w-6 h-6 animate-spin mr-2" />
          <span>{t('loading')}</span>
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
