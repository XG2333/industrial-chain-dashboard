import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { CardHeader } from "@/components/ui/CardHeader";
import { RefreshBtn } from "@/components/ui/RefreshBtn";
import { intradayDueKey } from "@/lib/autoRefreshTimes";

// 自选股票（C 方案：双层视图）
// 总览层：每行一个细分板块按钮（板块名+只数+涨跌只数+平均涨跌幅），
//   底色按板块平均涨跌幅红/绿深浅着色（热力，深浅 = 幅度），点击进入该板块；
//   顶部一条"市场宽度"摘要：全市场涨跌平只数 + 平均涨跌 + 领涨/领跌 Top3。
// 板块层：全宽股票表（代码/名称/最新/涨跌/成交量/换手/主力 完整列，表头固定），
//         顶部"← 返回板块总览"。空间占用 ≈ 板块数行高，一次只看一个板块。
// 自动刷新: 默认开启, 交易日按固定时点触发(09:32/整点半点/14:58, 见 REFRESH_TIMES), 非固定间隔;
// 时点刷新完成后回调 onAutoCycle 联动个股速评。

interface WatchStock {
  code: string;
  name: string;
  price: number;
  change_pct: number;
  volume: number;
  turnover_pct: number;
  // 明细扩展列(锡/硅等数据源未提供时显示 "-")
  open?: number;
  high?: number;
  low?: number;
  last_close?: number;
  amount_yi?: number;
}

interface SectorWatchlistProps {
  order: string[];
  sectors: Record<string, string[]>;
  data: Record<string, WatchStock>;
  flows: Record<string, number | null>;
  fetching: boolean;
  lastUpdate: string;
  onRefresh: () => void | Promise<void>;
  // flush: 不自带卡壳(由外层容器统一提供白卡边框, 用于与个股速评连成一体)
  flush?: boolean;
  // 定时自动刷新完成后回调(用于联动个股速评等下游: 等行情更新完再触发)
  onAutoCycle?: () => void;
}

const cc = (pct: number) =>
  pct === 0 ? "text-muted-foreground" : pct > 0 ? "text-red-500" : "text-green-500";

// 板块热力底色：按平均涨跌幅着色（红涨绿跌），|avg| 越大越深
const heatBg = (avg: number | null): string | undefined => {
  if (avg == null) return undefined;
  if (avg === 0) return "rgba(148, 163, 184, 0.08)";
  const alpha = Math.min(0.28, 0.05 + Math.abs(avg) * 0.045);
  return avg > 0
    ? `rgba(239, 68, 68, ${alpha.toFixed(3)})`
    : `rgba(34, 197, 94, ${alpha.toFixed(3)})`;
};

const fmtPct = (v: number) => (v > 0 ? "+" : "") + v.toFixed(2) + "%";

export function SectorWatchlist({
  order,
  sectors,
  data,
  flows,
  fetching,
  lastUpdate,
  onRefresh,
  flush = false,
  onAutoCycle,
}: SectorWatchlistProps) {
  // "overview" = 板块总览层；板块名 = 单板块视图
  const [view, setView] = useState<string>("overview");
  const activeSector = view === "overview" ? null : view;
  // 自动刷新开关（默认开，30s 轮询；跨页面共享偏好）
  const [autoRefresh, setAutoRefresh] = useState(() => {
    try {
      return localStorage.getItem("sector_watch_auto_v1") !== "off";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("sector_watch_auto_v1", autoRefresh ? "on" : "off");
    } catch {
      /* ignore */
    }
  }, [autoRefresh]);
  // 盘中定时自动刷新: 交易日固定时点触发(同一时点只刷一次), 完成后回调 onAutoCycle(联动个股速评);
  // 手动「刷新」与定时触发都走同一刷新流程, 完成后同样联动速评
  const lastAutoKey = useRef("");
  useEffect(() => {
    if (!autoRefresh) return;
    const tick = () => {
      const key = intradayDueKey();
      if (!key) return;
      if (lastAutoKey.current === key) return;
      lastAutoKey.current = key;
      void refreshAndCycle();
    };
    const t = window.setInterval(tick, 10_000);
    return () => window.clearInterval(t);
  }, [autoRefresh, onRefresh, onAutoCycle]);

  // 刷新 + 完成后联动下游(手动/自动共用): 先等行情刷新完成, 避免下游拿到旧数据
  const refreshAndCycle = async () => {
    try {
      await onRefresh();
    } catch {
      /* 仍尝试通知下游 */
    }
    if (onAutoCycle) onAutoCycle();
  };

  // 板块聚合统计：平均涨跌幅 + 上涨/下跌只数（供小卡扫读）
  const statOf = (codes: string[]): { avg: number | null; up: number; down: number } => {
    let up = 0;
    let down = 0;
    let sum = 0;
    let n = 0;
    for (const c of codes) {
      const s = data[c];
      if (!s || typeof s.change_pct !== "number") continue;
      if (s.change_pct > 0) up++;
      else if (s.change_pct < 0) down++;
      sum += s.change_pct;
      n++;
    }
    return { avg: n > 0 ? sum / n : null, up, down };
  };

  // 市场宽度（全部已加载股票）：只数 / 涨跌平 / 平均 / 领涨领跌 Top3
  const loaded = Object.values(data).filter((s) => s && s.price > 0);
  const width = (() => {
    if (loaded.length === 0) return null;
    let up = 0;
    let down = 0;
    let flat = 0;
    let sum = 0;
    for (const s of loaded) {
      if (s.change_pct > 0) up++;
      else if (s.change_pct < 0) down++;
      else flat++;
      sum += s.change_pct;
    }
    const sorted = [...loaded].sort((a, b) => b.change_pct - a.change_pct);
    return {
      total: loaded.length,
      up,
      down,
      flat,
      avg: sum / loaded.length,
      top: sorted.slice(0, 3),
      bottom: sorted.slice(-3).reverse(),
    };
  })();

  const fmtVol = (v?: number) =>
    (v || 0) >= 10000 ? ((v || 0) / 10000).toFixed(1) + "万手" : (v || 0) + "手";
  // 价格类(今开/最高/最低/昨收/最新): 0 视为未提供
  const fmtPx = (v?: number) => (v && v > 0 ? v.toFixed(2) : "-");
  // 成交额(亿)
  const fmtAmt = (v?: number) => (v && v > 0 ? v.toFixed(2) + "亿" : "-");

  const fmtFlow = (flow: number | null | undefined) =>
    flow == null ? "-" : (flow >= 0 ? "+" : "") + flow.toFixed(2) + "亿";

  const header = (
    <CardHeader
      title="自选股票"
      action={
        <div className="flex items-center gap-2">
          {lastUpdate && <span className="text-sm text-muted-foreground">更新于 {lastUpdate}</span>}
          {/* 自动刷新开关: 交易日固定时点触发(非 30s 间隔) */}
          <button
            type="button"
            onClick={() => setAutoRefresh((v) => !v)}
            title={autoRefresh
              ? "盘中自动刷新已开启: 交易日 09:32 / 10:00 / 10:30 / 11:00 / 11:30 / 13:30 / 14:00 / 14:30 / 14:58 各刷新一次; 点击关闭"
              : "盘中自动刷新已关闭, 点击开启(交易日固定时点刷新)"}
            className={
              "shrink-0 rounded-md border px-2 py-1 text-xs font-medium transition " +
              (autoRefresh
                ? "border-primary/30 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-muted/40")
            }
          >
            {autoRefresh ? "盘中自动刷新" : "盘中自动刷新 关"}
          </button>
          <RefreshBtn onClick={refreshAndCycle} loading={fetching} title="立即刷新自选行情(刷新完成后自动更新下方个股速评)" />
        </div>
      }
    />
  );

  // 领涨/领跌 Top3 迷你 chips（名称 + 涨跌幅，涨跌分别着色）
  const moverRow = (list: WatchStock[], up: boolean) => (
    <span className="flex min-w-0 items-center gap-1">
      <span className="shrink-0 text-muted-foreground">{up ? "领涨" : "领跌"}</span>
      {list.map((s, i) => (
        <span key={s.code} className="flex min-w-0 items-center gap-0.5">
          {i > 0 && <span className="text-muted-foreground/40">·</span>}
          <span className={`truncate ${up ? "text-red-500" : "text-green-600"}`} title={`${s.name} ${fmtPct(s.change_pct)}`}>
            <span className="max-w-[4.5rem] truncate font-medium align-baseline">{s.name}</span>
            <span className="tabular-nums">{fmtPct(s.change_pct)}</span>
          </span>
        </span>
      ))}
    </span>
  );

  // ── 板块总览层：市场宽度摘要 + 热力按钮网格，点击进入该板块 ──
  const shellCls = "scroll-mt-28" + (flush ? "" : " rounded-xl border bg-card");
  if (activeSector === null) {
    return (
      <div id="overview-watchlist" className={shellCls}>
        {header}
        {/* 市场宽度摘要条：涨跌平只数 + 平均涨跌 + 领涨/领跌 Top3 */}
        {width && (
          <div className="px-4 pt-3">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg bg-muted/40 px-4 py-2.5 text-[15px]">
              <span>
                全市场 <b className="text-base font-bold text-foreground">{width.total} 只</b>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="font-bold tabular-nums text-red-500">{width.up}涨</span>
                <span className="text-muted-foreground/40">/</span>
                <span className="font-bold tabular-nums text-green-600">{width.down}跌</span>
                <span className="text-muted-foreground/40">/</span>
                <span className="tabular-nums text-muted-foreground">{width.flat}平</span>
              </span>
              <span className={cc(width.avg)} title="全市场平均涨跌幅">
                平均 {fmtPct(width.avg)}
              </span>
              {width.top.length > 0 && (
                <span className="flex min-w-0 items-center gap-3">
                  {moverRow(width.top, true)}
                  {moverRow(width.bottom, false)}
                </span>
              )}
              <span className="shrink-0 text-[10px] text-muted-foreground/70">
                色块深浅 = 板块平均涨跌幅度
              </span>
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 gap-2 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {order.map((sector) => {
            const codes = sectors[sector] || [];
            const { avg, up, down } = statOf(codes);
            return (
              <button
                key={sector}
                type="button"
                onClick={() => setView(sector)}
                className="group flex w-full items-center justify-between gap-2 rounded-xl border bg-card px-3 py-3 text-left transition hover:border-primary/40 hover:brightness-[0.97]"
                style={heatBg(avg) ? { backgroundColor: heatBg(avg) } : undefined}
                title={`${sector} 平均${avg != null ? fmtPct(avg) : "—"}（点击查看个股）`}
              >
                {/* 单行：板块名 + 只数 + 涨跌只数 | 平均涨跌 + 进入箭头 */}
                <span className="flex min-w-0 items-baseline gap-1.5">
                  <span className="truncate text-base font-bold">{sector}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{codes.length} 只</span>
                  <span className="flex shrink-0 items-center gap-1 text-xs leading-none">
                    <span className="font-semibold tabular-nums text-red-500">{up}涨</span>
                    <span className="text-muted-foreground/50">/</span>
                    <span className="font-semibold tabular-nums text-green-600">{down}跌</span>
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  {avg != null && (
                    <span className={`text-sm font-bold tabular-nums ${cc(avg)}`} title="板块平均涨跌幅">
                      {avg >= 0 ? "+" : ""}
                      {avg.toFixed(2)}%
                    </span>
                  )}
                  <ChevronRight className="h-4 w-4 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5" />
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // ── 单板块视图：全宽股票表（完整列 + 固定表头） ──
  const codes = sectors[activeSector] || [];
  const { avg, up, down } = statOf(codes);
  return (
    <div id="overview-watchlist" className={shellCls}>
      {header}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <button
          type="button"
          onClick={() => setView("overview")}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-base font-semibold text-muted-foreground transition hover:bg-muted/40 hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          返回板块总览
        </button>
        <span className="flex items-baseline gap-2.5">
          <span className="text-base font-bold">{activeSector}</span>
          <span className="text-xs text-muted-foreground">{codes.length} 只</span>
          {avg != null && (
            <span className={`text-sm font-semibold tabular-nums ${cc(avg)}`} title="板块平均涨跌幅">
              板块平均 {avg >= 0 ? "+" : ""}
              {avg.toFixed(2)}%
            </span>
          )}
          <span className="flex items-center gap-1 text-xs">
            <span className="font-semibold tabular-nums text-red-500">{up}涨</span>
            <span className="text-muted-foreground/60">/</span>
            <span className="font-semibold tabular-nums text-green-600">{down}跌</span>
          </span>
        </span>
        <span className="w-28" />
      </div>
      <div className="max-h-[520px] overflow-x-auto overflow-y-auto p-2">
        {/* 表头（15px 数据对应 13px 表头） */}
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-card px-3 py-2 text-[13px] font-semibold text-muted-foreground">
          <span className="w-[4.5rem] shrink-0">代码</span>
          <span className="min-w-0 flex-1">名称</span>
          <span className="w-20 shrink-0 text-right">最新</span>
          <span className="w-20 shrink-0 text-right">涨跌幅</span>
          <span className="w-20 shrink-0 text-right">今开</span>
          <span className="w-20 shrink-0 text-right">最高</span>
          <span className="w-20 shrink-0 text-right">最低</span>
          <span className="w-20 shrink-0 text-right">昨收</span>
          <span className="w-24 shrink-0 text-right">成交量</span>
          <span className="w-20 shrink-0 text-right">换手</span>
          <span className="w-24 shrink-0 text-right">成交额</span>
          <span className="w-24 shrink-0 text-right">主力</span>
        </div>
        <div className="min-w-[1180px] divide-y divide-border/40">
          {codes.map((code) => {
            const s = data[code];
            if (!s) {
              return (
                <div key={code} className="flex items-center gap-2 px-3 py-3 text-[15px] text-muted-foreground">
                  <span className="w-[4.5rem] shrink-0 tabular-nums">{code}</span>
                  <span className="min-w-0 flex-1 truncate">加载中…</span>
                </div>
              );
            }
            const flow = flows[code];
            return (
              <div key={code} className="flex items-center gap-2 px-3 py-3 text-[15px] hover:bg-muted/20">
                <span className="w-[4.5rem] shrink-0 tabular-nums text-muted-foreground">{s.code}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{s.name}</span>
                <span className="w-20 shrink-0 text-right tabular-nums">{s.price > 0 ? s.price.toFixed(2) : "-"}</span>
                <span className={`w-20 shrink-0 text-right font-medium tabular-nums ${cc(s.change_pct)}`}>
                  {s.price === 0 ? "" : (s.change_pct > 0 ? "+" : "") + s.change_pct.toFixed(2) + "%"}
                </span>
                <span className="w-20 shrink-0 text-right tabular-nums text-muted-foreground">{fmtPx(s.open)}</span>
                <span className={`w-20 shrink-0 text-right tabular-nums ${(s.high ?? 0) > s.price ? "text-red-500" : "text-muted-foreground"}`}>{fmtPx(s.high)}</span>
                <span className={`w-20 shrink-0 text-right tabular-nums ${(s.low ?? 0) > 0 && (s.low ?? 0) < s.price ? "text-green-600" : "text-muted-foreground"}`}>{fmtPx(s.low)}</span>
                <span className="w-20 shrink-0 text-right tabular-nums text-muted-foreground">{fmtPx(s.last_close)}</span>
                <span className="w-24 shrink-0 text-right tabular-nums text-muted-foreground">{fmtVol(s.volume)}</span>
                <span className="w-20 shrink-0 text-right tabular-nums text-muted-foreground">{(s.turnover_pct || 0).toFixed(2)}%</span>
                <span className="w-24 shrink-0 text-right tabular-nums text-muted-foreground">{fmtAmt(s.amount_yi)}</span>
                <span className={`w-24 shrink-0 text-right tabular-nums ${flow == null ? "text-muted-foreground" : flow >= 0 ? "text-red-500" : "text-green-500"}`}>
                  {fmtFlow(flow)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
