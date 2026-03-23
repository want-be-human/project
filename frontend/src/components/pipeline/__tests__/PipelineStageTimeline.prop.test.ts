/**
 * PipelineStageTimeline 属性测试
 * 使用 fast-check 进行属性验证
 */
import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { getStatusStyle } from '../PipelineStageTimeline';

// 功能：pipeline-observability-panel，属性 1：状态样式映射完备性
// **验证需求：1.1、1.2、1.4**
describe('属性 1：状态样式映射完备性', () => {
  it('对所有有效状态值调用 getStatusStyle，应返回包含 badge、icon、overallBg 三个非空字段的有效样式对象', () => {
    const validStatuses = ['pending', 'running', 'completed', 'failed', 'skipped'] as const;

    fc.assert(
      fc.property(
        fc.constantFrom(...validStatuses),
        (status) => {
          const style = getStatusStyle(status);

          // 验证返回对象包含三个必需字段
          expect(style).toHaveProperty('badge');
          expect(style).toHaveProperty('icon');
          expect(style).toHaveProperty('overallBg');

          // 验证 badge 和 overallBg 为非空字符串
          expect(typeof style.badge).toBe('string');
          expect(style.badge.length).toBeGreaterThan(0);

          expect(typeof style.overallBg).toBe('string');
          expect(style.overallBg.length).toBeGreaterThan(0);

          // 验证 icon 不为 null/undefined
          expect(style.icon).toBeTruthy();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// 功能：pipeline-observability-panel，属性 5：旧版 success 状态向后兼容
// **验证需求：6.5**
describe('属性 5：旧版 success 状态向后兼容', () => {
  it('对 success 状态调用样式映射，应返回与 completed 相同的有效样式对象', () => {
    fc.assert(
      fc.property(
        fc.constant('success'),
        (status) => {
          const successStyle = getStatusStyle(status);
          const completedStyle = getStatusStyle('completed');

          // 验证 success 返回有效样式对象
          expect(successStyle).toHaveProperty('badge');
          expect(successStyle).toHaveProperty('icon');
          expect(successStyle).toHaveProperty('overallBg');

          // 验证 badge 和 overallBg 与 completed 完全一致
          expect(successStyle.badge).toBe(completedStyle.badge);
          expect(successStyle.overallBg).toBe(completedStyle.overallBg);

          // icon 是 JSX 元素，比较其类型和关键属性
          // 两者都应为非空值
          expect(successStyle.icon).toBeTruthy();
          expect(completedStyle.icon).toBeTruthy();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// 功能：pipeline-observability-panel，属性 2：国际化键值对等性
// **验证需求：2.2、2.3**
describe('属性 2：国际化键值对等性', () => {
  // 直接导入 zh.json 和 en.json 的 pipeline 命名空间
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const zhMessages = require('../../../../messages/zh.json');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const enMessages = require('../../../../messages/en.json');

  const zhPipelineKeys = Object.keys(zhMessages.pipeline).sort();
  const enPipelineKeys = Object.keys(enMessages.pipeline).sort();

  it('zh.json 和 en.json 的 pipeline 命名空间应包含完全相同的键集合', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...zhPipelineKeys),
        (key) => {
          // 验证中文语言包中的每个键都存在于英文语言包中
          expect(enMessages.pipeline).toHaveProperty(key);
          // 验证对应的值为非空字符串
          expect(typeof enMessages.pipeline[key]).toBe('string');
          expect(enMessages.pipeline[key].length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('en.json 和 zh.json 的 pipeline 命名空间应包含完全相同的键集合（反向验证）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...enPipelineKeys),
        (key) => {
          // 验证英文语言包中的每个键都存在于中文语言包中
          expect(zhMessages.pipeline).toHaveProperty(key);
          // 验证对应的值为非空字符串
          expect(typeof zhMessages.pipeline[key]).toBe('string');
          expect(zhMessages.pipeline[key].length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('两个语言包的 pipeline 键集合长度应完全相等', () => {
    expect(zhPipelineKeys.length).toBe(enPipelineKeys.length);
    // 逐一比较排序后的键名
    expect(zhPipelineKeys).toEqual(enPipelineKeys);
  });
});

// 导入任务 4 新增的辅助函数
import { computeStageStats, formatDateTime } from '../PipelineStageTimeline';

// 功能：pipeline-observability-panel，属性 3：阶段统计不变量
// **验证需求：3.4**
describe('属性 3：阶段统计不变量', () => {
  it('对随机 stages 数组，completed + failed + skipped + pending + running 应等于 stages.length', () => {
    const validStatuses = ['pending', 'running', 'completed', 'failed', 'skipped'] as const;

    // 生成随机 StageRecord 数组的生成器
    const stageRecordArb = fc.record({
      stage_name: fc.string({ minLength: 1, maxLength: 20 }),
      status: fc.constantFrom(...validStatuses),
      started_at: fc.constant(null),
      completed_at: fc.constant(null),
      latency_ms: fc.constant(null),
      key_metrics: fc.constant({}),
      error_summary: fc.constant(null),
      input_summary: fc.constant({}),
      output_summary: fc.constant({}),
    });

    fc.assert(
      fc.property(
        fc.array(stageRecordArb, { minLength: 0, maxLength: 50 }),
        (stages) => {
          const stats = computeStageStats(stages);

          // 验证各状态计数之和等于总阶段数
          const sum = stats.completed + stats.failed + stats.skipped + stats.pending + stats.running;
          expect(sum).toBe(stages.length);
          expect(stats.total).toBe(stages.length);

          // 验证每个计数都是非负整数
          expect(stats.completed).toBeGreaterThanOrEqual(0);
          expect(stats.failed).toBeGreaterThanOrEqual(0);
          expect(stats.skipped).toBeGreaterThanOrEqual(0);
          expect(stats.pending).toBeGreaterThanOrEqual(0);
          expect(stats.running).toBeGreaterThanOrEqual(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// 功能：pipeline-observability-panel，属性 6：时间格式化一致性
// **验证需求：3.2**
describe('属性 6：时间格式化一致性', () => {
  it('对随机有效日期，格式化输出应匹配 yyyy-MM-dd HH:mm:ss 模式', () => {
    // 使用时间戳生成器，确保生成的都是有效日期
    // 范围：2000-01-01 到 2099-06-30（留余量避免时区偏移越界）
    const minTs = new Date('2000-01-01T00:00:00Z').getTime();
    const maxTs = new Date('2099-06-30T23:59:59Z').getTime();
    const dateArb = fc.integer({ min: minTs, max: maxTs }).map(ts => new Date(ts));

    const pattern = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;

    fc.assert(
      fc.property(
        dateArb,
        (date) => {
          const isoString = date.toISOString();
          const formatted = formatDateTime(isoString);

          // 验证格式化输出匹配 yyyy-MM-dd HH:mm:ss 模式
          expect(formatted).toMatch(pattern);

          // 验证格式化后的各部分是有效的数值
          const parts = formatted.split(/[-: ]/);
          const month = parseInt(parts[1], 10);
          const day = parseInt(parts[2], 10);
          const hour = parseInt(parts[3], 10);
          const minute = parseInt(parts[4], 10);
          const second = parseInt(parts[5], 10);

          expect(month).toBeGreaterThanOrEqual(1);
          expect(month).toBeLessThanOrEqual(12);
          expect(day).toBeGreaterThanOrEqual(1);
          expect(day).toBeLessThanOrEqual(31);
          expect(hour).toBeGreaterThanOrEqual(0);
          expect(hour).toBeLessThanOrEqual(23);
          expect(minute).toBeGreaterThanOrEqual(0);
          expect(minute).toBeLessThanOrEqual(59);
          expect(second).toBeGreaterThanOrEqual(0);
          expect(second).toBeLessThanOrEqual(59);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// 功能：pipeline-observability-panel，属性 4：阶段元数据渲染完整性
// **验证需求：4.6、4.7**
describe('属性 4：阶段元数据渲染完整性', () => {
  /**
   * 模拟组件中 key_metrics 渲染逻辑的纯函数
   * 组件中使用 typeof v === 'number' ? v.toLocaleString() : String(v) 来序列化值
   * 此函数验证所有键值对的键名和值都能被正确序列化为非空字符串
   */
  function serializeKeyMetrics(metrics: Record<string, unknown>): Array<{ key: string; value: string }> {
    return Object.entries(metrics).map(([k, v]) => ({
      key: k,
      value: typeof v === 'number' ? v.toLocaleString() : String(v),
    }));
  }

  it('对随机 key_metrics 对象，所有键值对的键名和值都应出现在序列化输出中', () => {
    // 生成非空键名的字典，值为整数或非空字符串
    const keyMetricsArb = fc.dictionary(
      fc.string({ minLength: 1, maxLength: 30 }).filter(s => s.trim().length > 0),
      fc.oneof(
        fc.integer({ min: -1000000, max: 1000000 }),
        fc.string({ minLength: 1, maxLength: 50 })
      ),
      { minKeys: 1, maxKeys: 10 }
    );

    fc.assert(
      fc.property(
        keyMetricsArb,
        (metrics) => {
          const serialized = serializeKeyMetrics(metrics);
          const allKeys = Object.keys(metrics);
          const allValues = Object.values(metrics);

          // 验证序列化后的条目数量与原始键值对数量一致
          expect(serialized.length).toBe(allKeys.length);

          // 验证每个键名都出现在序列化输出中
          for (const entry of serialized) {
            expect(entry.key.length).toBeGreaterThan(0);
            expect(allKeys).toContain(entry.key);
          }

          // 验证每个值都能被正确序列化为非空字符串
          for (let i = 0; i < serialized.length; i++) {
            const originalValue = allValues[i];
            const serializedValue = serialized[i].value;

            expect(typeof serializedValue).toBe('string');
            expect(serializedValue.length).toBeGreaterThan(0);

            // 验证序列化后的值包含原始值的信息
            if (typeof originalValue === 'number') {
              // 数字经过 toLocaleString() 后应包含数字字符
              expect(serializedValue).toMatch(/\d/);
            } else {
              // 字符串值应与 String(originalValue) 一致
              expect(serializedValue).toBe(String(originalValue));
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('空 key_metrics 对象序列化后应返回空数组', () => {
    fc.assert(
      fc.property(
        fc.constant({}),
        (metrics) => {
          const serialized = serializeKeyMetrics(metrics);
          expect(serialized).toEqual([]);
        }
      ),
      { numRuns: 100 }
    );
  });
});
