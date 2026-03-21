'use client';

import { useEffect, useRef, useState } from 'react';

interface CountUpProps {
  /** 目标值 */
  end: number;
  /** 动画时长（毫秒），默认 800ms */
  duration?: number;
  /** 小数位数，默认 0 */
  decimals?: number;
}

/** easeOutCubic 缓动函数（导出以便属性测试使用） */
export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * 数字滚动动画组件
 * 从当前显示值平滑过渡到新目标值，使用 requestAnimationFrame 驱动动画
 */
export default function CountUp({ end, duration = 800, decimals = 0 }: CountUpProps) {
  const [display, setDisplay] = useState(end.toFixed(decimals));
  const prevEndRef = useRef(end);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    // 检测用户是否偏好减少动画
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const from = prevEndRef.current;
    const to = end;
    prevEndRef.current = end;

    // 目标值未变化或用户偏好减少动画时，直接显示目标值
    if (from === to || prefersReducedMotion) {
      setDisplay(to.toFixed(decimals));
      return;
    }

    let start: number | null = null;

    const animate = (timestamp: number) => {
      if (start === null) start = timestamp;
      const elapsed = timestamp - start;
      // 计算动画进度（0 ~ 1）
      const progress = Math.min(elapsed / duration, 1);
      // 从上一次目标值过渡到新目标值，应用缓动函数
      const current = from + (to - from) * easeOutCubic(progress);
      setDisplay(current.toFixed(decimals));

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        // 动画结束后强制设置精确值，避免浮点精度偏差
        setDisplay(to.toFixed(decimals));
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    // 组件卸载或依赖变化时清理动画帧
    return () => cancelAnimationFrame(rafRef.current);
  }, [end, duration, decimals]);

  return <span>{display}</span>;
}
