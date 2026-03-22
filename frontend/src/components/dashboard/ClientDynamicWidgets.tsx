'use client';

import { useState, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import type { TopologySnapshot, ActivityEvent } from '@/lib/api/types';
import ActivityFeed from './ActivityFeed';

// 3D 拓扑组件：使用 dynamic import 延迟加载，禁用 SSR（依赖 WebGL）
const MiniTopology3D = dynamic(
  () => import('./MiniTopology3D'),
  { ssr: false },
);

// 粒子背景组件：纯装饰性，延迟加载不阻塞首屏渲染
const ParticleBackground = dynamic(
  () => import('./ParticleBackground'),
  { ssr: false },
);

/**
 * 运行时帧率监控 hook
 * 连续 3 秒低于 30fps 时触发降级回调，关闭高开销视觉特效
 */
function usePerformanceMonitor(onDegrade: () => void) {
  useEffect(() => {
    let frames = 0;
    let lastTime = performance.now();
    let lowFpsCount = 0;
    let frameId: number;

    const measure = () => {
      frames++;
      const now = performance.now();
      if (now - lastTime >= 1000) {
        const fps = frames;
        frames = 0;
        lastTime = now;
        if (fps < 30) {
          lowFpsCount++;
          // 连续 3 秒低于 30fps 触发降级
          if (lowFpsCount >= 3) {
            onDegrade();
            return;
          }
        } else {
          lowFpsCount = 0;
        }
      }
      frameId = requestAnimationFrame(measure);
    };
    frameId = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(frameId);
  }, [onDegrade]);
}

interface ClientDynamicWidgetsProps {
  topologySnapshot: TopologySnapshot;
  recentActivity: ActivityEvent[];
}

/**
 * 客户端动态加载包装组件
 * 将需要 ssr: false 的 dynamic import 封装在客户端组件中
 * 解决 Next.js 16 不允许在 Server Component 中使用 dynamic + ssr: false 的限制
 * 包含运行时性能监控：帧率持续低于 30fps 时自动降级
 */
export default function ClientDynamicWidgets({
  topologySnapshot,
  recentActivity,
}: ClientDynamicWidgetsProps) {
  const [degraded, setDegraded] = useState(false);
  const handleDegrade = useCallback(() => setDegraded(true), []);
  usePerformanceMonitor(handleDegrade);

  return (
    <>
      {/* 粒子背景动效：降级时不渲染 */}
      {!degraded && <ParticleBackground />}
      {/* 3D 迷你拓扑 + 活动流 */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <div className="h-full">
          <MiniTopology3D snapshot={topologySnapshot} />
        </div>
        <div className="h-full">
          <ActivityFeed initialEvents={recentActivity} />
        </div>
      </section>
    </>
  );
}
