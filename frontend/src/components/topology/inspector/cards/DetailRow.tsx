'use client';

/** 键值对行 */
interface DetailRowProps {
  label: string;
  value: string;
  mono?: boolean;
  children?: React.ReactNode;
}

export default function DetailRow({ label, value, mono, children }: DetailRowProps) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-gray-500">{label}</span>
      <div className="flex items-center gap-2">
        {children}
        <span className={`text-gray-900 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
      </div>
    </div>
  );
}
