import { createRoot } from 'react-dom/client';
import { ThemeProvider } from 'flowbite-react';
import { App } from './App';
import { flowbiteTheme } from './theme/flowbiteTheme';
import { initPrintChartResize } from './lib/printCharts';
import './index.css';
import './theme/dashboardTokens.css';
import './i18n';

// 打印/导出 PDF 前强制全部 echarts 实例 resize(防 canvas 与容器错位)
initPrintChartResize();

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={flowbiteTheme}>
    <App />
  </ThemeProvider>,
);
