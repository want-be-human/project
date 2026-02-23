import { Alert } from '@/lib/api/types';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import Link from 'next/link';

interface AlertTableProps {
  alerts: Alert[];
  onStatusChange: (id: string, newStatus: string) => void;
}

export default function AlertTable({ alerts, onStatusChange }: AlertTableProps) {
  if (alerts.length === 0) {
    return (
      <div className="bg-white p-8 rounded-lg shadow-sm border border-gray-200 text-center text-gray-500">
        No alerts found.
      </div>
    );
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-200';
      case 'high': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low': return 'bg-blue-100 text-blue-800 border-blue-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'new': return 'bg-red-50 text-red-700';
      case 'triaged': return 'bg-blue-50 text-blue-700';
      case 'investigating': return 'bg-purple-50 text-purple-700';
      case 'resolved': return 'bg-green-50 text-green-700';
      case 'false_positive': return 'bg-gray-50 text-gray-700';
      default: return 'bg-gray-50 text-gray-700';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Severity</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source IP</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Dest Port</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tags</th>
            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {alerts.map((alert) => (
            <tr key={alert.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {format(new Date(alert.created_at), 'MM-dd HH:mm:ss')}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                <span className={clsx("px-2.5 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full border", getSeverityColor(alert.severity))}>
                  {alert.severity}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">
                {alert.type}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                {alert.entities.primary_src_ip}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                {alert.entities.primary_service?.dst_port || '-'}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                <select
                  value={alert.status}
                  onChange={(e) => onStatusChange(alert.id, e.target.value)}
                  className={clsx("text-xs font-semibold rounded-full px-2 py-1 border-0 cursor-pointer focus:ring-2 focus:ring-blue-500", getStatusColor(alert.status))}
                >
                  <option value="new">New</option>
                  <option value="triaged">Triaged</option>
                  <option value="investigating">Investigating</option>
                  <option value="resolved">Resolved</option>
                  <option value="false_positive">False Positive</option>
                </select>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                <div className="flex gap-1">
                  {alert.tags?.map(tag => (
                    <span key={tag} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                      {tag}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <Link href={`/alerts/${alert.id}`} className="text-blue-600 hover:text-blue-900">
                  View Details
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
