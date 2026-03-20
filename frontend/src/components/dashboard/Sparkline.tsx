'use client';

interface SparklineProps {
  /** 数据点数组 */
  data: number[];
  /** SVG 宽度，默认 80 */
  width?: number;
  /** SVG 高度，默认 24 */
  height?: number;
  /** 折线颜色，默认 '#00d4ff' */
  color?: string;
}

/**
 * 迷你趋势线组件
 * 接收数据点数组，使用 SVG polyline 渲染折线图
 */
export default function Sparkline({
  data,
  width = 80,
  height = 24,
  color = '#00d4ff',
}: SparklineProps) {
  // 空数据时不渲染
  if (!data || data.length === 0) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1; // 避免除以零

  // 内边距，防止折线紧贴边缘
  const padding = 2;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;

  // 将数据点映射到 SVG 坐标系
  const points = data
    .map((v, i) => {
      const x = padding + (i / (data.length - 1 || 1)) * innerW;
      const y = padding + innerH - ((v - min) / range) * innerH;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
