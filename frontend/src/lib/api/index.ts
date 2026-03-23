// 导出类型
export * from './types';

import { realApi } from './real';

// 导出 API 客户端（始终使用真实后端）
export const api = realApi;
