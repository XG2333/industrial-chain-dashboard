import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import * as echarts from "echarts/core";
import { CandlestickChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { CHART_FONTS, useChartTheme } from "@/theme/chartTheme";

echarts.use([LineChart, CandlestickChart, GridComponent, TooltipComponent, CanvasRenderer]);

// 顶部核心商品 KPI 带（第一行 4 卡一行）：
//   1) 现货(Excel 日频)  2) 主力(新浪盘面实时, live 标记, 30s 轮询)
//   3) 主力当日分时图(5 分钟)  4) 主力近 120 根日K 蜡烛图
// 现货无公开实时源保持 Excel 日频口径；主力与两图均随 30s 轮询跳动。

interface KpiItem {
  key: string;
  label: string;
  title: string;
  unit: string;
  value: number;
  date: string;
  change_pct: number | null;
  live?: boolean;
  live_time?: string;
}

interface KpiGroup {
  dataset: string;
  label: string;
  items: KpiItem[];
}

interface FutureMarket {
  ok: boolean;
  code: string;
  prev_close: number | null;
  date: string;
  interval?: "1" | "5";
  minute: { t: string; v: number }[];
  daily: { d: string; o: number; h: number; l: number; c: number; v: number }[];
}

const cc = (pct: number | null) => {
  if (pct == null || pct === 0) return "text-muted-foreground";
  return pct > 0 ? "text-red-500" : "text-green-500";
};

const fmtValue = (v: number) =>
  Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("zh-CN") : String(Math.round(v * 100) / 100);

export function IndustryKpiBand({ dataset }: { dataset: string }) {
  const theme = useChartTheme();
  const [groups, setGroups] = useState<KpiGroup[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState("");
  const [market, setMarket] = useState<FutureMarket | null>(null);
  const minuteRef = useRef<HTMLDivElement>(null);
  const klineRef = useRef<HTMLDivElement>(null);

  const loadKpi = useCallback((showSpin: boolean) => {
    if (showSpin) setLoading(true);
    fetch("/api/industry/kpi")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.groups?.length) {
          setGroups(d.groups);
          setFailed(false);
          setRefreshedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
        } else {
          setFailed(true);
        }
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const loadMarket = useCallback(() => {
    fetch(`/api/industry/future-market?dataset=${dataset}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.ok) setMarket(d);
      })
      .catch(() => {});
  }, [dataset]);

  // 30 秒轮询：主力价格/分时/日K 为盘面数据;现货为 Excel 日频(手动刷新用于更新后重取)
  useEffect(() => {
    loadKpi(false);
    loadMarket();
    const t = window.setInterval(() => {
      loadKpi(false);
      loadMarket();
    }, 30_000);
    return () => window.clearInterval(t);
  }, [loadKpi, loadMarket]);

  const group = groups?.find((g) => g.dataset === dataset) ?? null;
  const items = group?.items ?? [];
  const spot = items.find((i) => i.key === "spot") ?? null;
  const future = items.find((i) => i.key === "future") ?? null;

  // ── 当日分时(5 分钟) ──
  useEffect(() => {
    const node = minuteRef.current;
    const pts = market?.minute ?? [];
    if (!node || pts.length < 2) return;
    const values = pts.map((p) => p.v);
    const last = values[values.length - 1];
    const up =
      market?.prev_close != null ? last >= market.prev_close : last >= values[0];
    const color = up ? "#ef4444" : "#22c55e";
    echarts.dispose(node);
    const chart = echarts.init(node);
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 2, right: 2, top: 6, bottom: 4 },
      xAxis: {
        type: "category", data: pts.map((p) => p.t),
        axisLine: { show: false }, axisTick: { show: false },
        // 标签步长按点数自适应: 1分钟(~240点)每30根一个, 5分钟(~48点)每12根一个
        axisLabel: { fontSize: 8, color: theme.secondaryText, interval: (i: number) => i % (pts.length > 150 ? 30 : 12) === 0 },
      },
      yAxis: { type: "value", scale: true, show: false, splitLine: { show: false } },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { name: string; data: number }[]) => {
          const p = ps[0];
          return (p.name || "") + "<br/><b>" + (p.data?.toFixed(0) ?? "-") + "</b>";
        },
      },
      series: [{
        type: "line", data: values, symbol: "none", smooth: false,
        lineStyle: { width: 1.5, color },
        areaStyle: { color: color + "1a" },
      }],
    });
    return () => { chart.dispose(); };
  }, [market, theme]);

  // ── 日K 蜡烛(近 120 根, 红涨绿跌) ──
  useEffect(() => {
    const node = klineRef.current;
    const daily = market?.daily ?? [];
    if (!node || daily.length < 2) return;
    echarts.dispose(node);
    const chart = echarts.init(node);
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 2, right: 2, top: 6, bottom: 2 },
      xAxis: {
        type: "category",
        data: daily.map((k) => k.d.slice(5)),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { fontSize: 8, color: theme.secondaryText, interval: (i: number) => i % 20 === 0 },
      },
      yAxis: { type: "value", scale: true, show: false, splitLine: { show: false } },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { name: string; data: number[] }[]) => {
          const p = ps[0];
          if (!p?.data) return "";
          const [o, c, l, h] = p.data;
          return `${p.name}<br/>开 ${o?.toFixed(0)} 高 ${h?.toFixed(0)}<br/>低 ${l?.toFixed(0)} 收 ${c?.toFixed(0)}`;
        },
      },
      series: [{
        type: "candlestick",
        data: daily.map((k) => [k.o, k.c, k.l, k.h]),
        itemStyle: {
          color: "#ef4444", color0: "#22c55e",
          borderColor: "#ef4444", borderColor0: "#22c55e",
        },
      }],
    });
    return () => { chart.dispose(); };
  }, [market, theme]);

  if (!groups && !failed) {
    return (
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[128px] animate-pulse rounded-xl border bg-card p-4">
            <div className="h-3 w-16 rounded bg-muted" />
            <div className="mt-3 h-7 w-24 rounded bg-muted" />
            <div className="mt-2 h-3 w-12 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }
  if (failed || items.length === 0) return null;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">
          {group?.label ?? ""}核心价格 · 现货日频 / 主力实时(30s 自动刷新)
        </span>
        <span className="flex items-center gap-2">
          {refreshedAt && (
            <span className="text-[10px] text-muted-foreground/70">刷新于 {refreshedAt}</span>
          )}
          <button
            type="button"
            onClick={() => { loadKpi(true); loadMarket(); }}
            disabled={loading}
            title="重新读取最新值"
            className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] font-medium text-muted-foreground transition hover:bg-muted/40 hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={"h-3 w-3 " + (loading ? "animate-spin" : "")} />
            刷新
          </button>
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {/* 1) 现货卡 */}
        {spot && (
          <div className="min-w-0 rounded-xl border bg-card p-3" title={spot.title}>
            <div className="flex items-center justify-between gap-1">
              <span className="min-w-0 truncate text-xs font-medium text-slate-500 dark:text-slate-400">
                {spot.label}
              </span>
              <span className="shrink-0 rounded border border-border px-1 text-[10px] text-muted-foreground">
                {group?.label ?? ""}
              </span>
            </div>
            <p className="mt-1.5 text-2xl font-bold tabular-nums tracking-tight text-foreground">
              {fmtValue(spot.value)}
            </p>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className={`text-xs font-semibold tabular-nums ${cc(spot.change_pct)}`}>
                {spot.change_pct == null
                  ? "—"
                  : (spot.change_pct > 0 ? "+" : "") + spot.change_pct.toFixed(2) + "%"}
              </span>
              <span className="text-[10px] text-muted-foreground">日环比</span>
            </div>
            <div className="mt-1.5 flex items-center justify-between border-t border-border/50 pt-1 text-[10px] text-muted-foreground">
              <span>截至 {spot.date.replace(/-/g, "/")}</span>
              <span className="truncate pl-2">{spot.unit}</span>
            </div>
          </div>
        )}

        {/* 2) 主力卡(实时) */}
        {future && (
          <div className="min-w-0 rounded-xl border bg-card p-3" title={future.title}>
            <div className="flex items-center justify-between gap-1">
              <span className="min-w-0 truncate text-xs font-medium text-slate-500 dark:text-slate-400">
                {future.label}
              </span>
              <span className="flex shrink-0 items-center gap-1">
                {future.live && (
                  <span className="flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1 text-[10px] font-semibold text-primary">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                    实时
                  </span>
                )}
                <span className="rounded border border-border px-1 text-[10px] text-muted-foreground">
                  {group?.label ?? ""}
                </span>
              </span>
            </div>
            <p className="mt-1.5 text-2xl font-bold tabular-nums tracking-tight text-foreground">
              {fmtValue(future.value)}
            </p>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className={`text-xs font-semibold tabular-nums ${cc(future.change_pct)}`}>
                {future.change_pct == null
                  ? "—"
                  : (future.change_pct > 0 ? "+" : "") + future.change_pct.toFixed(2) + "%"}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {future.live ? "实时涨跌" : "日环比"}
              </span>
            </div>
            <div className="mt-1.5 flex items-center justify-between border-t border-border/50 pt-1 text-[10px] text-muted-foreground">
              <span>
                截至 {future.date.replace(/-/g, "/")}
                {future.live && future.live_time && future.live_time.length >= 4
                  ? ` ${future.live_time.slice(0, 2)}:${future.live_time.slice(2, 4)}`
                  : ""}
              </span>
              <span className="truncate pl-2">{future.unit}</span>
            </div>
          </div>
        )}

        {/* 3) 当日分时图卡 */}
        <div className="min-w-0 rounded-xl border bg-card p-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              主力当日分时
            </span>
            <span className="text-[10px] text-muted-foreground">
              {market?.date ? market.date.replace(/-/g, "/") : ""}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between px-1">
            <span className="text-[10px] text-muted-foreground/70">
              昨结 {market?.prev_close != null ? Math.round(market.prev_close).toLocaleString("zh-CN") : "-"}
            </span>
            <span className="text-[10px] text-muted-foreground/70">
              {market?.interval === "1" ? "1分钟" : "5分钟"}
            </span>
          </div>
          <div className="h-[74px]">
            {(market?.minute?.length ?? 0) >= 2 ? (
              <div ref={minuteRef} style={{ width: "100%", height: "100%" }} />
            ) : (
              <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/50">
                分时数据加载中…
              </div>
            )}
          </div>
        </div>

        {/* 4) 日K 图卡 */}
        <div className="min-w-0 rounded-xl border bg-card p-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              主力日K
            </span>
            <span className="text-[10px] text-muted-foreground">
              {market?.daily?.length ? `近 ${market.daily.length} 根` : ""}
            </span>
          </div>
          <div className="h-[92px]">
            {(market?.daily?.length ?? 0) >= 2 ? (
              <div ref={klineRef} style={{ width: "100%", height: "100%" }} />
            ) : (
              <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/50">
                日K 数据加载中…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
