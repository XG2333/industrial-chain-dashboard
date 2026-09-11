import { createRoot } from 'react-dom/client';
import { ThemeProvider } from 'flowbite-react';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App';
import { Router } from './router';
import { flowbiteTheme } from './theme/flowbiteTheme';
import { initPrintChartResize } from './lib/printCharts';
import './index.css';
import './theme/dashboardTokens.css';
import './i18n';

// 打印/导出 PDF 前强制全部 echarts 实例 resize(防 canvas 与容器错位)
initPrintChartResize();

// file:// 直开(离线单文件快照): history API 在 file 下不可用,
// 用 MemoryRouter 固定进入 /battery(碳酸锂总览页);http(s) 部署行为不变。
// App 自带 BrowserRouter, 此处 file 分支直接挂载内部 Router 避免双重路由。
const isFileProtocol = typeof location !== 'undefined' && location.protocol === 'file:';
const RouterImpl = isFileProtocol ? (
  <MemoryRouter initialEntries={['/battery']}>
    <Router />
  </MemoryRouter>
) : (
  <App />
);

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={flowbiteTheme}>
    {RouterImpl}
  </ThemeProvider>,
);
