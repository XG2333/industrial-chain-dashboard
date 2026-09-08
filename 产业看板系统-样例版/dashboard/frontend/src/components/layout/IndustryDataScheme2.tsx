import { LazyChartCard } from "@/components/charts/LazyChartCard";
import type { ChartMeta } from "@/lib/chartTypes";
import { groupChartRows } from "@/lib/chartGrouping";
import type { IndustryGroup } from "@/lib/industryGroups";
import { productLabelOf, subDisplayName } from "@/lib/industryGroups";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { IndicatorSummaryTable } from "@/components/dashboard/IndicatorSummaryTable";
import { SectorQuickAnalysis } from "@/components/dashboard/SectorQuickAnalysis";
import { chartRowGridClass } from "./chartRowGrid";

interface IndustryDataScheme2Props {
  excelCharts: ChartMeta[];
  fetchingExcel: boolean;
  industryGroups: IndustryGroup[];
  // 板块开头指标速览表（仅总览显示）
  showIndicatorTable?: boolean;
}

export function IndustryDataScheme2({
  excelCharts,
  fetchingExcel,
  industryGroups,
  showIndicatorTable = false,
}: IndustryDataScheme2Props) {
  return (
    <>
      {!fetchingExcel && excelCharts.length === 0 && (
        <EmptyState message="暂无行业数据" />
      )}
      {fetchingExcel && (
        <EmptyState message="正在读取 Excel 数据…" />
      )}
      {industryGroups.length > 0 && (
        <>
          <div className="space-y-4 p-4">
            {industryGroups.map((group, groupIdx) => (
              <div
                key={group.major}
                id={`industry-${groupIdx}`}
                className="mt-6 scroll-mt-28 first:mt-0"
              >
                <div className="flex items-baseline gap-2 border-b border-border pb-2">
                  {/* 板块序号徽标：长列表秩序感 + 与浮动导航定位呼应 */}
                  <span className="select-none rounded-md bg-slate-200 px-1.5 py-0.5 text-xs font-bold tabular-nums text-slate-600">
                    {String(groupIdx + 1).padStart(2, "0")}
                  </span>
                  <h3 className="text-2xl font-extrabold text-foreground">{group.major}</h3>
                </div>
                {showIndicatorTable && (
                  <>
                    <div className="pt-3">
                      <IndicatorSummaryTable charts={group.subs.flatMap((s) => s.charts)} />
                    </div>
                    {/* 板块速评：基于上方指标速览生成 AI 点评（速览表与具体指标图之间） */}
                    <SectorQuickAnalysis
                      sectorName={group.major}
                      charts={group.subs.flatMap((s) => s.charts)}
                    />
                  </>
                )}
                {group.subs.map((sub, subIdx) => (
                  <div
                    key={sub.sub}
                    id={`industry-${groupIdx}-${subIdx}`}
                    className="mt-3 scroll-mt-28"
                  >
                    {/* 图区子类标题降为 15px：板块(24) > 卡标题(18) > 图组(15) > 行标签(14) */}
                    <h4 className="mb-2 pl-3 text-[15px] font-bold text-slate-600">
                      {subDisplayName(sub.title ?? sub.sub)}
                    </h4>
                    {(() => {
                      // 行产品标题：同一产品行显示该产品名；一行含多个产品时并列写在一起；
                      // 连续相同标题只显示首个（按子类重置），避免每行都重复标题
                      const rows = groupChartRows(sub.charts);
                      const rowLabels = rows.map((row) => [...new Set(
                        row.map(c => productLabelOf(c.title, c.freq)).filter((l): l is string => l != null),
                      )].join(" | "));
                      return rows.map((row, rowIdx) => {
                        const label = rowLabels[rowIdx];
                        const prevLabel = rowIdx > 0 ? rowLabels[rowIdx - 1] : "";
                        const showLabel = label !== "" && label !== prevLabel;
                        return (
                          <div key={`${sub.sub}-row-${rowIdx}`} className="mb-4">
                            {showLabel && (
                              <div className="mb-1.5 pl-3 text-sm font-bold text-slate-500">
                                {label}
                              </div>
                            )}
                            <div className={chartRowGridClass(row.length)}>
                              {row.map((chart) => (
                                <LazyChartCard key={chart.id} chart={chart} />
                              ))}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
