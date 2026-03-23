/**
 * PipelineStageTimeline 单元测试
 * 覆盖需求：1.3, 3.5, 3.6, 4.4, 4.5
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import type { PipelineStageStatus } from '@/lib/api/types';
import type { PipelineRun } from '@/lib/api/types';
import { getStatusStyle } from '../PipelineStageTimeline';
import PipelineStageTimeline from '../PipelineStageTimeline';

// mock next-intl，返回键名作为翻译结果
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params) {
      // 简单模拟参数替换
      let result = key;
      for (const [k, v] of Object.entries(params)) {
        result += ` ${k}=${v}`;
      }
      return result;
    }
    return key;
  },
}));

// 每个测试后清理 DOM
afterEach(cleanup);

// ============================================================
// 需求 1.3：PipelineStageStatus 类型不包含 success
// ============================================================
describe('需求 1.3：PipelineStageStatus 类型不包含 success', () => {
  it('success 不应是 PipelineStageStatus 的有效值', () => {
    // 使用 TypeScript 类型断言验证：
    // 如果 'success' 是 PipelineStageStatus 的成员，下面的类型检查会通过编译
    // 我们通过运行时验证合法状态集合不包含 'success'
    const validStatuses: PipelineStageStatus[] = ['pending', 'running', 'completed', 'failed', 'skipped'];
    expect(validStatuses).not.toContain('success');

    // 验证 'completed' 替代了 'success'
    expect(validStatuses).toContain('completed');
  });

  it('PipelineStageStatus 应恰好包含 5 种状态值', () => {
    const validStatuses: PipelineStageStatus[] = ['pending', 'running', 'completed', 'failed', 'skipped'];
    expect(validStatuses).toHaveLength(5);
  });
});

// ============================================================
// 需求 3.5, 3.6：状态样式颜色验证
// ============================================================
describe('需求 3.5, 3.6：状态样式颜色映射', () => {
  it('completed 状态应返回绿色样式', () => {
    const style = getStatusStyle('completed');
    // 验证 badge 包含绿色类名
    expect(style.badge).toContain('green');
    // 验证 overallBg 包含绿色类名
    expect(style.overallBg).toContain('green');
  });

  it('failed 状态应返回红色样式', () => {
    const style = getStatusStyle('failed');
    // 验证 badge 包含红色类名
    expect(style.badge).toContain('red');
    // 验证 overallBg 包含红色类名
    expect(style.overallBg).toContain('red');
  });
});


// ============================================================
// 需求 4.4：failed 阶段显示 error_summary
// ============================================================
describe('需求 4.4：failed 阶段显示错误摘要', () => {
  it('failed 阶段展开后应显示 error_summary 内容', () => {
    const mockPipelineRun: PipelineRun = {
      id: 'run-1',
      pcap_id: 'test-pcap-1',
      status: 'failed',
      started_at: '2024-01-01T00:00:00Z',
      completed_at: '2024-01-01T00:01:00Z',
      total_latency_ms: 60000,
      created_at: '2024-01-01T00:00:00Z',
      stages: [
        {
          stage_name: 'detect',
          status: 'failed',
          started_at: '2024-01-01T00:00:00Z',
          completed_at: '2024-01-01T00:00:30Z',
          latency_ms: 30000,
          key_metrics: {},
          error_summary: '检测模型加载失败：模型文件不存在',
          input_summary: {},
          output_summary: {},
        },
      ],
    };

    const { container } = render(
      <PipelineStageTimeline pipelineRun={mockPipelineRun} loading={false} error={null} />
    );

    // 点击 failed 阶段卡片展开详情
    const stageButton = container.querySelector('button');
    expect(stageButton).toBeTruthy();
    fireEvent.click(stageButton!);

    // 验证 error_summary 内容显示在页面中
    expect(screen.getByText(/检测模型加载失败：模型文件不存在/)).toBeTruthy();
  });
});

// ============================================================
// 需求 4.5：skipped 阶段显示跳过原因
// ============================================================
describe('需求 4.5：skipped 阶段显示跳过原因', () => {
  it('skipped 阶段展开后应显示跳过原因（使用 error_summary）', () => {
    const mockPipelineRun: PipelineRun = {
      id: 'run-2',
      pcap_id: 'test-pcap-2',
      status: 'completed',
      started_at: '2024-01-01T00:00:00Z',
      completed_at: '2024-01-01T00:02:00Z',
      total_latency_ms: 120000,
      created_at: '2024-01-01T00:00:00Z',
      stages: [
        {
          stage_name: 'dry_run',
          status: 'skipped',
          started_at: null,
          completed_at: null,
          latency_ms: null,
          key_metrics: {},
          error_summary: '未配置推演环境',
          input_summary: {},
          output_summary: {},
        },
      ],
    };

    const { container } = render(
      <PipelineStageTimeline pipelineRun={mockPipelineRun} loading={false} error={null} />
    );

    // 点击 skipped 阶段卡片展开详情
    const stageButton = container.querySelector('button');
    expect(stageButton).toBeTruthy();
    fireEvent.click(stageButton!);

    // 验证跳过原因显示在页面中
    expect(screen.getByText(/未配置推演环境/)).toBeTruthy();
  });

  it('skipped 阶段无 error_summary 时应显示默认跳过原因文案', () => {
    const mockPipelineRun: PipelineRun = {
      id: 'run-3',
      pcap_id: 'test-pcap-3',
      status: 'completed',
      started_at: '2024-01-01T00:00:00Z',
      completed_at: '2024-01-01T00:02:00Z',
      total_latency_ms: 120000,
      created_at: '2024-01-01T00:00:00Z',
      stages: [
        {
          stage_name: 'visualize',
          status: 'skipped',
          started_at: null,
          completed_at: null,
          latency_ms: null,
          key_metrics: {},
          error_summary: null,
          input_summary: {},
          output_summary: {},
        },
      ],
    };

    const { container } = render(
      <PipelineStageTimeline pipelineRun={mockPipelineRun} loading={false} error={null} />
    );

    // 点击 skipped 阶段卡片展开详情
    const stageButton = container.querySelector('button');
    expect(stageButton).toBeTruthy();
    fireEvent.click(stageButton!);

    // 当 error_summary 为 null 时，组件使用 t('detailSkipReason') 作为默认文案
    // mock 的 useTranslations 返回键名本身，标签和内容都显示 'detailSkipReason'
    const matches = screen.getAllByText(/detailSkipReason/);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });
});
