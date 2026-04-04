import { useRef, useState, useEffect } from 'react';

/**
 * 监听容器元素真实尺寸的 Hook
 * 内部使用 ResizeObserver + 防抖策略，返回经过防抖处理的 width/height
 *
 * @param debounceMs 防抖时长（毫秒），默认 200ms。首次测量不防抖，立即同步。
 * @returns containerRef —— 绑定到目标 DOM 元素；width/height —— 当前容器像素尺寸（未测量时为 0）
 */
export function useContainerSize(debounceMs = 200) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    /** 标记是否完成首次测量 */
    let hasMeasured = false;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;

      const w = Math.round(entry.contentRect.width);
      const h = Math.round(entry.contentRect.height);

      // 首次测量立即同步，避免首帧画布尺寸为 0
      if (!hasMeasured) {
        hasMeasured = true;
        setSize({ width: w, height: h });
        return;
      }

      // 后续 resize 走防抖，避免高频重渲染
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setSize({ width: w, height: h });
      }, debounceMs);
    });

    observer.observe(el);

    return () => {
      observer.disconnect();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [debounceMs]);

  return { containerRef, width: size.width, height: size.height };
}
