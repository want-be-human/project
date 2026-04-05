import { FlowRecord } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import { formatBytes } from '@/lib/utils';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import { MouseEvent } from 'react';

interface FlowTableProps {
  flows: FlowRecord[];
  onSelect: (flow: FlowRecord) => void;
  selectedId?: string | null;
}

export default function FlowTable({ flows, onSelect, selectedId }: FlowTableProps) {
  const t = useTranslations('flows');

  if (flows.length === 0) {
    return (
      <div className="bg-white p-8 rounded-lg shadow-sm border border-gray-200 text-center text-gray-500">
        {t('empty')}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-auto h-full">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50 sticky top-0 z-10">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('time')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('source')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('destination')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('proto')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('duration')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('bytes')}</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{t('score')}</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {flows.map((flow) => {
            const isSelected = selectedId === flow.id;
            const scoreColor =
              flow.anomaly_score == null ? 'text-gray-400' :
              flow.anomaly_score > 0.8 ? 'text-red-600 font-bold' :
              flow.anomaly_score > 0.5 ? 'text-orange-500' :
              'text-green-600';

            return (
              <tr 
                key={flow.id} 
                className={clsx(
                  "hover:bg-gray-50 cursor-pointer transition-colors",
                  isSelected && "bg-blue-50 hover:bg-blue-100"
                )}
                onClick={() => onSelect(flow)}
              >
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {format(new Date(flow.ts_start), 'HH:mm:ss.SSS')}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {flow.src_ip}:{flow.src_port}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {flow.dst_ip}:{flow.dst_port}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">
                    {flow.proto}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {(() => {
                    const ms = new Date(flow.ts_end).getTime() - new Date(flow.ts_start).getTime();
                    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
                  })()}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatBytes(flow.bytes_fwd + flow.bytes_bwd)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <span className={scoreColor}>
                    {flow.anomaly_score != null ? flow.anomaly_score.toFixed(3) : '--'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
