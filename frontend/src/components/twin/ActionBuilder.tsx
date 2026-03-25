'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { ActionPlan, Recommendation, CompilePlanResponse, CompiledAction, SkippedAction } from '@/lib/api/types';
import { Send, AlertTriangle, Zap, ChevronDown, ChevronUp, Shield, Check, X } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';

interface ActionBuilderProps {
  alertId: string;
  initialRecommendation?: Recommendation | null;
  onPlanCreated: (plan: ActionPlan) => void;
}

export default function ActionBuilder({ alertId, initialRecommendation, onPlanCreated }: ActionBuilderProps) {
  const t = useTranslations('twin');
  const tc = useTranslations('confidence');
  const locale = useLocale();

  // compile-plan 状态
  const [compiledResult, setCompiledResult] = useState<CompilePlanResponse | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [expandedActions, setExpandedActions] = useState<number[]>([]);
  // 编译错误信息（null 表示无错误）
  const [compileError, setCompileError] = useState<string | null>(null);

  // ── 根据错误消息分类，返回对应的用户提示 ──
  const classifyCompileError = (err: unknown): string => {
    const msg = err instanceof Error ? err.message : String(err);
    // fetchJson 抛出格式: "API Error: {status} {statusText} - {detail}"
    const statusMatch = msg.match(/API Error:\s*(\d{3})/);
    const status = statusMatch ? parseInt(statusMatch[1], 10) : 0;

    // 422: 验证失败，通常是缺少 recommendation
    if (status === 422 || /validation/i.test(msg)) {
      return t('compileErrorNoRecommendation');
    }
    // 404: 建议不存在或已过期
    if (status === 404 || /not found/i.test(msg)) {
      return t('compileErrorNotFound');
    }
    // 5xx: 服务器内部错误
    if (status >= 500) {
      return t('compileErrorServer');
    }
    // 兜底：优先展示后端返回的原始详情
    const detailMatch = msg.match(/- (.+)$/);
    if (detailMatch) {
      return `${t('compileFailed')} — ${detailMatch[1]}`;
    }
    return t('compileErrorServer');
  };

  // ── 编译方案 ──
  const handleCompilePlan = async () => {
    setCompiling(true);
    setCompileError(null); // 清除上次错误
    setCompiledResult(null); // 清除上次结果
    try {
      const result = await api.compilePlan(alertId, {
        recommendation_id: initialRecommendation?.id || null,
        language: locale === 'zh' ? 'zh' : 'en',
      });

      // 始终保存结果（即使 0 动作），以便展示跳过详情
      setCompiledResult(result);
    } catch (e) {
      console.error(e);
      setCompileError(classifyCompileError(e));
    } finally {
      setCompiling(false);
    }
  };

  // ── 确认编译计划，直接使用后端返回的 compiled plan ──
  const handleConfirmPlan = () => {
    if (compiledResult) {
      onPlanCreated(compiledResult.plan);
    }
  };

  // ── 展开/折叠动作详情 ──
  const toggleExpand = (idx: number) => {
    setExpandedActions(prev =>
      prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx]
    );
  };

  // ── 置信度颜色辅助函数 ──
  const confidenceColor = (c: number) => {
    if (c >= 0.8) return { bar: 'bg-green-500', text: 'text-green-700', bg: 'bg-green-50' };
    if (c >= 0.6) return { bar: 'bg-yellow-500', text: 'text-yellow-700', bg: 'bg-yellow-50' };
    return { bar: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50' };
  };

  const compiledActions = compiledResult?.plan.actions as CompiledAction[] | undefined;
  const hasCompiled = !!compiledActions && compiledActions.length > 0;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Send className="w-5 h-5 text-blue-600" /> {t('builderTitle')}
        </h3>
        {hasCompiled && (
          <span className="px-2 py-1 text-xs rounded-full bg-indigo-100 text-indigo-700">
            {t('source')} {t('compiledSource')}
          </span>
        )}
      </div>

      {/* ── 编译方案按钮（仅在有 recommendation 且尚未编译时显示） ── */}
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

      {/* ── 编译错误提示（红色内联块） ── */}
      {compileError && (
        <div className="mb-4 flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-500" />
          <span className="flex-1">{compileError}</span>
          <button
            onClick={() => setCompileError(null)}
            className="flex-shrink-0 text-red-400 hover:text-red-600"
            aria-label={t('compileErrorDismiss')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ── 编译完成但无可执行动作（amber 警告面板） ── */}
      {compiledResult && (!compiledResult.plan.actions || compiledResult.plan.actions.length === 0) && (
        <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            <h4 className="text-sm font-semibold text-amber-800">
              {t('compileEmptyTitle')}
            </h4>
          </div>

          {compiledResult.compilation.empty_reason && (
            <p className="text-sm text-amber-700 mb-3">
              {compiledResult.compilation.empty_reason}
            </p>
          )}

          {compiledResult.compilation.skipped_actions && compiledResult.compilation.skipped_actions.length > 0 && (
            <div className="space-y-2 mb-3">
              <p className="text-xs font-semibold text-amber-700">{t('skippedActionsTitle')}</p>
              {compiledResult.compilation.skipped_actions.map((sa: SkippedAction, idx: number) => (
                <div key={idx} className="bg-white rounded border border-amber-200 p-2 text-xs">
                  <div className="font-medium text-gray-800">{sa.title}</div>
                  <div className="text-gray-500 mt-1">
                    <span className="font-semibold">{t('skipReason')}:</span> {sa.reason}
                  </div>
                  {sa.suggestion && (
                    <div className="text-amber-600 mt-1">{sa.suggestion}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <button
              onClick={handleCompilePlan}
              disabled={compiling}
              className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-700 text-white rounded disabled:opacity-50"
            >
              {t('retryCompile')}
            </button>
          </div>
        </div>
      )}

      {/* ── 已编译动作面板（只读展示） ── */}
      {hasCompiled && compiledActions && (
        <div className="mb-6 space-y-3">
          {/* 编译元信息 */}
          <div className="flex items-center gap-4 text-xs text-gray-500 bg-gray-50 rounded px-3 py-2 border border-gray-100">
            <span className="font-semibold text-gray-700">{t('compilationMeta')}</span>
            <span>{t('rulesMatched')}: <strong className="text-gray-800">{compiledResult!.compilation.rules_matched}</strong></span>
            <span>{t('actionsSkipped')}: <strong className="text-gray-800">{compiledResult!.compilation.actions_skipped}</strong></span>
            <span>{t('compilerVersion')}: <strong className="text-gray-800">{compiledResult!.compilation.compiler_version}</strong></span>
          </div>

          {/* 动作标题 */}
          <h4 className="text-sm font-semibold text-indigo-800 flex items-center gap-1.5">
            <Shield className="w-4 h-4" /> {t('compiledActions')}
          </h4>

          {/* 动作卡片（只读，无 checkbox） */}
          {compiledActions.map((action, idx) => {
            const cc = confidenceColor(action.confidence);
            const isExpanded = expandedActions.includes(idx);
            return (
              <div key={idx} className="rounded border-2 border-indigo-400 bg-white">
                {/* 头部 */}
                <div className="flex items-center gap-3 p-3">
                  <span className="font-mono text-sm font-bold text-gray-800">{action.action_type}</span>
                  <span className="text-gray-400">→</span>
                  <span className="font-mono text-sm text-blue-600">{action.target.type}:{action.target.value}</span>
                  <div className="ml-auto flex items-center gap-2">
                    {/* 置信度徽标 */}
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${cc.bg} ${cc.text}`} title={tc('actionConfidenceTooltip')}>
                      {tc('actionConfidenceLabel')}: {(action.confidence * 100).toFixed(0)}%
                    </span>
                    <button onClick={() => toggleExpand(idx)} className="text-gray-400 hover:text-gray-600">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* 置信度进度条 */}
                <div className="px-3 pb-2">
                  <div className="w-full bg-gray-200 rounded-full h-1.5">
                    <div className={`${cc.bar} h-1.5 rounded-full transition-all`} style={{ width: `${action.confidence * 100}%` }} />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">{tc('disclaimer')}</p>
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

      {/* ── 确认编译计划按钮 ── */}
      {hasCompiled && (
        <div className="flex justify-end pt-4 border-t border-gray-100">
          <button
            onClick={handleConfirmPlan}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded shadow-sm text-sm font-medium flex items-center gap-2"
          >
            {t('confirmPlan')}
            <Check className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
