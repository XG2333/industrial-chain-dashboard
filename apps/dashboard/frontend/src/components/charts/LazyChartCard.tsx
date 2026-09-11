import { useEffect, useRef, useState } from "react";
import type { ChartData, ChartMeta } from "@/lib/chartTypes";
import { loadChartData } from "@/lib/excelCache";
import { simplifyIndicatorName } from "@/lib/indicatorName";
import { isExportMode } from "@/lib/exportMode";
import { SeasonalChart } from "./SeasonalChart";
import { YearlyChart } from "./YearlyChart";

interface LazyChartCardProps {
  chart: ChartMeta;
}

// 相邻数据点平均间隔天数：目录 freq 可能错标（月度/日度被标成 yearly），
// 用数据自身间隔兜底——≥300 天才算真年度（柱状年份图）；否则交给
// SeasonalChart 按实际间隔渲染（日/周/月轴）。<2 点视为年度（无间隔信息）。
function avgGapDays(pts: { date: string }[]): number {
  if (pts.length < 2) return Infinity;
  const sorted = [...pts].map((p) => Date.parse(p.date)).sort((a, b) => a - b);
  let total = 0;
  for (let i = 1; i < sorted.length; i++) total += (sorted[i] - sorted[i - 1]) / 86400000;
  return total / (sorted.length - 1);
}

export function LazyChartCard({ chart }: LazyChartCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [series, setSeries] = useState<ChartData | null>(null);
  const [visible, setVisible] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const node = containerRef.current;
    // 导出模式(?export=1): 跳过懒加载, 全部图表立即取数渲染(供整页 PDF)
    if (!node || typeof IntersectionObserver === "undefined" || isExportMode()) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "600px 0px", threshold: 0.01 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || series || failed) return;
    let cancelled = false;
    loadChartData([chart.id])
      .then((items) => {
        if (!cancelled && items[0]) {
          setSeries(items[0]);
        } else if (!cancelled) {
          setFailed(true);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [chart.id, failed, series, visible]);

  return (
    <div
      ref={containerRef}
      className="flex flex-col rounded-xl border border-border bg-card pl-1 pr-3 pt-3 pb-3 scroll-mt-28 shadow-sm transition-shadow hover:shadow-md"
      id={chart.id}
    >
      <div className="mb-1">
        {/* 指标图标题与速览表一致：简化名称(去来源前缀/指标词/频率后缀)；悬停可看原标题 */}
        <p className="break-words text-sm font-bold whitespace-normal" title={chart.title}>
          {simplifyIndicatorName(chart.title)}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          单位：{chart.unit}
        </p>
      </div>
      {/* 图表区长高比统一（1.73:1，与五张图一行一致）：1/2/3/4 张行的图按宽度等比放大 */}
      <div style={{ aspectRatio: "1.73", width: "100%" }}>
        {failed ? (
          <div className="flex h-full items-center justify-center rounded bg-muted/40 text-xs text-muted-foreground">
            数据加载失败
          </div>
        ) : series ? (
          // 真年度（间隔 ≥300 天）才用年份柱状图；错标 yearly 的月度/日度数据
          // 交给 SeasonalChart 按实际间隔渲染（修复 x 轴同年重复）
          chart.freq === "yearly" && avgGapDays(series.data) >= 300 ? (
            <YearlyChart title={chart.title} unit={chart.unit} data={series.data} />
          ) : (
            <SeasonalChart
              title={chart.title}
              unit={chart.unit}
              data={series.data}
              freq={chart.freq}
              keepExtremes={
                chart.sub === "基差" ||
                chart.sub === "月差" ||
                chart.title.includes("期现价差") ||
                chart.title.includes("基差") ||
                chart.title.includes("月差") ||
                chart.title.includes("价差")
              }
            />
          )
        ) : (
          <div className="h-full w-full animate-pulse rounded bg-slate-100" />
        )}
      </div>
    </div>
  );
}
