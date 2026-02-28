'use client';

import { Scenario } from '@/lib/api/types';
import { Play } from 'lucide-react';

interface Props {
  scenarios: Scenario[];
  onSelect: (scenario: Scenario) => void;
  selectedId?: string;
  runningId?: string;
}

export default function ScenarioList({ scenarios, onSelect, selectedId, runningId }: Props) {
  return (
    <div className="bg-white rounded-lg shadow border border-gray-200">
      <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-gray-800">Scenarios</h2>
        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">{scenarios.length} available</span>
      </div>
      <div className="divide-y divide-gray-100 overflow-y-auto max-h-[calc(100vh-200px)]">
        {scenarios.map((s) => (
          <div 
            key={s.id} 
            className={`p-4 cursor-pointer transition-colors ${
              selectedId === s.id ? 'bg-indigo-50 border-l-4 border-indigo-500' : 'hover:bg-gray-50 border-l-4 border-transparent'
            }`}
            onClick={() => onSelect(s)}
          >
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-medium text-gray-900">{s.name}</h3>
              {runningId === s.id && (
                <span className="flex items-center text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                  <Play className="w-3 h-3 mr-1 animate-pulse" /> Running
                </span>
              )}
            </div>
            {s.description && (
              <p className="text-sm text-gray-500 mb-3 line-clamp-2">{s.description}</p>
            )}
            <div className="flex flex-wrap gap-1 mb-3">
              {(s.tags || []).map(tag => (
                <span key={tag} className="text-[10px] uppercase font-semibold text-gray-600 bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded">
                  {tag}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-500 mb-1">
              <div>
                <span className="font-semibold text-gray-400">Min Alerts:</span> {s.min_alerts || 0}
              </div>
              <div>
                <span className="font-semibold text-gray-400">Dry-Run:</span> {s.dry_run_required ? 'Required' : 'Skipped'}
              </div>
            </div>
            <div className="text-xs text-gray-500">
              <span className="font-semibold text-gray-400">PCAP:</span> <span className="font-mono text-[10px]">{s.pcap_ref?.pcap_id?.slice(0,18)}...</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}