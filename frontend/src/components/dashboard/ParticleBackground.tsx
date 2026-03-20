'use client';

import { useEffect, useMemo, useState } from 'react';
import Particles, { initParticlesEngine } from '@tsparticles/react';
import { loadSlim } from '@tsparticles/slim';
import type { ISourceOptions } from '@tsparticles/engine';

/**
 * 粒子背景组件
 * 使用 @tsparticles/react + @tsparticles/slim 实现低密度粒子背景动效
 * 粒子密度保持低水平，不影响交互性能
 * 使用 position: fixed + pointer-events: none 确保不阻挡页面交互
 */
export default function ParticleBackground() {
  // 引擎初始化状态
  const [ready, setReady] = useState(false);

  // 初始化粒子引擎，加载 slim 预设
  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      setReady(true);
    });
  }, []);

  // 粒子配置：低密度、小尺寸、慢速移动、青蓝色系
  const options: ISourceOptions = useMemo(
    () => ({
      fullScreen: false,
      fpsLimit: 30,
      particles: {
        number: {
          value: 35,
          density: {
            enable: true,
          },
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
          enable: true,
          color: '#06b6d4',
          opacity: 0.1,
          distance: 150,
          width: 0.5,
        },
      },
      detectRetina: true,
    }),
    [],
  );

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
