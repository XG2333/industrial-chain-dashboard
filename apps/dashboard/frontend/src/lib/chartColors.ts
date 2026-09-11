// 年份颜色对齐 shadcn chart 色板；2026/2027 不再重复红色
const YEAR_COLORS: Record<string, string> = {
  "2020": "#94a3b8",
  "2021": "#64748b",
  "2022": "#e76e50",
  "2023": "#2a9d90",
  "2024": "#274754",
  "2025": "#e8c468",
  "2026": "#f4a462",
  "2027": "#8b5cf6",
};

const FALLBACK_COLORS = [
  "#e76e50",
  "#2a9d90",
  "#274754",
  "#e8c468",
  "#f4a462",
  "#8b5cf6",
  "#2563eb",
  "#10b981",
  "#64748b",
];

export function getYearColor(year: string, index = 0): string {
  return YEAR_COLORS[year] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}
