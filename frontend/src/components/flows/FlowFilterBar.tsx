import { Input } from '@/components/ui/input'; // Assuming we strictly follow shadcn or just basic html. I'll stick to basic tailwind for now as per instructions "UI 简洁即可" and I don't recall installing shadcn components. WIll use standard HTML elements styled with Tailwind.

interface FlowFilterBarProps {
  onFilterChange: (filters: any) => void;
}

export default function FlowFilterBar({ onFilterChange }: FlowFilterBarProps) {
  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 mb-4 flex gap-4 items-end flex-wrap">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Source IP</label>
        <input 
          type="text" 
          placeholder="192.168.1.1" 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40 focus:ring-blue-500 focus:border-blue-500"
          onChange={(e) => onFilterChange({ src_ip: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Dest IP</label>
        <input 
          type="text" 
          placeholder="10.0.0.1" 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-40"
          onChange={(e) => onFilterChange({ dst_ip: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Protocol</label>
        <select 
          className="border border-gray-300 rounded px-3 py-2 text-sm w-32 bg-white"
          onChange={(e) => onFilterChange({ proto: e.target.value })}
        >
          <option value="">All</option>
          <option value="TCP">TCP</option>
          <option value="UDP">UDP</option>
          <option value="ICMP">ICMP</option>
        </select>
      </div>
       <div className="flex-grow"></div>
      <button 
        className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        onClick={() => { /* Trigger refresh if needed, for now filters are immediate/managed by parent */ }}
      >
        Apply Filter
      </button>
    </div>
  );
}
