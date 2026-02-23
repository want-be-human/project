import { useState } from 'react';

interface FlowFilters {
  src_ip?: string;
  dst_ip?: string;
  proto?: string;
  min_score?: string;
}

interface FlowFilterBarProps {
  onFilterChange: (filters: FlowFilters) => void;
}

export default function FlowFilterBar({ onFilterChange }: FlowFilterBarProps) {
  const [filters, setFilters] = useState<FlowFilters>({});

  const updateFilter = (key: keyof FlowFilters, value: string) => {
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
        <label className="block text-sm font-medium text-gray-700 mb-1">Source IP</label>
        <input 
          type="text" 
          placeholder="192.168.1.1" 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40 focus:ring-blue-500 focus:border-blue-500"
          onChange={(e) => updateFilter('src_ip', e.target.value)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Dest IP</label>
        <input 
          type="text" 
          placeholder="10.0.0.1" 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40"
          onChange={(e) => updateFilter('dst_ip', e.target.value)}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Protocol</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => updateFilter('proto', e.target.value)}
        >
          <option value="">All</option>
          <option value="TCP">TCP</option>
          <option value="UDP">UDP</option>
          <option value="ICMP">ICMP</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Min Score</label>
        <input 
          type="number" 
          min="0"
          max="1"
          step="0.1"
          placeholder="0.0" 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-24"
          onChange={(e) => updateFilter('min_score', e.target.value)}
        />
      </div>
       <div className="flex-grow"></div>
    </div>
  );
}
