'use client';

/** 可点击的节点/边迷你列表 */
interface MiniNodeListProps {
  items: Array<{ id: string; label: string; value: number }>;
  onSelect?: (id: string) => void;
  maxItems?: number;
  /** value 的格式化函数 */
  formatValue?: (v: number) => string;
}

/** 风险色点颜色 */
function riskDotColor(v: number): string {
  if (v > 0.7) return 'bg-red-500';
  if (v > 0.3) return 'bg-yellow-400';
  return 'bg-green-400';
}

export default function MiniNodeList({ items, onSelect, maxItems = 5, formatValue }: MiniNodeListProps) {
  const display = items.slice(0, maxItems);
  const fmt = formatValue ?? ((v: number) => v.toFixed(2));

  if (display.length === 0) return <div className="text-xs text-gray-400 italic">—</div>;

  return (
    <div className="space-y-0.5">
      {display.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect?.(item.id)}
          className="w-full flex items-center gap-2 px-2 py-1 rounded hover:bg-blue-50 transition-colors text-left group"
        >
          <span className={`w-2 h-2 rounded-full shrink-0 ${riskDotColor(item.value)}`} />
          <span className="text-xs text-gray-700 truncate flex-grow group-hover:text-blue-700">
            {item.label}
          </span>
          <span className="text-[10px] font-mono text-gray-500 shrink-0">{fmt(item.value)}</span>
        </button>
      ))}
    </div>
  );
}
