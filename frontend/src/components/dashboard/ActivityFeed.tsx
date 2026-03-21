'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { ActivityEvent } from '@/lib/api/types';
import { api } from '@/lib/api';

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

// ==================== summary 标识符到 i18n 键映射（已弃用） ====================

/**
 * 将后端返回的 summary 标识符映射到 i18n 翻译键
 * 修复后 summary 已改为上下文摘要，此映射仅作为兼容回退
 * 导出以便属性测试使用
 */
export const SUMMARY_I18N_MAP: Record<string, string> = {
  pcap_upload: 'activitySummaryPcapUpload',
  pipeline_run: 'activitySummaryPipelineRun',
  alert_created: 'activitySummaryAlertCreated',
  dryrun_executed: 'activitySummaryDryrunExecuted',
  scenario_run: 'activitySummaryScenarioRun',
};

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
  'pcap.process.done': 'pcap',
  'alert.created': 'alert',
  'twin.dryrun.created': 'dryrun',
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
  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  /** 启动 30s 轮询作为 WebSocket 回退 */
  const startPolling = useCallback(() => {
    // 避免重复启动
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      try {
        const data = await api.getDashboardSummary();
        if (data?.recent_activity) {
          setEvents(data.recent_activity);
        }
      } catch {
        // 轮询失败时静默忽略
      }
    }, 30_000);
  }, []);

  /** 停止轮询 */
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // WebSocket 连接与轮询回退逻辑
  useEffect(() => {
    let cancelled = false;

    function connectWs() {
      try {
        const ws = new WebSocket('ws://localhost:8000/ws/events');
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) return;
          // WebSocket 连接成功，停止轮询
          stopPolling();
        };

        ws.onmessage = (msg) => {
          if (cancelled) return;
          try {
            const payload = JSON.parse(msg.data);
            const eventType = WS_EVENT_MAP[payload?.type];
            if (!eventType) return;

            // 构造新的活动事件（兼容新字段，提供默认值）
            const id = payload.data?.id ?? crypto.randomUUID();
            const newEvent: ActivityEvent = {
              id,
              type: eventType,
              kind: payload.data?.kind ?? 'unknown',
              entity_type: payload.data?.entity_type ?? eventType,
              entity_id: payload.data?.entity_id ?? id,
              summary: payload.data?.summary ?? payload.type,
              payload: payload.data?.payload ?? {},
              href: payload.data?.href ?? null,
              detail: payload.data ?? {},
              created_at: new Date().toISOString(),
            };

            // 添加到列表顶部，保持最多 20 条
            setEvents((prev) => [newEvent, ...prev].slice(0, 20));
          } catch {
            // 解析失败时忽略
          }
        };

        ws.onclose = () => {
          if (cancelled) return;
          wsRef.current = null;
          // WebSocket 断开，回退到轮询
          startPolling();
        };

        ws.onerror = () => {
          // 触发 onclose，由 onclose 处理回退
          ws.close();
        };
      } catch {
        // WebSocket 构造失败，直接启动轮询
        if (!cancelled) startPolling();
      }
    }

    connectWs();

    return () => {
      cancelled = true;
      wsRef.current?.close();
      wsRef.current = null;
      stopPolling();
    };
  }, [startPolling, stopPolling]);

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
        {events.map((ev) => (
          <li
            key={`${ev.type}-${ev.id}`}
            className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-800/60 cursor-pointer transition-colors"
            onClick={() => router.push(resolveEventUrl(ev))}
          >
            {/* 类型图标（未知类型回退到默认图标） */}
            <span className="text-base shrink-0 mt-0.5" aria-hidden>
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
        ))}
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
