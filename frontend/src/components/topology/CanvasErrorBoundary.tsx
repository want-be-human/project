'use client';

import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * 错误边界：静默吞掉页面切换期间 React ↔ Three.js (R3F) 清理竞争
 * 导致的 "removeChild" DOM 异常。
 * 其他异常会继续抛出，由最近的 Next.js 错误页接管。
 */
export default class CanvasErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(_error: Error): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    // 静默忽略 Three.js / React DOM 清理竞争导致的预期异常
    if (
      error?.message?.includes('removeChild') ||
      error?.name === 'NotFoundError'
    ) {
      // 页面切换时的预期情况，无需处理
      return;
    }
    // 非预期异常继续抛出，避免被吞掉
    throw error;
  }

  render() {
    if (this.state.hasError) {
      // 直接返回空内容，用户通常正在离开当前页面
      return null;
    }
    return this.props.children;
  }
}
