import { FlowRecord } from '@/lib/api/types';
import { X } from 'lucide-react';
import { format } from 'date-fns';

interface FlowDetailDrawerProps {
  flow: FlowRecord | null;
  onClose: () => void;
}

export default function FlowDetailDrawer({ flow, onClose }: FlowDetailDrawerProps) {
  if (!flow) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-[500px] bg-white shadow-2xl transform transition-transform duration-300 ease-in-out border-l border-gray-200 overflow-y-auto z-50">
      <div className="p-6">
        <div className="flex justify-between items-start mb-6">
          <h2 className="text-xl font-bold text-gray-900">Flow Details</h2>
          <button 
            onClick={onClose}
            className="p-1 rounded-full hover:bg-gray-100 text-gray-500"
          >
            <X size={20} />
          </button>
        </div>

        <div className="space-y-6">
          <section>
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">5-Tuple</h3>
            <div className="grid grid-cols-2 gap-4 bg-gray-50 p-4 rounded-lg">
              <div>
                <span className="block text-xs text-gray-500">Source</span>
                <span className="font-mono text-sm">{flow.src_ip}:{flow.src_port}</span>
              </div>
              <div>
                <span className="block text-xs text-gray-500">Destination</span>
                <span className="font-mono text-sm">{flow.dst_ip}:{flow.dst_port}</span>
              </div>
              <div>
                <span className="block text-xs text-gray-500">Protocol</span>
                <span className="font-medium text-sm">{flow.proto}</span>
              </div>
              <div>
                <span className="block text-xs text-gray-500">Score</span>
                <span className={`font-medium text-sm ${flow.anomaly_score > 0.5 ? 'text-red-600' : 'text-green-600'}`}>
                  {flow.anomaly_score}
                </span>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Timing</h3>
            <div className="grid grid-cols-1 gap-2 text-sm">
              <div className="flex justify-between border-b pb-2">
                <span className="text-gray-500">Start</span>
                <span className="font-mono">{flow.ts_start}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-gray-500">End</span>
                <span className="font-mono">{flow.ts_end}</span>
              </div>
              <div className="flex justify-between pt-1">
                <span className="text-gray-500">Duration (ms)</span>
                <span>{(new Date(flow.ts_end).getTime() - new Date(flow.ts_start).getTime())}</span>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Statistics</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="bg-blue-50 p-3 rounded">
                <span className="block text-xs text-blue-600 mb-1">Forward</span>
                <div className="flex justify-between">
                  <span>Pkts: {flow.packets_fwd}</span>
                  <span>Bytes: {flow.bytes_fwd}</span>
                </div>
              </div>
              <div className="bg-purple-50 p-3 rounded">
                <span className="block text-xs text-purple-600 mb-1">Backward</span>
                <div className="flex justify-between">
                  <span>Pkts: {flow.packets_bwd}</span>
                  <span>Bytes: {flow.bytes_bwd}</span>
                </div>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Extracted Features</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto font-mono">
              {JSON.stringify(flow.features, null, 2)}
            </pre>
          </section>
        </div>
      </div>
    </div>
  );
}
