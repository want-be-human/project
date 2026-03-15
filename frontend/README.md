# 网特威恩 SOC 的前端界面
## 发展
1. 安装依赖项：
``bash
npm install
```2. 启动开发服务器：
``bash
npm run dev
```3. 打开 [http://localhost:3000](http://localhost:3000) 。
## 模拟模式与真实模式
要切换到模拟（独立运行）模式和真实（后端连接）模式，请设置 NEXT_PUBLIC_API_MODE 环境变量。
- **模拟模式**（默认设置）：
``bash
NEXT_PUBLIC_API_MODE=mock npm run dev
``  在此模式下，应用程序会从 ../../contract/samples/*.json 文件中读取数据。
- **实模式**：
`ash
NEXT_PUBLIC_API_MODE=real NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
``n 在此模式下，应用程序会将请求代理给后端。
## 结构
- 源代码/应用程序：路由（Next.js 应用程序路由器）
- 源代码/组件：用户界面组件
- 源代码/库/API：API 客户端层（模拟/真实切换）