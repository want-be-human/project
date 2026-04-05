import { Alert } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';

interface AlertEvidenceSectionProps {
  alert: Alert;
}

export default function AlertEvidenceSection({ alert }: AlertEvidenceSectionProps) {
  const t = useTranslations('alertDetail');

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('evidenceTitle')}</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 关键流量 */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">{t('topFlows')}</h3>
          <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-gray-100 text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">{t('flowId')}</th>
                  <th className="px-4 py-2 font-medium">{t('score')}</th>
                  <th className="px-4 py-2 font-medium">{t('summary')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {alert.evidence.top_flows.map((flow, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono text-xs text-gray-500 truncate max-w-[100px]" title={flow.flow_id}>
                      {flow.flow_id.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-2">
                      <span className={`font-medium ${flow.anomaly_score > 0.8 ? 'text-red-600' : 'text-orange-500'}`}>
                        {flow.anomaly_score.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{flow.summary}</td>
                  </tr>
                ))}
                {alert.evidence.top_flows.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-4 text-center text-gray-500">{t('noFlows')}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 关键特征 */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">{t('topFeatures')}</h3>
          <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-gray-100 text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">{t('featureName')}</th>
                  <th className="px-4 py-2 font-medium">{t('value')}</th>
                  <th className="px-4 py-2 font-medium">{t('direction')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {alert.evidence.top_features.map((feature, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-medium text-gray-700">{feature.name}</td>
                    <td className="px-4 py-2 font-mono text-gray-600">{feature.value}</td>
                    <td className="px-4 py-2">
                      {feature.direction && (
                        <span className={`px-2 py-0.5 rounded text-xs ${feature.direction === 'high' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'}`}>
                          {feature.direction}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {alert.evidence.top_features.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-4 text-center text-gray-500">{t('noFeaturesRecorded')}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 时间窗口 */}
      <div className="mt-6 pt-6 border-t border-gray-100">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">{t('timeWindow')}</h3>
        <div className="flex gap-8 text-sm">
          <div>
            <span className="text-gray-500 mr-2">{t('start')}</span>
            <span className="font-mono text-gray-900">{format(new Date(alert.time_window.start), 'yyyy-MM-dd HH:mm:ss.SSS')}</span>
          </div>
          <div>
            <span className="text-gray-500 mr-2">{t('end')}</span>
            <span className="font-mono text-gray-900">{format(new Date(alert.time_window.end), 'yyyy-MM-dd HH:mm:ss.SSS')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
