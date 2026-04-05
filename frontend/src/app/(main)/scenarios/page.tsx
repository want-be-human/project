'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { Scenario, PcapFile } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import ScenarioList from '@/components/scenarios/ScenarioList';
import ScenarioRunPanel from '@/components/scenarios/ScenarioRunPanel';
import { AlertCircle, RefreshCw, Plus, X, AlertTriangle } from 'lucide-react';

export default function ScenariosPage() {
  const t = useTranslations('scenarios');
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | undefined>();

  // 视图模式：active | archived
  const [viewMode, setViewMode] = useState<'active' | 'archived'>('active');

  // 删除确认
  const [deleteTarget, setDeleteTarget] = useState<Scenario | null>(null);
  const [deleting, setDeleting] = useState(false);

  // 创建对话框状态 - 基础信息
  const [showCreate, setShowCreate] = useState(false);
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [creating, setCreating] = useState(false);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formPcapId, setFormPcapId] = useState('');
  const [formTags, setFormTags] = useState('');

  // 基础结果类
  const [formMinAlerts, setFormMinAlerts] = useState(0);
  const [formMaxAlerts, setFormMaxAlerts] = useState<number | undefined>();
  const [formExactAlerts, setFormExactAlerts] = useState<number | undefined>();
  const [formMinHighSeverity, setFormMinHighSeverity] = useState(0);
  const [formDryRun, setFormDryRun] = useState(false);

  // 模式匹配类
  const [formMustHave, setFormMustHave] = useState<Array<{type: string; severity: string}>>([]);
  const [formForbiddenTypes, setFormForbiddenTypes] = useState<string[]>([]);

  // 证据类
  const [formEvidenceChain, setFormEvidenceChain] = useState<string[]>([]);
  const [formRequiredEntities, setFormRequiredEntities] = useState<string[]>([]);
  const [formRequiredFeatures, setFormRequiredFeatures] = useState<string[]>([]);

  // 性能类
  const [formMaxPipelineLatency, setFormMaxPipelineLatency] = useState<number | undefined>();
  const [formRequiredStages, setFormRequiredStages] = useState<string[]>([]);
  const [formNoFailedStages, setFormNoFailedStages] = useState(false);

  const fetchScenarios = useCallback(async (mode: 'active' | 'archived' = viewMode) => {
    try {
      setLoading(true);
      const data = await api.listScenarios({ include_archived: mode === 'archived' });
      setScenarios(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load scenarios');
    } finally {
      setLoading(false);
    }
  }, [viewMode]);

  useEffect(() => { fetchScenarios(viewMode); }, [viewMode]);

  const handleViewModeChange = (mode: 'active' | 'archived') => {
    setViewMode(mode);
    setSelectedScenario(null);
  };

  const handleSelect = (scenario: Scenario) => {
    setSelectedScenario(scenario);
  };

  const handleArchive = async (scenario: Scenario) => {
    try {
      await api.archiveScenario(scenario.id);
      if (selectedScenario?.id === scenario.id) setSelectedScenario(null);
      await fetchScenarios(viewMode);
    } catch (e: any) {
      alert(e.message || 'Failed to archive scenario');
    }
  };

  const handleUnarchive = async (scenario: Scenario) => {
    try {
      await api.unarchiveScenario(scenario.id);
      if (selectedScenario?.id === scenario.id) setSelectedScenario(null);
      await fetchScenarios(viewMode);
    } catch (e: any) {
      alert(e.message || 'Failed to unarchive scenario');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteScenario(deleteTarget.id);
      if (selectedScenario?.id === deleteTarget.id) setSelectedScenario(null);
      setDeleteTarget(null);
      await fetchScenarios(viewMode);
    } catch (e: any) {
      alert(e.message || 'Failed to delete scenario');
    } finally {
      setDeleting(false);
    }
  };

  const resetForm = () => {
    setFormName(''); setFormDesc(''); setFormPcapId(''); setFormTags('');
    setFormMinAlerts(0); setFormMaxAlerts(undefined); setFormExactAlerts(undefined);
    setFormMinHighSeverity(0); setFormDryRun(false);
    setFormMustHave([]); setFormForbiddenTypes([]);
    setFormEvidenceChain([]); setFormRequiredEntities([]); setFormRequiredFeatures([]);
    setFormMaxPipelineLatency(undefined); setFormRequiredStages([]); setFormNoFailedStages(false);
  };

  const openCreate = async () => {
    setShowCreate(true);
    try {
      const list = await api.listPcaps({ limit: 100 });
      const done = list.filter(p => p.status === 'done');
      setPcaps(done);
      if (done.length > 0 && !formPcapId) setFormPcapId(done[0].id);
    } catch { /* 忽略 */ }
  };

  const handleCreate = async () => {
    if (!formName || !formPcapId) return;

    // 前端校验：exact_alerts 与 min/max 冲突
    if (formExactAlerts !== undefined && (formMinAlerts > 0 || formMaxAlerts !== undefined)) {
      alert(t('exactAlertsConflict'));
      return;
    }

    setCreating(true);
    try {
      await api.createScenario({
        name: formName,
        description: formDesc,
        pcap_ref: { pcap_id: formPcapId },
        expectations: {
          // 基础结果类
          min_alerts: formMinAlerts,
          ...(formMaxAlerts !== undefined && { max_alerts: formMaxAlerts }),
          ...(formExactAlerts !== undefined && { exact_alerts: formExactAlerts }),
          min_high_severity_count: formMinHighSeverity,
          dry_run_required: formDryRun,
          // 模式匹配类
          must_have: formMustHave.filter(m => m.type.trim()).map(m => ({
            type: m.type.trim(),
            severity_at_least: m.severity,
          })),
          forbidden_types: formForbiddenTypes.filter(v => v.trim()),
          // 证据类
          evidence_chain_contains: formEvidenceChain.filter(e => e.trim()),
          required_entities: formRequiredEntities.filter(e => e.trim()),
          required_feature_names: formRequiredFeatures.filter(f => f.trim()),
          // 性能类
          ...(formMaxPipelineLatency !== undefined && { max_pipeline_latency_ms: formMaxPipelineLatency }),
          required_pipeline_stages: formRequiredStages.filter(s => s.trim()),
          no_failed_stages: formNoFailedStages,
        },
        tags: formTags.split(',').map(s => s.trim()).filter(Boolean),
      });
      setShowCreate(false);
      resetForm();
      await fetchScenarios('active');
      if (viewMode !== 'active') setViewMode('active');
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

      {/* 创建对话框 - 可配置 benchmark 创建器 */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            {/* 标题栏 */}
            <div className="flex justify-between items-center px-6 py-4 border-b border-gray-200 shrink-0">
              <h2 className="text-lg font-bold text-gray-900">{t('createTitle')}</h2>
              <button onClick={() => { setShowCreate(false); resetForm(); }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>

            {/* 可滚动表单区 */}
            <div className="overflow-y-auto flex-1 px-6 py-4 space-y-5">

              {/* 基础信息 */}
              <FormSection title={t('sectionBasic')}>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('nameLabel')}</label>
                  <input type="text" value={formName} onChange={e => setFormName(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="e.g. bruteforce_regression" />
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
              </FormSection>

              {/* 告警数量规则 */}
              <FormSection title={t('sectionAlertCount')}>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('minAlerts')}</label>
                    <input type="number" min={0} value={formMinAlerts}
                      onChange={e => setFormMinAlerts(Number(e.target.value))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('maxAlerts')}</label>
                    <input type="number" min={0} value={formMaxAlerts ?? ''}
                      onChange={e => setFormMaxAlerts(e.target.value === '' ? undefined : Number(e.target.value))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" placeholder={t('optional')} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('exactAlerts')}</label>
                    <input type="number" min={0} value={formExactAlerts ?? ''}
                      onChange={e => setFormExactAlerts(e.target.value === '' ? undefined : Number(e.target.value))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" placeholder={t('optional')} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('minHighSeverity')}</label>
                    <input type="number" min={0} value={formMinHighSeverity}
                      onChange={e => setFormMinHighSeverity(Number(e.target.value))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" />
                  </div>
                  <div className="flex items-end pb-1.5">
                    <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                      <input type="checkbox" checked={formDryRun} onChange={e => setFormDryRun(e.target.checked)} className="rounded" />
                      {t('dryRunRequired')}
                    </label>
                  </div>
                </div>
                {formExactAlerts !== undefined && (formMinAlerts > 0 || formMaxAlerts !== undefined) && (
                  <p className="text-xs text-red-600 mt-1">{t('exactAlertsConflict')}</p>
                )}
              </FormSection>

              {/* 模式匹配规则 */}
              <FormSection title={t('sectionPatternMatch')}>
                {/* must_have 动态列表 */}
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <label className="text-xs font-medium text-gray-600">{t('mustHaveTypes')}</label>
                    <button onClick={() => setFormMustHave([...formMustHave, { type: '', severity: 'medium' }])}
                      className="text-xs text-indigo-600 hover:text-indigo-800">+ {t('addItem')}</button>
                  </div>
                  {formMustHave.map((item, idx) => (
                    <div key={idx} className="flex gap-2 mb-1.5">
                      <input value={item.type} placeholder={t('alertTypePlaceholder')}
                        onChange={e => { const u = [...formMustHave]; u[idx] = { ...u[idx], type: e.target.value }; setFormMustHave(u); }}
                        className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm" />
                      <select value={item.severity}
                        onChange={e => { const u = [...formMustHave]; u[idx] = { ...u[idx], severity: e.target.value }; setFormMustHave(u); }}
                        className="border border-gray-300 rounded px-2 py-1 text-sm">
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                        <option value="critical">critical</option>
                      </select>
                      <button onClick={() => setFormMustHave(formMustHave.filter((_, i) => i !== idx))}
                        className="text-red-500 hover:text-red-700 text-xs px-1">✕</button>
                    </div>
                  ))}
                </div>
                {/* 禁止类型列表 */}
                <StringArrayInput label={t('forbiddenTypes')} items={formForbiddenTypes}
                  onChange={setFormForbiddenTypes} placeholder={t('alertTypePlaceholder')} addLabel={t('addItem')} />
              </FormSection>

              {/* 证据与实体规则 */}
              <FormSection title={t('sectionEvidence')}>
                <StringArrayInput label={t('evidenceChainNodes')} items={formEvidenceChain}
                  onChange={setFormEvidenceChain} placeholder="node_id" addLabel={t('addItem')} />
                <StringArrayInput label={t('requiredEntities')} items={formRequiredEntities}
                  onChange={setFormRequiredEntities} placeholder="192.168.1.1" addLabel={t('addItem')} />
                <StringArrayInput label={t('requiredFeatures')} items={formRequiredFeatures}
                  onChange={setFormRequiredFeatures} placeholder="flow_duration" addLabel={t('addItem')} />
              </FormSection>

              {/* 性能与稳定性规则 */}
              <FormSection title={t('sectionPerformance')}>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('maxPipelineLatency')}</label>
                    <input type="number" min={0} value={formMaxPipelineLatency ?? ''}
                      onChange={e => setFormMaxPipelineLatency(e.target.value === '' ? undefined : Number(e.target.value))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" placeholder={t('optional')} />
                  </div>
                  <div className="flex items-end pb-1.5">
                    <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                      <input type="checkbox" checked={formNoFailedStages} onChange={e => setFormNoFailedStages(e.target.checked)} className="rounded" />
                      {t('noFailedStages')}
                    </label>
                  </div>
                </div>
                <StringArrayInput label={t('requiredStages')} items={formRequiredStages}
                  onChange={setFormRequiredStages} placeholder="parse_pcap" addLabel={t('addItem')} />
              </FormSection>

              {/* 标签 */}
              <FormSection title={t('tagsLabel')}>
                <input type="text" value={formTags} onChange={e => setFormTags(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="regression,smoke" />
              </FormSection>
            </div>

            {/* 底部按钮 */}
            <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 shrink-0">
              <button onClick={() => { setShowCreate(false); resetForm(); }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">{t('cancel')}</button>
              <button onClick={handleCreate} disabled={creating || !formName || !formPcapId}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md text-sm font-medium disabled:opacity-50">
                {creating ? t('creatingBtn') : t('createBtn')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 永久删除确认对话框 */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={() => !deleting && setDeleteTarget(null)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              <h2 className="text-lg font-bold text-gray-900">{t('deleteTitle')}</h2>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              {t('deleteWarning', { name: deleteTarget.name })}
            </p>
            <p className="text-sm font-semibold text-red-600 mb-6">{t('deleteIrreversible')}</p>
            {runningScenarioId === deleteTarget.id && (
              <p className="text-xs text-amber-600 bg-amber-50 rounded px-3 py-2 mb-4">{t('deleteDisabledRunning')}</p>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50"
              >
                {t('cancel')}
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={deleting || runningScenarioId === deleteTarget.id}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
              >
                {deleting ? t('deletingBtn') : t('deleteConfirmBtn')}
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
          <div className="lg:col-span-1 flex flex-col min-h-0">
            <ScenarioList
              scenarios={scenarios}
              viewMode={viewMode}
              onViewModeChange={handleViewModeChange}
              onSelect={handleSelect}
              onArchive={handleArchive}
              onUnarchive={handleUnarchive}
              onDeleteRequest={setDeleteTarget}
              selectedId={selectedScenario?.id}
              runningId={runningScenarioId}
            />
          </div>
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

// ─── 辅助组件 ────────────────────────────────────────────────────────────────

/** 表单分区：带标题的卡片容器 */
function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 border-b border-gray-100 pb-2">{title}</h3>
      {children}
    </div>
  );
}

/** 动态字符串数组输入：支持增加/删除条目 */
function StringArrayInput({
  label,
  items,
  onChange,
  placeholder,
  addLabel,
}: {
  label: string;
  items: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  addLabel: string;
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <label className="text-xs font-medium text-gray-600">{label}</label>
        <button
          type="button"
          onClick={() => onChange([...items, ''])}
          className="text-xs text-indigo-600 hover:text-indigo-800"
        >
          + {addLabel}
        </button>
      </div>
      {items.map((item, idx) => (
        <div key={idx} className="flex gap-2 mb-1.5">
          <input
            value={item}
            placeholder={placeholder}
            onChange={e => {
              const updated = [...items];
              updated[idx] = e.target.value;
              onChange(updated);
            }}
            className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm"
          />
          <button
            type="button"
            onClick={() => onChange(items.filter((_, i) => i !== idx))}
            className="text-red-500 hover:text-red-700 text-xs px-1"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
