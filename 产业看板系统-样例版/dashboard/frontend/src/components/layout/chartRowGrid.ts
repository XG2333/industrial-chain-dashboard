// 图表行网格列数（按行内图数决定单图宽度）：
// 5 张 -> 1/5 页面宽；4 张 -> 1/4 页面宽；3/2/1 张 -> 1/3 页面宽。
// 注意：类名必须完整写在源码中（Tailwind JIT 扫描），禁止动态拼接。
const ROW_GRID_CLASS: Record<number, string> = {
  5: "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5",
  4: "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4",
  3: "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3",
  2: "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3",
  1: "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3",
};

export function chartRowGridClass(count: number): string {
  return ROW_GRID_CLASS[count] ?? ROW_GRID_CLASS[5];
}
