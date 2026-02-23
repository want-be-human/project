import { Alert } from '@/lib/api/types';
import { format } from 'date-fns';

interface AlertEvidenceSectionProps {
  alert: Alert;
}

export default function AlertEvidenceSection({ alert }: AlertEvidenceSectionProps) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Evidence & Context</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Flows */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Top Flows</h3>
          <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-gray-100 text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Flow ID</th>
                  <th className="px-4 py-2 font-medium">Score</th>
                  <th className="px-4 py-2 font-medium">Summary</th>
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
                    <td colSpan={3} className="px-4 py-4 text-center text-gray-500">No flows recorded</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Top Features */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Top Features</h3>
          <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-gray-100 text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Feature Name</th>
                  <th className="px-4 py-2 font-medium">Value</th>
                  <th className="px-4 py-2 font-medium">Direction</th>
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
                    <td colSpan={3} className="px-4 py-4 text-center text-gray-500">No features recorded</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Time Window */}
      <div className="mt-6 pt-6 border-t border-gray-100">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Time Window</h3>
        <div className="flex gap-8 text-sm">
          <div>
            <span className="text-gray-500 mr-2">Start:</span>
            <span className="font-mono text-gray-900">{format(new Date(alert.time_window.start), 'yyyy-MM-dd HH:mm:ss.SSS')}</span>
          </div>
          <div>
            <span className="text-gray-500 mr-2">End:</span>
            <span className="font-mono text-gray-900">{format(new Date(alert.time_window.end), 'yyyy-MM-dd HH:mm:ss.SSS')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
