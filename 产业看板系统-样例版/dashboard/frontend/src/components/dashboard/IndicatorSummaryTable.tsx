import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { ChartData, ChartMeta } from "@/lib/chartTypes";
import { loadChartData } from "@/lib/excelCache";
import { simplifyIndicatorName } from "@/lib/indicatorName";
import { TrendChart } from "@/components/charts/TrendChart";

// 板块指标速览表：每个板块开头展示指标近 2 期数据（日度近 2 天、周度近 2 周）
// + 环比，一行两个指标。日度/周度指标各用独立表头。
// 功能：搜索过滤、表头排序、sub 分组标题带数量、整行点击跳转图表（闪烁提示）、
// 每行走势迷你图 + 悬停放大（颜色按月环比：>0 红、<0 绿、=0/缺失 灰）。

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

interface Recent {
  v1: number | null;
  v2: number | null;
  chg: number | null;
}

// 周度数据按周采样：部分周度指标每周有 2 个数据点（周三/周四，周四值与下一周
// 周三重复），直接取前 2 点会显示"相隔 1 天"的日期而非相隔一周。
// 按 ISO 周分组（周一为起点），每周取最新（第一个）数据点；正常指标每周 1 点不受影响。
export function sampleWeekly(data: { date: string; value: number }[]): { date: string; value: number }[] {
  const out: { date: string; value: number }[] = [];
  let lastWeek = "";
  for (const p of data) {
    // 数据降序（最新在前），周一为一周起点（本地时区计算，避免 toISOString 的 UTC 偏移）
    const d = new Date(p.date + "T00:00:00");
    const monday = new Date(d.getTime() - ((d.getDay() + 6) % 7) * 86400000);
    const week =
      `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
    if (week !== lastWeek) {
      out.push(p);
      lastWeek = week;
    }
  }
  return out;
}

// 月环比(%) = (最新值 − 30 天前的最近数据点) ÷ 30 天前值 × 100
//（数据为降序，最新在前；返回百分比而非绝对差，否则会被渲染处误读为 210% 之类）
function monthlyChange(data: { date: string; value: number }[]): number | null {
  if (data.length < 2) return null;
  const t1 = new Date(data[0].date + "T00:00:00").getTime();
  const cutoff = t1 - 30 * 86400000;
  let base: number | null = null;
  for (const p of data) {
    const t = new Date(p.date + "T00:00:00").getTime();
    if (t <= cutoff) {
      base = p.value;
      break;
    }
  }
  if (base == null || base === 0) return null;
  return Math.round(((data[0].value - base) / base) * 10000) / 100;
}

// 点击指标跳转到对应图表卡，并闪烁红色边框提示（闪烁 2 下，0.8s/下）
function flashChart(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("chart-flash");
  window.setTimeout(() => el.classList.remove("chart-flash"), 1600);
}

// 近 2 期数据点 + 环比（周度指标先按周采样）
function recentTwo(chart: ChartData): Recent {
  const raw = chart.data || [];
  const pts = chart.freq === "weekly" ? sampleWeekly(raw) : raw;
  const v1 = pts[0]?.value ?? null;
  const v2 = pts[1]?.value ?? null;
  const chg = v1 != null && v2 != null ? Math.round((v1 - v2) * 100) / 100 : null;
  return { v1, v2, chg };
}

// 迷你走势线（SVG 轻量渲染，不打断表格；近 60 个数据点）
// 颜色由外部传入（月环比 >0 红、<0 绿、=0/缺失 灰），与悬停大图一致。
// 注意：data 为降序（最新在前），画线前必须先转升序，否则时间轴颠倒。
function Sparkline({ data, color }: { data?: { date: string; value: number }[]; color: "up" | "down" | "neutral" }) {
  const pts = (data || []).slice(0, 60).reverse();
  if (pts.length < 2) {
    return <span className="text-xs text-muted-foreground/40">—</span>;
  }
  const values = pts.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 90;
  const h = 24;
  const coords = pts.map((p, i) => {
    const x = (i / (pts.length - 1)) * (w - 2) + 1;
    const y = h - 2 - ((p.value - min) / range) * (h - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const stroke = color === "up" ? "#ef4444" : color === "down" ? "#22c55e" : "#94a3b8";
  return (
    <svg width={w} height={h} className="inline-block align-middle" role="img" aria-label="指标走势">
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// 迷你图 + 悬停放大：鼠标悬停时在行右侧弹出大图（fixed 定位，不受表格裁剪影响）
// 配色说明：走势线颜色按月环比区分（>0 红、<0 绿、=0/缺失 灰），与表格数值列的
// 日/周环比文字颜色可能不同（短期回调但月度仍涨时：绿字红线）。为消除误读，
// 走势图下方标注月环比数值（颜色与线一致）。
function TableSparklineHover({ chart }: { chart: ChartData }) {
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
  const m = monthlyChange(chart.data || []);
  const color: "up" | "down" | "neutral" = m == null ? "neutral" : m > 0 ? "up" : "down";
  const trendUp = m == null ? null : m > 0;
  const title = simplifyIndicatorName(chart.title);
  const mText =
    m == null
      ? null
      : `月环比 ${m > 0 ? "+" : ""}${Math.round(m * 100) / 100}%`;
  const mCls =
    m == null
      ? ""
      : m > 0
        ? "text-red-500"
        : m < 0
          ? "text-green-600"
          : "text-muted-foreground";

  return (
    <div
      ref={cellRef}
      className="relative flex cursor-pointer items-center justify-center gap-1.5"
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
      <Sparkline data={chart.data} color={color} />
      {mText && (
        <span className={`whitespace-nowrap text-[11px] leading-none tabular-nums ${mCls}`} title="走势颜色依据：月环比">
          {mText}
        </span>
      )}
      {pos && (
        <div
          className="fixed z-50 w-[320px] rounded-lg border border-border bg-card p-2 shadow-xl"
          style={{ left: pos.x, top: pos.y }}
          onMouseEnter={cancelHide}
          onMouseLeave={() => setPos(null)}
        >
          <p className="truncate text-sm font-bold text-foreground" title={title}>
            {title}
          </p>
          <div className="h-36">
            {/* 全量历史(可跨数年)：横轴标签带年份(YYYY-MM)，避免看不出时间跨度 */}
            <TrendChart title={title} unit={chart.unit} data={(chart.data || []) as { date: string; value: number }[]} trendUp={trendUp} showYearLabel />
          </div>
        </div>
      )}
    </div>
  );
}

// 单指标单元格组（5 列：指标名 / 近 2 期 / 环比 / 走势迷你图）。
// 左组（rightBorder）走势列右侧带中间分隔线。
function IndicatorCells({ chart, rightBorder = false }: { chart: ChartData; rightBorder?: boolean }) {
  const r = recentTwo(chart);
  const divider = rightBorder ? " border-r-2 border-r-slate-400" : "";
  const valCls = "px-2 py-0.5 text-right text-[15px] tabular-nums";
  return (
    <>
      {/* 指标名 + 单位并入一列（名称可换行，单位小字）；点击跳转到对应图表并闪烁提示 */}
      <td
        className="min-w-[130px] cursor-pointer px-2 py-0.5 font-medium text-foreground hover:bg-muted/30"
        onClick={(e) => {
          e.stopPropagation();
          flashChart(chart.id);
        }}
        title={`${chart.title}（点击跳转到图表）`}
      >
        <div className="whitespace-normal break-words hover:underline">{simplifyIndicatorName(chart.title)}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground">{chart.unit || "—"}</div>
      </td>
      {/* 数值列固定宽度右对齐；空值置灰；数值字体与表头日期一致（15px） */}
      <td className={`${valCls}${r.v1 == null ? " text-muted-foreground/40" : ""}`}>{fmt(r.v1)}</td>
      <td className={`${valCls} text-muted-foreground/80${r.v2 == null ? " opacity-60" : ""}`}>{fmt(r.v2)}</td>
      <td className={`${valCls} font-semibold ${chgColor(r.chg)}`}>{fmtSigned(r.chg)}</td>
      {/* 走势列：迷你图 + 悬停放大；颜色按月环比区分 */}
      <td className={`border-l border-border/60 px-1.5 py-0.5 align-middle${divider}`}>
        <TableSparklineHover chart={chart} />
      </td>
    </>
  );
}

interface SubGroup {
  sub: string;
  items: ChartMeta[];
}

function groupBySub(items: ChartMeta[]): SubGroup[] {
  const subs: SubGroup[] = [];
  for (const c of items) {
    const subName = c.sub ?? "其他";
    const existing = subs.find((s) => s.sub === subName);
    if (existing) {
      existing.items.push(c);
    } else {
      subs.push({ sub: subName, items: [c] });
    }
  }
  return subs;
}

// 默认收起：整组截断（保持组完整，不切断组内指标），返回展示组与隐藏指标数
const DEFAULT_VISIBLE_PER_TABLE = 12;
function trimGroups(groups: SubGroup[], limit: number): { shown: SubGroup[]; hidden: number } {
  let count = 0;
  const shown: SubGroup[] = [];
  for (const g of groups) {
    if (shown.length && count + g.items.length > limit) break;
    shown.push(g);
    count += g.items.length;
  }
  const hidden = groups.reduce((s, g) => s + g.items.length, 0) - count;
  return { shown, hidden };
}

type SortCol = "v1" | "v2" | "chg";
interface SortState {
  col: SortCol;
  dir: 1 | -1;
}

function valueOfChart(chart: ChartMeta, dataMap: Map<string, ChartData>, col: SortCol): number | null {
  const data = dataMap.get(chart.id);
  if (!data) return null;
  const r = recentTwo(data);
  return col === "v1" ? r.v1 : col === "v2" ? r.v2 : r.chg;
}

// 分组内按列排序（空值排最后）
function sortedItems(items: ChartMeta[], sort: SortState, dataMap: Map<string, ChartData>): ChartMeta[] {
  return [...items].sort((a, b) => {
    const va = valueOfChart(a, dataMap, sort.col);
    const vb = valueOfChart(b, dataMap, sort.col);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va - vb) * sort.dir;
  });
}

// 每个指标单元格组 5 列；一行两个指标共 10 列
const CELLS_PER_GROUP = 5;

// 单个表格（日度或周度）：表头列头用该频率指标的真实日期，列名区分"日环比/周环比"
function SummaryTableBody({
  groups,
  dataMap,
  weekly,
}: {
  groups: SubGroup[];
  dataMap: Map<string, ChartData>;
  weekly: boolean;
}) {
  const [sort, setSort] = useState<SortState | null>(null);

  const firstData = dataMap.get(groups[0].items[0].id);
  // 周度表列头日期同样按周采样（取每周最新点），保证显示"相隔一周"的日期
  const sampled = weekly && firstData?.data ? sampleWeekly(firstData.data) : firstData?.data ?? [];
  const asof = sampled[0]?.date ?? "";
  const second = sampled[1]?.date ?? "";
  const chgLabel = weekly ? "周环比" : "日环比";

  const toggleSort = (col: SortCol) => {
    setSort((s) => (s && s.col === col ? (s.dir === 1 ? { col, dir: -1 } : null) : { col, dir: 1 }));
  };
  const sortMark = (col: SortCol) => (sort?.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");

  return (
    <div className="px-4 py-1.5">
      {/* table-fixed + colgroup：日度/周度两表列宽结构完全一致，
          左右指标名列平分剩余宽度 → 中间竖线固定在中线，两表对齐 */}
      <table className="w-full table-fixed text-xs">
        <colgroup>
          {[0, 1].map((g) => (
            <Fragment key={g}>
              <col className="min-w-[130px]" />
              {/* 日期列需容纳 "2026/08/19" + 排序箭头（15px bold 约 90px），加宽到 110px */}
              <col style={{ width: "110px" }} />
              <col style={{ width: "110px" }} />
              {/* 环比列 "日环比/周环比" 较短，独立收窄 */}
              <col style={{ width: "78px" }} />
              {/* 走势列：90px 迷你线 + 右侧月环比标注（约 75px） */}
              <col style={{ width: "176px" }} />
            </Fragment>
          ))}
        </colgroup>
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            {[0, 1].map((g) => (
              <Fragment key={g}>
                <th className="sticky top-0 z-10 bg-card px-2 py-0.5 text-[15px] font-bold">
                  {g === 0 ? (weekly ? "周度指标" : "日度指标") : ""}
                </th>
                <th
                  onClick={() => toggleSort("v1")}
                  className="sticky top-0 z-10 cursor-pointer select-none bg-card px-2 py-0.5 text-right text-[15px] font-bold hover:text-foreground"
                >
                  {asof.replace(/-/g, "/")}
                  {sortMark("v1")}
                </th>
                <th
                  onClick={() => toggleSort("v2")}
                  className="sticky top-0 z-10 cursor-pointer select-none bg-card px-2 py-0.5 text-right text-[15px] font-bold hover:text-foreground"
                >
                  {second.replace(/-/g, "/")}
                  {sortMark("v2")}
                </th>
                <th
                  onClick={() => toggleSort("chg")}
                  className="sticky top-0 z-10 cursor-pointer select-none bg-card px-2 py-0.5 text-right text-[15px] font-bold hover:text-foreground"
                >
                  {chgLabel}
                  {sortMark("chg")}
                </th>
                {/* 走势列：左侧 border 与数值列分隔；左组右侧带中间竖线（与表体贯穿） */}
                <th
                  className={`sticky top-0 z-10 border-l border-border bg-card px-1.5 py-0.5 text-center text-[15px] font-bold${g === 0 ? " border-r-2 border-r-slate-400" : ""}`}
                >
                  走势
                </th>
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const items = sort ? sortedItems(g.items, sort, dataMap) : g.items;
            const rows: ChartMeta[][] = [];
            for (let i = 0; i < items.length; i += 2) {
              rows.push(items.slice(i, i + 2));
            }
            return (
              <Fragment key={g.sub}>
                {/* 不同子类（大类）分组间的分隔线，标题带指标数量；中间竖线贯穿标题行 */}
                <tr className="border-t-2 border-t-slate-400 border-b border-border/60 bg-muted/25 text-foreground">
                  <td colSpan={CELLS_PER_GROUP} className="border-r-2 border-r-slate-400 px-2 py-0.5 text-[15px] font-bold">
                    {g.sub}({g.items.length})
                  </td>
                  <td colSpan={CELLS_PER_GROUP} className="px-2 py-0.5" />
                </tr>
                {rows.map((pair, ri) => (
                  <tr
                    key={ri}
                    onClick={() => {
                      if (pair[0]) flashChart(pair[0].id);
                    }}
                    className={`cursor-pointer border-b border-border/60 hover:bg-muted/40${ri % 2 === 1 ? " bg-muted/5" : ""}`}
                  >
                    {pair[0] && dataMap.get(pair[0].id) ? (
                      <IndicatorCells chart={dataMap.get(pair[0].id)!} rightBorder />
                    ) : (
                      Array.from({ length: CELLS_PER_GROUP }, (_, k) => (
                        <td
                          key={k}
                          className={`px-2 py-0.5${k === CELLS_PER_GROUP - 1 ? " border-r-2 border-r-slate-400" : ""}`}
                        />
                      ))
                    )}
                    {pair[1] && dataMap.get(pair[1].id) ? (
                      <IndicatorCells chart={dataMap.get(pair[1].id)!} />
                    ) : (
                      Array.from({ length: CELLS_PER_GROUP }, (_, k) => <td key={k} className="px-2 py-0.5" />)
                    )}
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function IndicatorSummaryTable({ charts }: { charts: ChartMeta[] }) {
  const [dataMap, setDataMap] = useState<Map<string, ChartData>>(new Map());
  const [query, setQuery] = useState("");
  // 默认收起长表（搜索输入时自动展开）
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const ids = charts.map((c) => c.id);
    if (ids.length === 0) return;
    loadChartData(ids)
      .then((loaded) => {
        if (!cancelled) setDataMap(new Map(loaded.map((c) => [c.id, c])));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [charts]);

  const { daily, weekly } = useMemo(() => {
    const withData = charts.filter((c) => (dataMap.get(c.id)?.data?.length ?? 0) > 0);
    const q = query.trim();
    // 按简化后的指标名搜索（同时兼容原标题）
    const matched = q
      ? withData.filter(
          (c) =>
            simplifyIndicatorName(c.title).includes(q) ||
            (c.title || "").includes(q),
        )
      : withData;
    return {
      daily: groupBySub(matched.filter((c) => c.freq === "daily")),
      weekly: groupBySub(matched.filter((c) => c.freq === "weekly")),
    };
  }, [charts, dataMap, query]);

  // 板块本身无日度/周度指标时不显示；搜索输入时始终保留标题行+搜索框
  if (daily.length === 0 && weekly.length === 0 && !query.trim()) return null;

  // 默认收起：日度/周度各只显示前若干整组；搜索时强制全量
  const collapsed = !query.trim() && !expanded;
  const dailyTrim = collapsed ? trimGroups(daily, DEFAULT_VISIBLE_PER_TABLE) : { shown: daily, hidden: 0 };
  const weeklyTrim = collapsed ? trimGroups(weekly, DEFAULT_VISIBLE_PER_TABLE) : { shown: weekly, hidden: 0 };
  const hiddenTotal = dailyTrim.hidden + weeklyTrim.hidden;
  const dailyShown = dailyTrim.shown;
  const weeklyShown = weeklyTrim.shown;
  // 表本身超出默认限制时，无论展开/收起都显示切换按钮（展开后可收起）
  const canToggle =
    trimGroups(daily, DEFAULT_VISIBLE_PER_TABLE).hidden +
      trimGroups(weekly, DEFAULT_VISIBLE_PER_TABLE).hidden >
    0;

  // 标题日期 = 全局最新数据日期（优先日度，其次周度）
  // 注意：搜索无匹配时 daily/weekly 都为空，titleSource 为 undefined，必须先判空
  // （否则 titleSource.id 抛 TypeError，React 卸载整棵树 → 页面空白）
  const titleSource = daily[0]?.items[0] ?? weekly[0]?.items[0];
  const titleDate = titleSource ? (dataMap.get(titleSource.id)?.data?.[0]?.date ?? "") : "";

  return (
    <div className="mb-4 rounded-xl border bg-card">
      {/* 标题行 + 搜索框 */}
      <div className="flex items-center justify-between gap-2 px-5 pt-2">
        <div className="text-lg font-bold text-foreground">
          近期指标速览{titleDate ? ` · 截至 ${titleDate.replace(/-/g, "/")}` : ""}
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索指标…"
          className="w-40 rounded border border-border bg-background px-2 py-1 text-xs text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary"
        />
      </div>
      {daily.length === 0 && weekly.length === 0 ? (
        <div className="px-5 py-4 text-sm text-muted-foreground">
          未找到匹配“<span className="font-medium text-foreground">{query}</span>”的指标
        </div>
      ) : (
        <>
          {daily.length > 0 && <SummaryTableBody groups={dailyShown} dataMap={dataMap} weekly={false} />}
          {weekly.length > 0 && (
            <>
              {/* 日度与周度表之间分隔 */}
              <div className="mx-4 my-1 border-t-[3px] border-slate-400" />
              <SummaryTableBody groups={weeklyShown} dataMap={dataMap} weekly />
            </>
          )}
          {/* 收起长表：默认只显示前几组；展开后按钮保留，可随时收起 */}
          {canToggle && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="block w-full border-t border-border/60 py-2 text-center text-xs font-medium text-primary hover:bg-muted/20"
            >
              {expanded ? "收起" : `展开剩余 ${hiddenTotal} 条指标`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
