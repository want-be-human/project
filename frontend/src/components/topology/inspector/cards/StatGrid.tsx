'use client';

/** N 列指标网格 */
interface StatGridProps {
  items: Array<{ label: string; value: string | number; color?: string }>;
  columns?: 2 | 3;
}

export default function StatGrid({ items, columns = 3 }: StatGridProps) {
  const gridCls = columns === 2 ? 'grid-cols-2' : 'grid-cols-3';
  return (
    <div className={`grid ${gridCls} gap-2`}>
      {items.map((item, i) => (
        <div key={i} className="bg-gray-50 rounded-md px-2 py-1.5 text-center">
          <div className={`text-lg font-bold ${item.color ?? 'text-gray-900'}`}>
            {item.value}
          </div>
          <div className="text-[10px] text-gray-500 leading-tight">{item.label}</div>
        </div>
      ))}
    </div>
  );
}
