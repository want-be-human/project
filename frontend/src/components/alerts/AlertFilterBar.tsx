import { useState } from 'react';

interface AlertFilters {
  status?: string;
  severity?: string;
  type?: string;
}

interface AlertFilterBarProps {
  onFilterChange: (filters: AlertFilters) => void;
}

export default function AlertFilterBar({ onFilterChange }: AlertFilterBarProps) {
  const [filters, setFilters] = useState<AlertFilters>({});

  const updateFilter = (key: keyof AlertFilters, value: string) => {
    const newFilters = {
      ...filters,
      [key]: value || undefined
    };
    setFilters(newFilters);
    onFilterChange(newFilters);
  };

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 mb-4 flex gap-4 items-end flex-wrap">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('status', e.target.value)}
        >
          <option value="">All</option>
          <option value="new">New</option>
          <option value="triaged">Triaged</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
          <option value="false_positive">False Positive</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Severity</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('severity', e.target.value)}
        >
          <option value="">All</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('type', e.target.value)}
        >
          <option value="">All</option>
          <option value="anomaly">Anomaly</option>
          <option value="scan">Scan</option>
          <option value="dos">DoS</option>
          <option value="bruteforce">Bruteforce</option>
          <option value="exfil">Exfil</option>
          <option value="unknown">Unknown</option>
        </select>
      </div>
      <div className="flex-grow"></div>
    </div>
  );
}
