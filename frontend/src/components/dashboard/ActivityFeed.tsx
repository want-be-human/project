'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { ActivityEvent } from '@/lib/api/types';
import { api } from '@/lib/api';
import { wsClient } from '@/lib/ws';
import {
  PCAP_PROCESS_DONE,
  ALERT_CREATED,
  TWIN_DRYRUN_CREATED,
} from '@/lib/events';

// ==================== 新事件追踪器 — 导出以便属性测试使用 ====================

/**
 * 创建新事件追踪器，用于追踪 WebSocket 推送的新事件 ID
 * 初始事件列表中的事件不会被追踪，仅 WebSocket 新增的事件会被追踪
 * 动画完成后通过 remove() 移除追踪
 */
export function createNewEventTracker() {
  const ids = new Set<string>();
  return {
    /** 追踪新事件 ID */
    track(id: string) { ids.add(id); },
    /** 检查是否为新事件 */
    isNew(id: string) { return ids.has(id); },
    /** 动画完成后移除 */
    remove(id: string) { ids.delete(id); },
    /** 获取当前追踪的 ID 集合（用于测试） */
    getIds() { return new Set(ids); },
    /** 获取追踪数量 */
    size() { return ids.size; },
  };
}

// ==================== 事件类型图标映射 ====================
const EVENT_ICONS: Record<string, string> = {
  pcap: '📦',
  pipeline: '⚙️',
  alert: '🔔',
  dryrun: '🧪',
  scenario: '🎯',
};

/** 未知 entity_type 时的默认图标 */
const DEFAULT_EVENT_ICON = '📋';

// ==================== 事件导航 URL 生成 ====================
/**
 * 根据事件类型和 ID 生成导航 URL
 * 导出以便属性测试使用
 */
export function getEventUrl(type: ActivityEvent['type'], id: string): string {
  switch (type) {
    case 'pcap':
      return '/pcaps';
    case 'alert':
      return `/alerts/${id}`;
    case 'pipeline':
      return '/pcaps';
    case 'dryrun':
      return '/alerts';
    case 'scenario':
      return '/scenarios';
  }
}

// ==================== i18n 摘要渲染逻辑 ====================

/**
 * 根据事件的 entity_type 和 kind 生成 i18n 翻译键
 * 格式：activitySummary_{entity_type}_{kind}
 * 导出以便属性测试使用
 */
export function getActivityI18nKey(entityType: string, kind: string): string {
  return `activitySummary_${entityType}_${kind}`;
}

/**
 * 解析事件导航 URL，优先使用后端返回的 href，回退到 getEventUrl
 * 导出以便属性测试使用
 */
export function resolveEventUrl(ev: ActivityEvent): string {
  if (ev.href) return ev.href;
  // 未知 entity_type 时回退到 /alerts
  const knownTypes: string[] = ['pcap', 'pipeline', 'alert', 'dryrun', 'scenario'];
  if (!knownTypes.includes(ev.type)) return '/alerts';
  return getEventUrl(ev.type, ev.entity_id);
}

// ==================== 相对时间格式化 ====================

/**
 * 将 ISO8601 时间字符串格式化为相对时间
 * 使用 i18n 翻译键
 */
function formatRelativeTime(
  iso: string,
  t: ReturnType<typeof useTranslations>,
): string {
  try {
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diffMs = now - then;
    if (diffMs < 0) return t('activityTimeJustNow');

    const minutes = Math.floor(diffMs / 60_000);
    if (minutes < 1) return t('activityTimeJustNow');
    if (minutes < 60) return t('activityTimeMinutesAgo', { minutes });

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('activityTimeHoursAgo', { hours });

    const days = Math.floor(hours / 24);
    return t('activityTimeDaysAgo', { days });
  } catch {
    return '--';
  }
}

// ==================== WebSocket 事件类型到 ActivityEvent 类型的映射 ====================
const WS_EVENT_MAP: Record<string, ActivityEvent['type']> = {
  [PCAP_PROCESS_DONE]: 'pcap',
  [ALERT_CREATED]: 'alert',
  [TWIN_DRYRUN_CREATED]: 'dryrun',
};

// ==================== 组件 Props ====================
interface ActivityFeedProps {
  initialEvents: ActivityEvent[];
}

/**
 * 活动流组件
 * 展示最近事件列表，支持 WebSocket 实时增量刷新
 * WebSocket 不可用时回退到 30s 轮询
 */
export default function ActivityFeed({ initialEvents }: ActivityFeedProps) {
  const t = useTranslations('dashboard');
  const router = useRouter();
  const [events, setEvents] = useState<ActivityEvent[]>(initialEvents);

  // 新事件追踪：仅追踪 WebSocket 推送的新事件，初始事件不触发入场动画
  const newEventTrackerRef = useRef(createNewEventTracker());
  const [, forceUpdate] = useState(0);

  /**
   * 渲染事件摘要，实现三级降级策略：
   * 1. 尝试 t(activitySummary_{entity_type}_{kind}, payload)
   * 2. 若键不存在 → t('activityFallbackSummary', { type, kind })
   * 3. 若降级键也失败 → summary 标识符原文
   */
  const renderSummary = useCallback(
    (ev: ActivityEvent): string => {
      try {
        const i18nKey = getActivityI18nKey(ev.entity_type, ev.kind);
        if (t.has(i18nKey)) {
          return t(i18nKey, ev.payload);
        }
        if (t.has('activityFallbackSummary')) {
          return t('activityFallbackSummary', { type: ev.entity_type, kind: ev.kind });
        }
        return ev.summary;
      } catch {
        return ev.summary;
      }
    },
    [t],
  );

  /** 获取事件类型的翻译标签 */
  const getTypeLabel = useCallback(
    (type: ActivityEvent['type']): string => {
      const map: Record<ActivityEvent['type'], string> = {
        pcap: t('activityTypePcap'),
        pipeline: t('activityTypePipeline'),
        alert: t('activityTypeAlert'),
        dryrun: t('activityTypeDryrun'),
        scenario: t('activityTypeScenario'),
      };
      return map[type] ?? type;
    },
    [t],
  );

  // 通过统一 wsClient 订阅事件（替代原有 new WebSocket 直连 + 轮询回退）
  useEffect(() => {
    const unsubs = Object.entries(WS_EVENT_MAP).map(([wsEvent, activityType]) =>
      wsClient.onEvent(wsEvent, (data: any) => {
        const id = data?.pcap_id ?? data?.alert_id ?? data?.dry_run_id ?? crypto.randomUUID();
        const newEvent: ActivityEvent = {
          id,
          type: activityType as ActivityEvent['type'],
          kind: data?.kind ?? 'created',
          entity_type: data?.entity_type ?? activityType,
          entity_id: data?.entity_id ?? id,
          summary: data?.summary ?? wsEvent,
          payload: data ?? {},
          href: data?.href ?? null,
          detail: data ?? {},
          created_at: new Date().toISOString(),
        };
        newEventTrackerRef.current.track(newEvent.id);
        setEvents((prev) => [newEvent, ...prev].slice(0, 20));
      })
    );
    return () => unsubs.forEach(u => u());
  }, []);

  return (
    <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-5 backdrop-blur-sm hover:border-cyan-500/40 transition-colors h-full flex flex-col">
      {/* 标题 + 事件计数 badge（空列表时隐藏） */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-200">
          {t('activityTitle')}
        </h3>
        {events.length > 0 && (
          <span
            data-testid="activity-count-badge"
            className="text-xs font-medium text-cyan-400 bg-cyan-400/10 rounded-full px-2 py-0.5"
          >
            {events.length}
          </span>
        )}
      </div>

      {/* 事件列表 */}
      <ul className="space-y-2 flex-1 overflow-y-auto pr-1">
        {events.length === 0 && (
          <li className="text-xs text-gray-500 text-center py-4">
            {t('activityEmptyState')}
          </li>
        )}
        {events.map((ev) => {
          const eventKey = `${ev.type}-${ev.id}`;
          const isNew = newEventTrackerRef.current.isNew(ev.id);
          return (
            <li
              key={eventKey}
              className={`flex items-start gap-2 p-2 rounded-lg hover:bg-gray-800/60 cursor-pointer transition-colors${isNew ? ' animate-slide-in' : ''}`}
              onClick={() => router.push(resolveEventUrl(ev))}
              onAnimationEnd={() => {
                // 动画完成后从追踪集合中移除，触发重渲染以移除动画类
                if (newEventTrackerRef.current.isNew(ev.id)) {
                  newEventTrackerRef.current.remove(ev.id);
                  forceUpdate((n) => n + 1);
                }
              }}
            >
              {/* 类型图标（未知类型回退到默认图标） */}
              <span className="text-base shrink-0 mt-0.5" aria-hidden="true">
                {EVENT_ICONS[ev.type] ?? DEFAULT_EVENT_ICON}
              </span>

              {/* 事件内容 */}
              <div className="flex-1 min-w-0">
                <span className="text-xs text-cyan-400 font-medium">
                  {getTypeLabel(ev.type)}
                </span>
                <p className="text-xs text-gray-300 truncate">
                  {renderSummary(ev)}
                </p>
              </div>

              {/* 时间 */}
              <span className="text-[10px] text-gray-500 shrink-0 mt-0.5">
                {formatRelativeTime(ev.created_at, t)}
              </span>
            </li>
          );
        })}
      </ul>

      {/* 查看全部活动链接 */}
      <div className="mt-3 pt-3 border-t border-gray-700/50 text-center">
        <button
          type="button"
          onClick={() => router.push('/alerts')}
          className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          {t('activityViewAll')}
        </button>
      </div>
    </div>
  );
}
