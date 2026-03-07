'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { ActionPlan, Recommendation } from '@/lib/api/types';
import { Plus, Trash2, Save, Send, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface ActionBuilderProps {
  alertId: string;
  initialRecommendation?: Recommendation | null;
  onPlanCreated: (plan: ActionPlan) => void;
}

export default function ActionBuilder({ alertId, initialRecommendation, onPlanCreated }: ActionBuilderProps) {
  const t = useTranslations('twin');
  const [actions, setActions] = useState<any[]>([]);
  const [source, setSource] = useState<'agent' | 'manual'>('manual');
  const [loading, setLoading] = useState(false);
  const [newActionType, setNewActionType] = useState('block_ip');
  const [newActionTarget, setNewActionTarget] = useState('');

  // Hydrate from recommendation
  useEffect(() => {
    if (initialRecommendation && initialRecommendation.actions.length > 0) {
      setActions(initialRecommendation.actions.map(a => ({
        type: a.type,
        target: a.target,
        params: a.params,
        rollback: a.rollback
      })));
      setSource('agent');
    }
  }, [initialRecommendation]);

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

  const handleCreatePlan = async () => {
    setLoading(true);
    try {
      const plan = await api.createPlan({
        alert_id: alertId,
        source: source,
        actions: actions,
        notes: 'Created via ActionBuilder'
      });
      onPlanCreated(plan);
    } catch (e) {
      console.error(e);
      alert(t('createFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Send className="w-5 h-5 text-blue-600" /> {t('builderTitle')}
        </h3>
        <span className={`px-2 py-1 text-xs rounded-full ${source === 'agent' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
          {t('source')} {source.toUpperCase()}
        </span>
      </div>

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
          <option value="disable_user">disable_user</option>
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

      <div className="flex justify-end pt-4 border-t border-gray-100">
        <button
          onClick={handleCreatePlan}
          disabled={loading || actions.length === 0}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded shadow-sm text-sm font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? t('creating') : t('createPlan')}
          <Save className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
