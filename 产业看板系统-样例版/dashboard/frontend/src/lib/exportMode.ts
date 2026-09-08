// 导出模式: URL 带 ?export=1 时进入"完整页面导出"模式 ——
// 图表跳过 IntersectionObserver 懒加载全量渲染、打印样式隐藏悬浮/按钮/展开滚动容器,
// 配合浏览器 打印→另存为PDF(或 Chrome --headless --print-to-pdf) 得到完整长页 PDF。
export function isExportMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).has("export");
  } catch {
    return false;
  }
}

export function exportUrl(active = true): string {
  const url = new URL(window.location.href);
  if (active) url.searchParams.set("export", "1");
  else url.searchParams.delete("export");
  return url.toString();
}
