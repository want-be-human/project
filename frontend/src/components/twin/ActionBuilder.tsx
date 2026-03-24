'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { ActionPlan, Recommendation, CompilePlanResponse, CompiledAction } from '@/lib/api/types';
import { Plus, Trash2, Save, Send, AlertTriangle, Zap, ChevronDown, ChevronUp, CheckSquare, Square, Shield } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';

interface ActionBuilderProps {
  alertId: string;
  initialRecommendation?: Recommendation | null;
  onPlanCreated: (plan: ActionPlan) => void;
}

export default function ActionBuilder({ alertId, initialRecommendation, onPlanCreated }: ActionBuilderProps) {
  const t = useTranslations('twin');
  const locale = useLocale();
  const [actions, setActions] = useState<any[]>([]);
  const [source, setSource] = useState<'agent' | 'manual'>('manual');
  const [loading, setLoading] = useState(false);
  const [newActionType, setNewActionType] = useState('block_ip');
  const [newActionTarget, setNewActionTarget] = useState('');

  // compile-plan 状态
  const [compiledResult, setCompiledResult] = useState<CompilePlanResponse | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [selectedActions, setSelectedActions] = useState<number[]>([]);
  const [expandedActions, setExpandedActions] = useState<number[]>([]);

  // ── 编译方案 ──
  const handleCompilePlan = async () => {
    setCompiling(true);
    try {
      const result = await api.compilePlan(alertId, {
        recommendation_id: initialRecommendation?.id || null,
        language: locale === 'zh' ? 'zh' : 'en',
      });
      setCompiledResult(result);
      // 默认全选已编译动作
      const compiledActions = result.plan.actions as CompiledAction[];
      setSelectedActions(compiledActions.map((_, i) => i));
      setSource('agent');
    } catch (e) {
      console.error(e);
      alert(t('compileFailed'));
    } finally {
      setCompiling(false);
    }
  };

  // ── 切换动作选中状态 ──
  const toggleAction = (idx: number) => {
    setSelectedActions(prev =>
      prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
    );
  };

  const toggleSelectAll = () => {
    if (!compiledResult) return;
    const all = (compiledResult.plan.actions as CompiledAction[]).map((_, i) => i);
    setSelectedActions(prev => prev.length === all.length ? [] : all);
  };

  const toggleExpand = (idx: number) => {
    setExpandedActions(prev =>
      prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
    );
  };

  const addAction = () => {
    setActions([...actions, {
      type: newActionType,
      target: newActionTarget,
      params: {},
    }]);
    setNewActionTarget('');
  };

  const removeAction = (index: number) => {
    const newActions = [...actions];
    newActions.splice(index, 1);
    setActions(newActions);
  };

  // ── 创建方案 ──
  const handleCreatePlan = async () => {
    setLoading(true);
    try {
      if (compiledResult) {
        // 后端 compile-plan 已通过 TwinService.create_plan() 持久化方案
        // 直接使用编译方案，无需再次调用 createPlan
        onPlanCreated(compiledResult.plan);
      } else {
        // 兜底：手工 actions → createPlan
        const plan = await api.createPlan({
          alert_id: alertId,
          source: source,
          actions: actions,
          notes: 'Created via ActionBuilder'
        });
        onPlanCreated(plan);
      }
    } catch (e) {
      console.error(e);
      alert(t('createFailed'));
    } finally {
      setLoading(false);
    }
  };

  // ── 置信度颜色辅助函数 ──
  const confidenceColor = (c: number) => {
    if (c >= 0.8) return { bar: 'bg-green-500', text: 'text-green-700', bg: 'bg-green-50' };
    if (c >= 0.6) return { bar: 'bg-yellow-500', text: 'text-yellow-700', bg: 'bg-yellow-50' };
    return { bar: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50' };
  };

  const compiledActions = compiledResult?.plan.actions as CompiledAction[] | undefined;
  const hasCompiled = !!compiledActions && compiledActions.length > 0;
  const canCreate = hasCompiled ? selectedActions.length > 0 : actions.length > 0;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Send className="w-5 h-5 text-blue-600" /> {t('builderTitle')}
        </h3>
        <span className={`px-2 py-1 text-xs rounded-full ${
          hasCompiled ? 'bg-indigo-100 text-indigo-700' :
          source === 'agent' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'
        }`}>
          {t('source')} {hasCompiled ? t('compiledSource') : source === 'agent' ? 'AGENT' : t('manualSource')}
        </span>
      </div>

      {/* ── 编译方案按钮 ── */}
      {initialRecommendation && !hasCompiled && (
        <div className="mb-4">
          <button
            onClick={handleCompilePlan}
            disabled={compiling}
            className="w-full px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded shadow-sm text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Zap className="w-4 h-4" />
            {compiling ? t('compiling') : t('compilePlan')}
          </button>
          {/* 提示用户：需要先编译才能生成结构化动作 */}
          <div className="mt-2 flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded px-3 py-2 border border-amber-200">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{t('pleaseCompileFirst')}</span>
          </div>
        </div>
      )}

      {/* ── 已编译动作面板 ── */}
      {hasCompiled && compiledActions && (
        <div className="mb-6 space-y-3">
          {/* 编译元信息 */}
          <div className="flex items-center gap-4 text-xs text-gray-500 bg-gray-50 rounded px-3 py-2 border border-gray-100">
            <span className="font-semibold text-gray-700">{t('compilationMeta')}</span>
            <span>{t('rulesMatched')}: <strong className="text-gray-800">{compiledResult!.compilation.rules_matched}</strong></span>
            <span>{t('actionsSkipped')}: <strong className="text-gray-800">{compiledResult!.compilation.actions_skipped}</strong></span>
            <span>{t('compilerVersion')}: <strong className="text-gray-800">{compiledResult!.compilation.compiler_version}</strong></span>
          </div>

          {/* 全选 */}
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-indigo-800 flex items-center gap-1.5">
              <Shield className="w-4 h-4" /> {t('compiledActions')}
            </h4>
            <button onClick={toggleSelectAll} className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
              {selectedActions.length === compiledActions.length ? <CheckSquare className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
              {t('selectAll')}
            </button>
          </div>

          {/* 动作卡片 */}
          {compiledActions.map((action, idx) => {
            const cc = confidenceColor(action.confidence);
            const isSelected = selectedActions.includes(idx);
            const isExpanded = expandedActions.includes(idx);
            return (
              <div
                key={idx}
                className={`rounded border-2 transition-colors ${
                  isSelected ? 'border-indigo-400 bg-white' : 'border-gray-200 bg-gray-50 opacity-70'
                }`}
              >
                {/* 头部 */}
                <div className="flex items-center gap-3 p-3 cursor-pointer" onClick={() => toggleAction(idx)}>
                  <span className="flex-shrink-0">
                    {isSelected ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4 text-gray-400" />}
                  </span>
                  <span className="font-mono text-sm font-bold text-gray-800">{action.action_type}</span>
                  <span className="text-gray-400">→</span>
                  <span className="font-mono text-sm text-blue-600">{action.target.type}:{action.target.value}</span>
                  <div className="ml-auto flex items-center gap-2">
                    {/* 置信度徽标 */}
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${cc.bg} ${cc.text}`}>
                      {t('confidence')}: {(action.confidence * 100).toFixed(0)}%
                    </span>
                    <button onClick={(e) => { e.stopPropagation(); toggleExpand(idx); }} className="text-gray-400 hover:text-gray-600">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* 置信度进度条 */}
                <div className="px-3 pb-2">
                  <div className="w-full bg-gray-200 rounded-full h-1.5">
                    <div className={`${cc.bar} h-1.5 rounded-full transition-all`} style={{ width: `${action.confidence * 100}%` }} />
                  </div>
                </div>

                {/* 推理摘要（始终可见） */}
                <div className="px-3 pb-3 text-xs text-gray-600">
                  <span className="font-semibold text-gray-500">{t('reasoning')}:</span> {action.reasoning_summary}
                </div>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="px-3 pb-3 space-y-2 border-t border-gray-100 pt-2">
                    {/* 证据 */}
                    <div>
                      <span className="text-xs font-semibold text-gray-500">{t('evidence')}:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {action.derived_from_evidence.map((eid, i) => (
                          <span key={i} className="px-1.5 py-0.5 bg-blue-50 text-blue-700 text-xs rounded font-mono">{eid}</span>
                        ))}
                      </div>
                    </div>
                    {/* 参数 */}
                    <div>
                      <span className="text-xs font-semibold text-gray-500">{t('params')}:</span>
                      <pre className="mt-1 text-xs bg-gray-50 rounded p-2 overflow-x-auto text-gray-700">{JSON.stringify(action.params, null, 2)}</pre>
                    </div>
                    {/* 回滚 */}
                    {action.rollback && (
                      <div>
                        <span className="text-xs font-semibold text-gray-500">{t('rollback')}:</span>
                        <pre className="mt-1 text-xs bg-orange-50 rounded p-2 overflow-x-auto text-orange-700">{JSON.stringify(action.rollback, null, 2)}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Manual Actions (fallback, or when no compiled result) ── */}
      {!hasCompiled && (
        <>
          <div className="space-y-4 mb-6">
            {actions.length === 0 ? (
              <div className="text-center py-8 text-gray-400 bg-gray-50 rounded border border-dashed border-gray-200">
                {t('noActions')}
              </div>
            ) : (
              actions.map((action, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded border border-gray-200">
                  <div>
                    <span className="font-mono text-sm font-bold text-gray-800">{action.type}</span>
                    <span className="mx-2 text-gray-400">→</span>
                    <span className="font-mono text-sm text-blue-600">{JSON.stringify(action.target)}</span>
                  </div>
                  <button onClick={() => removeAction(idx)} className="text-gray-400 hover:text-red-500">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>

          {/* Simple Add Form */}
          <div className="flex gap-2 mb-6">
            <select 
              className="border border-gray-300 rounded px-2 py-1.5 text-sm"
              value={newActionType}
              onChange={(e) => setNewActionType(e.target.value)}
            >
              <option value="block_ip">block_ip</option>
              <option value="isolate_host">isolate_host</option>
              <option value="segment_subnet">segment_subnet</option>
              <option value="rate_limit_service">rate_limit_service</option>
            </select>
            <input 
              type="text" 
              placeholder={t('targetPlaceholder')} 
              className="border border-gray-300 rounded px-2 py-1.5 text-sm flex-1"
              value={newActionTarget}
              onChange={(e) => setNewActionTarget(e.target.value)}
            />
            <button 
              onClick={addAction}
              disabled={!newActionTarget}
              className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-sm disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </>
      )}

      <div className="flex justify-end pt-4 border-t border-gray-100">
        <button
          onClick={handleCreatePlan}
          disabled={loading || !canCreate}
          className={`px-4 py-2 rounded shadow-sm text-sm font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${
            hasCompiled
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
          }`}
        >
          {loading ? t('creating') : hasCompiled ? t('useSelected') : t('createPlan')}
          <Save className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
