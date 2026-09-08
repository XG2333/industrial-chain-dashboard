import { useEffect, useState } from 'react';

export interface ChartVisualTheme {
  background: string;
  text: string;
  secondaryText: string;
  axisLine: string;
  splitLine: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  legendText: string;
  palette: string[];
  emphasis: string;
}

const LIGHT_THEME: ChartVisualTheme = {
  background: '#ffffff',
  text: '#0f172a',
  secondaryText: '#64748b',
  axisLine: '#e2e8f0',
  splitLine: '#f1f5f9',
  tooltipBg: '#ffffff',
  tooltipBorder: '#e2e8f0',
  tooltipText: '#334155',
  legendText: '#475569',
  // shadcn chart 色板（浅色 chart-1..8）
  palette: ['#e76e50', '#2a9d90', '#274754', '#e8c468', '#f4a462', '#8b5cf6', '#2563eb', '#10b981'],
  emphasis: '#2563eb',
};

const DARK_THEME: ChartVisualTheme = {
  background: '#1e293b',
  text: '#f8fafc',
  secondaryText: '#94a3b8',
  axisLine: '#334155',
  splitLine: '#334155',
  tooltipBg: '#1e293b',
  tooltipBorder: '#475569',
  tooltipText: '#e2e8f0',
  legendText: '#cbd5e1',
  // shadcn chart 色板（深色 chart-1..8）
  palette: ['#6488f0', '#4cc9a2', '#f6b85e', '#b48cf8', '#f27d72', '#60a5fa', '#a3e635', '#34d399'],
  emphasis: '#60a5fa',
};

// 图表字号统一来源（2026-09-02：图卡与速览/仓单大图口径一致）
export const CHART_FONTS = {
  tooltip: 11,
  axis: 10,
  legend: 10,
};

export function getChartTheme(dark: boolean): ChartVisualTheme {
  return dark ? DARK_THEME : LIGHT_THEME;
}

export function useChartTheme(): ChartVisualTheme {
  const [dark, setDark] = useState(
    () => typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
  );

  useEffect(() => {
    const root = document.documentElement;
    const update = () => setDark(root.classList.contains('dark'));
    update();
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return getChartTheme(dark);
}
