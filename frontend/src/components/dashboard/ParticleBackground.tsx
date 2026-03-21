'use client';

import { useEffect, useMemo, useState } from 'react';
import Particles, { initParticlesEngine } from '@tsparticles/react';
import { loadSlim } from '@tsparticles/slim';
import type { ISourceOptions } from '@tsparticles/engine';

/**
 * 检测设备性能能力级别
 * - prefers-reduced-motion: reduce 时返回 'none'（不渲染粒子）
 * - CPU 核心数 ≤ 2 或设备像素比 < 1.5 时返回 'low'（低配模式）
 * - 否则返回 'high'（完整效果）
 */
export function getDeviceCapability(): 'high' | 'low' | 'none' {
  // prefers-reduced-motion 时完全不渲染
  if (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    return 'none';
  }
  // hardwareConcurrency 不可用时回退到默认值 4
  const cores = navigator.hardwareConcurrency ?? 4;
  const dpr = window.devicePixelRatio ?? 1;
  if (cores <= 2 || dpr < 1.5) return 'low';
  return 'high';
}

/**
 * 根据设备能力级别返回粒子配置
 * - 'high'：35 粒子、连线启用、fpsLimit 30
 * - 'low'：15 粒子、连线关闭、fpsLimit 30
 */
export function getParticleConfig(capability: 'high' | 'low'): ISourceOptions {
  const isLow = capability === 'low';
  return {
    fullScreen: false,
    fpsLimit: 30,
    particles: {
      number: {
        value: isLow ? 15 : 35,
        density: { enable: true },
      },
      color: {
        value: ['#06b6d4', '#3b82f6'],
      },
      opacity: {
        value: { min: 0.1, max: 0.4 },
      },
      size: {
        value: { min: 1, max: 3 },
      },
      move: {
        enable: true,
        speed: 0.5,
        direction: 'none',
        outModes: {
          default: 'out',
        },
      },
      links: {
        enable: !isLow,
        color: '#06b6d4',
        opacity: 0.1,
        distance: 150,
        width: 0.5,
      },
    },
    detectRetina: true,
  };
}

/**
 * 粒子背景组件
 * 使用 @tsparticles/react + @tsparticles/slim 实现低密度粒子背景动效
 * 支持设备性能降级：低端设备减少粒子、关闭连线；reduced-motion 时不渲染
 * 使用 position: fixed + pointer-events: none 确保不阻挡页面交互
 */
export default function ParticleBackground() {
  // 引擎初始化状态
  const [ready, setReady] = useState(false);

  // 检测设备能力级别
  const capability = useMemo(() => getDeviceCapability(), []);

  // 初始化粒子引擎，加载 slim 预设
  useEffect(() => {
    // reduced-motion 时跳过引擎初始化
    if (capability === 'none') return;

    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      setReady(true);
    });
  }, [capability]);

  // 根据能力级别生成粒子配置
  const options: ISourceOptions = useMemo(
    () => (capability === 'none' ? {} : getParticleConfig(capability)),
    [capability],
  );

  // reduced-motion 时不渲染粒子背景
  if (capability === 'none') return null;

  if (!ready) return null;

  return (
    <div
      className="fixed inset-0 z-0 pointer-events-none"
      aria-hidden="true"
    >
      <Particles
        id="particle-background"
        options={options}
        className="h-full w-full"
      />
    </div>
  );
}
