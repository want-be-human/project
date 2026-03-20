'use client';

import { useEffect, useRef, useState } from 'react';

interface CountUpProps {
  /** 目标值 */
  end: number;
  /** 动画时长（毫秒），默认 1000 */
  duration?: number;
  /** 小数位数，默认 0 */
  decimals?: number;
}

/** easeOutCubic 缓动函数 */
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * 数字滚动动画组件
 * 从 0 平滑滚动到目标值，使用 requestAnimationFrame 驱动动画
 */
export default function CountUp({ end, duration = 1000, decimals = 0 }: CountUpProps) {
  const [display, setDisplay] = useState('0');
  const rafRef = useRef<number>(0);

  useEffect(() => {
    let start: number | null = null;

    const animate = (timestamp: number) => {
      if (start === null) start = timestamp;
      const elapsed = timestamp - start;
      // 计算动画进度（0 ~ 1）
      const progress = Math.min(elapsed / duration, 1);
      // 应用缓动函数
      const current = end * easeOutCubic(progress);
      setDisplay(current.toFixed(decimals));

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    // 组件卸载时清理动画帧
    return () => cancelAnimationFrame(rafRef.current);
  }, [end, duration, decimals]);

  return <span>{display}</span>;
}
