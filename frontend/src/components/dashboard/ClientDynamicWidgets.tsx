'use client';

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

interface ClientDynamicWidgetsProps {
  topologySnapshot: TopologySnapshot;
  recentActivity: ActivityEvent[];
}

/**
 * 客户端动态加载包装组件
 * 将需要 ssr: false 的 dynamic import 封装在客户端组件中
 * 解决 Next.js 16 不允许在 Server Component 中使用 dynamic + ssr: false 的限制
 */
export default function ClientDynamicWidgets({
  topologySnapshot,
  recentActivity,
}: ClientDynamicWidgetsProps) {
  return (
    <>
      {/* 粒子背景动效 */}
      <ParticleBackground />
      {/* 3D 迷你拓扑 + 活动流 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 px-6 pb-8">
        <div className="lg:col-span-2">
          <MiniTopology3D snapshot={topologySnapshot} />
        </div>
        <div className="lg:col-span-1">
          <ActivityFeed initialEvents={recentActivity} />
        </div>
      </section>
    </>
  );
}
