'use client';

/** 标签列表（协议/服务等） */
interface TagListProps {
  items: Array<{ label: string; count?: number }>;
  color?: string; // Tailwind 颜色前缀，如 'blue' | 'purple'
}

export default function TagList({ items, color = 'blue' }: TagListProps) {
  if (items.length === 0) return <div className="text-xs text-gray-400 italic">—</div>;

  // 预定义颜色映射，避免 Tailwind 动态类名问题
  const colorMap: Record<string, string> = {
    blue:   'bg-blue-50 text-blue-700 border-blue-100',
    purple: 'bg-purple-50 text-purple-700 border-purple-100',
    green:  'bg-green-50 text-green-700 border-green-100',
    gray:   'bg-gray-50 text-gray-700 border-gray-100',
  };
  const cls = colorMap[color] ?? colorMap.blue;

  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item, i) => (
        <span key={i} className={`px-1.5 py-0.5 text-[10px] font-mono rounded border ${cls}`}>
          {item.label}{item.count !== undefined && item.count > 1 ? ` ×${item.count}` : ''}
        </span>
      ))}
    </div>
  );
}
