'use client';

import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Error boundary that silently swallows the "removeChild" DOM error
 * caused by React ↔ Three.js (R3F) cleanup race during navigation.
 * On any other error it re-throws so the nearest Next.js error page kicks in.
 */
export default class CanvasErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(_error: Error): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    // Silently ignore the Three.js / React DOM cleanup race
    if (
      error?.message?.includes('removeChild') ||
      error?.name === 'NotFoundError'
    ) {
      // expected during page transitions – nothing to do
      return;
    }
    // Re-throw anything unexpected so it doesn't get swallowed
    throw error;
  }

  render() {
    if (this.state.hasError) {
      // Return nothing – the user is navigating away anyway
      return null;
    }
    return this.props.children;
  }
}
