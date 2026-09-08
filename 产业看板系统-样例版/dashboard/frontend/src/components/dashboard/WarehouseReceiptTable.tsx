import { useEffect, useRef, useState } from "react";
import { TrendChart } from "@/components/charts/TrendChart";
import { WarehouseQuickAnalysis } from "@/components/dashboard/WarehouseQuickAnalysis";
import { ContractPositionTable } from "@/components/dashboard/ContractPositionTable";

interface WarehouseRow {
  kind: "warehouse" | "region" | "total" | "metric";
  warehouse: string;
  region: string;
  product: string;
  values: (number | null)[];
  daily_change: number | null;
  weekly_change: number | null;
  monthly_change: number | null;
  daily_rate: number | null;
  weekly_rate: number | null;
  monthly_rate: number | null;
  // 仓库明细行的折线数据（近 N 个交易日，供表格内插图）
  series?: { date: string; value: number }[];
}

interface WarehouseTableData {
  dates: string[];
  rows: WarehouseRow[];
  title: string;
}

// 涨跌着色：正值红色、负值绿色、零值灰色（与页面行情配色一致）
const chgColor = (v: number | null) =>
  v == null ? "text-muted-foreground/40" : v > 0 ? "text-red-500" : v < 0 ? "text-green-500" : "text-muted-foreground";

const fmt = (v: number | null) => {
  if (v == null) return "#N/A";
  const n = Math.round(v * 100) / 100;
  return Number.isInteger(n) ? String(n) : String(n);
};

const fmtSigned = (v: number | null) => {
  if (v == null) return "#N/A";
  const s = v > 0 ? "+" : "";
  return `${s}${fmt(v)}`;
};

// 迷你走势线（SVG 轻量渲染，不打断表格；近 60 个数据点）
// 颜色由外部传入（月环比 >0 红、<0 绿、=0/缺失 灰），与悬停大图一致。
// 注意：server 返回的 series 为降序（最新在前），画线前必须先转升序，
// 否则时间轴颠倒、趋势与 TrendChart（升序）镜像相反。
function Sparkline({ data, color }: { data?: { date: string; value: number }[]; color: "up" | "down" | "neutral" }) {
  const pts = (data || []).slice(0, 60).reverse();
  if (pts.length < 2) {
    return <span className="text-sm text-muted-foreground/40">—</span>;
  }
  const values = pts.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 170;
  const h = 28;
  const coords = pts.map((p, i) => {
    const x = (i / (pts.length - 1)) * (w - 2) + 1;
    const y = h - 2 - ((p.value - min) / range) * (h - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const stroke = color === "up" ? "#ef4444" : color === "down" ? "#22c55e" : "#94a3b8";
  return (
    <svg width={w} height={h} className="inline-block align-middle" role="img" aria-label="仓单量走势">
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// 迷你图 + 悬停放大：鼠标悬停时在行右侧弹出大图（fixed 定位，不受表格裁剪影响）
// 颜色按月环比区分：>0 红、<0 绿、=0/缺失 灰
function SparklineHover({ row }: { row: WarehouseRow }) {
  const cellRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<number | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  // 延迟关闭：鼠标从走势线移向弹层(或经过缝隙)时不闪关；移入弹层取消关闭
  const scheduleHide = () => {
    if (hideTimer.current) window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setPos(null), 250);
  };
  const cancelHide = () => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  };
  // 颜色按月环比区分：>0 红、<0 绿、=0/缺失 灰
  const m = row.monthly_change;
  const color: "up" | "down" | "neutral" = m == null ? "neutral" : m > 0 ? "up" : "down";
  const trendUp = m == null ? null : m > 0;
  const chartTitle = row.kind === "warehouse" ? `${row.warehouse}仓单量` : row.warehouse;

  return (
    <div
      ref={cellRef}
      className="relative cursor-pointer"
      onMouseEnter={() => {
        const r = cellRef.current?.getBoundingClientRect();
        if (!r) return;
        const popW = 320;
        const popH = 200;
        const x = Math.min(r.right + 10, window.innerWidth - popW - 10);
        const y = Math.max(4, Math.min(r.top, window.innerHeight - popH - 10));
        setPos({ x, y });
      }}
      onMouseLeave={scheduleHide}
    >
      <Sparkline data={row.series} color={color} />
      {pos && (
        <div
          className="fixed z-50 w-[320px] rounded-lg border border-border bg-card p-2 shadow-xl"
          style={{ left: pos.x, top: pos.y }}
          onMouseEnter={cancelHide}
          onMouseLeave={() => setPos(null)}
        >
          <p className="truncate text-sm font-bold text-foreground" title={chartTitle}>
            {chartTitle}
          </p>
          <div className="h-36">
            <TrendChart
              title={chartTitle}
              unit="手"
              data={(row.series || []) as { date: string; value: number }[]}
              trendUp={trendUp}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function WarehouseReceiptTable({ dataset }: { dataset: "lithium" | "tin" | "silicon" }) {
  const [data, setData] = useState<WarehouseTableData | null>(null);
  // 数据源: 本地Excel(默认, 全量历史+走势) ⇄ 公开API(交易所/东财, 当日仓单)
  const [sourceMode, setSourceMode] = useState<"excel" | "live">("excel");
  // 仓库行收起/展开：默认只显示前 10 个，按钮位于仓库与地区汇总的分隔线处
  const [whExpanded, setWhExpanded] = useState(false);
  const WH_LIMIT = 10;
  // 排序：默认按最新日期仓单量降序（大仓在前）；可切 日/周/月环比，
  // 再次点击同键切换升/降序（null/无数据显示在末尾）
  const [sortKey, setSortKey] = useState<"latest" | "daily" | "weekly" | "monthly">("latest");
  const [sortAsc, setSortAsc] = useState(false);
  const SORT_KEYS: { key: typeof sortKey; label: string }[] = [
    { key: "latest", label: "最新量" },
    { key: "daily", label: "日环比" },
    { key: "weekly", label: "周环比" },
    { key: "monthly", label: "月环比" },
  ];
  const sortValueOf = (row: WarehouseRow): number | null => {
    if (sortKey === "latest") return row.values[0] ?? null;
    if (sortKey === "daily") return row.daily_change;
    if (sortKey === "weekly") return row.weekly_change;
    return row.monthly_change;
  };
  const toggleSort = (key: typeof sortKey) => {
    if (key === sortKey) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(false); // 新键默认降序
    }
  };
  const cmpSort = (a: number | null, b: number | null): number => {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    const d = a - b;
    return sortAsc ? d : -d;
  };

  useEffect(() => {
    let cancelled = false;
    const url =
      sourceMode === "live"
        ? `/api/warehouse-table-live?dataset=${dataset}`
        : `/api/warehouse-table?dataset=${dataset}`;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled) return;
        if (!d) return;
        if (d.rows.length === 0 && sourceMode === "live") {
          // 公开源暂无数据(如非交易日) → 自动回退本地 Excel
          setSourceMode("excel");
          return;
        }
        setData(d);
      })
      .catch(() => {
        if (sourceMode === "live") setSourceMode("excel");
      });
    return () => {
      cancelled = true;
    };
  }, [dataset, sourceMode]);

  if (!data || data.rows.length === 0) return null;

  const hasMultiProduct =
    new Set(data.rows.filter((r) => r.kind === "warehouse").map((r) => r.product).filter(Boolean)).size > 1;
  // 只显示近 2 个交易日
  const displayDates = data.dates.slice(0, 2);
  const changeCols = [
    { label: "日环比", chg: "daily_change" as const, rate: "daily_rate" as const },
    { label: "周环比", chg: "weekly_change" as const, rate: "weekly_rate" as const },
    { label: "月环比", chg: "monthly_change" as const, rate: "monthly_rate" as const },
  ];
  // 左右分栏对齐：表格最右一列"走势"，每个仓库行右侧显示该仓库的仓单折线图
  //（与数据同行、随页面同步滚动）；汇总/量价行无图，图列留空
  const totalCols = 2 + (hasMultiProduct ? 1 : 0) + displayDates.length + changeCols.length + 1;

  // 仓库明细行与汇总行拆分（数据结构中仓库行均在前）：支持默认收起后 10+ 仓库
  const warehouseRows = data.rows.filter((r) => r.kind === "warehouse");
  const otherRows = data.rows.filter((r) => r.kind !== "warehouse");
  // 排序：仓库行按所选键排序；地区汇总行（kind=region）同键排序（汇总排序），
  // 全国总量/量价行（kind=total/metric）保持原业务顺序排在汇总区后
  const sortedWarehouseRows = [...warehouseRows].sort((x, y) => cmpSort(sortValueOf(x), sortValueOf(y)));
  const regionRows = otherRows.filter((r) => r.kind === "region");
  const tailRows = otherRows.filter((r) => r.kind !== "region");
  const sortedOtherRows = [...regionRows]
    .sort((x, y) => cmpSort(sortValueOf(x), sortValueOf(y)))
    .concat(tailRows);
  const needsToggle = sortedWarehouseRows.length > WH_LIMIT;
  const shownWarehouses = whExpanded
    ? sortedWarehouseRows
    : sortedWarehouseRows.slice(0, WH_LIMIT);
  const hiddenCount = sortedWarehouseRows.length - shownWarehouses.length;

  // 共享行单元格渲染（仓库明细/地区汇总/全国/量价共用一套列结构）
  const renderCells = (row: WarehouseRow) => (
    <>
      {row.kind === "warehouse" ? (
        <>
          {/* 仓库列限宽截断，压缩列宽为走势图留位置 */}
          <td className="max-w-[130px] px-1.5 py-px font-medium text-foreground">
            <span className="block truncate" title={row.warehouse}>{row.warehouse}</span>
          </td>
          <td className="max-w-[56px] px-1.5 py-px text-muted-foreground">{row.region || "—"}</td>
        </>
      ) : (
        <td colSpan={2} className="px-1.5 py-px text-center font-medium text-foreground">
          {row.warehouse}
        </td>
      )}
      {hasMultiProduct && <td className="px-1.5 py-px text-muted-foreground">{row.product || "—"}</td>}
      {row.values.slice(0, 2).map((v, vi) => (
        <td key={vi} className="px-1.5 py-px text-right tabular-nums">
          {fmt(v)}
        </td>
      ))}
      {changeCols.map((c) => (
        <td key={c.chg} className={`px-1.5 py-px text-right tabular-nums ${chgColor(row[c.chg])}`}>
          {fmtSigned(row[c.chg])}
        </td>
      ))}
      {/* 走势列：所有行（仓库明细/地区汇总/全国/量价）右侧显示迷你走势线，
          悬停弹出大图；颜色按月环比区分 */}
      <td className="border-l border-border/60 px-1.5 py-px align-middle">
        {(row.series?.length ?? 0) > 0 ? <SparklineHover row={row} /> : null}
      </td>
    </>
  );

  return (
    <div id="warehouse-receipts" className="scroll-mt-28 border-b border-border">
      {/* 标题行：仓单日报 单位（字号与"行业数据"标题一致）+ 排序控件 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-3 text-lg">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground">仓单日报</span>
          <span className="text-[10px] text-muted-foreground/70">
            {sourceMode === "live" ? "单位：手 · 公开API(交易所/东财) · 仅当日快照" : "单位：手"}
          </span>
        </div>
        {/* 右侧: 数据源切换 + 排序控件 */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-0.5 rounded-lg border border-border p-0.5">
            {(
              [
                { key: "excel", label: "本地Excel" },
                { key: "live", label: "公开API" },
              ] as const
            ).map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setSourceMode(key)}
                title={key === "live" ? "公开API: 锂/硅=广期所官网仓单日报(仓库级), 锡=东财仓单(仅全国总量); 当日快照, 无历史走势" : "本地Excel: 全量历史+地区汇总+走势(默认)"}
                className={
                  "rounded-md px-2 py-1 text-xs font-medium transition " +
                  (sourceMode === key
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted/40")
                }
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground/70">排序</span>
          {SORT_KEYS.map(({ key, label }) => {
            const active = sortKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleSort(key)}
                title="点击切换排序键；再次点击切换升/降序"
                className={
                  "flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm font-medium transition " +
                  (active
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted/40")
                }
              >
                {label}
                {active && <span className="text-xs">{sortAsc ? "↑" : "↓"}</span>}
              </button>
            );
          })}
          </div>
        </div>
      </div>
      <div className="px-4 py-2">
        <table className="w-full whitespace-nowrap text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="sticky top-0 z-10 bg-card px-1.5 py-px text-[15px] font-bold">仓库</th>
              <th className="sticky top-0 z-10 bg-card px-1.5 py-px text-[15px] font-bold">地区</th>
              {hasMultiProduct && (
                <th className="sticky top-0 z-10 bg-card px-1.5 py-px text-[15px] font-bold">品种</th>
              )}
              {displayDates.map((d) => (
                <th key={d} className="sticky top-0 z-10 bg-card px-1.5 py-px text-right font-medium">
                  {d.replace("-", "/")}
                </th>
              ))}
              {changeCols.map((c) => (
                <th key={c.label} className="sticky top-0 z-10 bg-card px-1.5 py-px text-right font-medium">
                  {c.label}
                </th>
              ))}
              <th className="sticky top-0 z-10 w-52 border-l border-border bg-card px-1.5 py-px font-medium">
                走势
              </th>
            </tr>
          </thead>
          <tbody>
            {/* 仓库明细区：默认前 10 个，可展开/收起 */}
            {shownWarehouses.map((row, i) => (
              <tr key={`${row.warehouse}-${i}`} className="border-b border-border/60 hover:bg-muted/40">
                {renderCells(row)}
              </tr>
            ))}
            {/* 仓库 → 地区汇总 分隔线处的收起/展开按钮（前 10 个之后）：
                全宽与表格同宽，上下边框横贯整行，消除居中按钮的割裂感 */}
            {needsToggle && (
              <tr>
                <td colSpan={totalCols} className="p-0">
                  <button
                    type="button"
                    onClick={() => setWhExpanded((v) => !v)}
                    className="block w-full border-y border-border bg-background py-1.5 text-center text-xs font-medium text-primary transition-colors hover:bg-muted/20"
                  >
                    {whExpanded ? "收起" : `展开剩余 ${hiddenCount} 个仓库`}
                  </button>
                </td>
              </tr>
            )}
            {/* 汇总区：地区汇总/全国/量价；仓库→汇总首行线由上方按钮行承担，其余切换处保留分隔线 */}
            {sortedOtherRows.map((row, j) => {
              const prevKind = j > 0 ? sortedOtherRows[j - 1].kind : "warehouse";
              const kindChanged = row.kind !== prevKind;
              // 分隔排版(合计行=单分隔线原则): 全国总量行上边用 1px 深灰单线且行底不再有线,
              // 其下(量价)行补一条常规细线; 其余汇总区切换处用 1px 中灰细线, 不再用 3px 粗线,
              // 避免"全国行"上下两条粗线夹击的视觉割裂
              const isTotal = row.kind === "total";
              const prevIsTotal = prevKind === "total";
              const boundary = kindChanged && !(j === 0 && needsToggle);
              const summaryDivider = isTotal
                ? " border-t border-t-slate-500/60"
                : prevIsTotal
                  ? " border-t border-t-border/60"
                  : boundary
                    ? " border-t border-t-slate-400/50"
                    : "";
              return (
                <tr
                  key={`${row.warehouse}-sum-${j}`}
                  style={isTotal ? { borderBottom: "none" } : undefined}
                  className={`border-b border-border/60 bg-muted/25 font-semibold text-foreground${summaryDivider}`}
                >
                  {renderCells(row)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* 仓单速评：基于上方仓单日报数据（AI 点评，与板块速评同款卡片） */}
      <div className="px-4 pb-4">
        <WarehouseQuickAnalysis dataset={dataset} source={sourceMode} />
      </div>
      {/* 各合约成交持仓：与仓单日报同款通栏版式（标题/排序控件/表格样式一致） */}
      <div className="border-t border-border/60">
        <ContractPositionTable dataset={dataset} />
      </div>
    </div>
  );
}
