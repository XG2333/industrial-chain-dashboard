import { useCallback, useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";

// 主力期货总体分析: 显示在总览第一行(现货/主力 KPI)下方。
// 输入 = 实时行情(KPI) + 当日分时 + 日K窗口(近5/10/20/60日) + 主力合约成交量与持仓量(资金参与),
// 走 /api/sector/quick-analysis(kind=market_overview); 结果按行业缓存。

interface KpiItem {
  key: string;
  label: string;
  value: number;
  change_pct: number | null;
  date: string;
}
interface KpiGroup {
  dataset: string;
  label: string;
  items: KpiItem[];
}

interface MinutePoint {
  t: string;
  v: number;
}
interface Kline {
  d: string;
  c: number;
}
interface MarketData {
  ok: boolean;
  prev_close: number | null;
  date?: string;
  interval?: string;
  minute: MinutePoint[];
  daily: Kline[];
}

interface PosRow {
  contract: string;
  price: number | null;
  vol: number | null;
  oi: number | null;
  ratio: number | null;
  turnover: number | null;
  d_vol: number | null;
  d_oi: number | null;
}
interface PosGroup {
  product: string;
  rows: PosRow[];
}
interface PosData {
  ok: boolean;
  groups: PosGroup[];
}

interface QuickPoint {
  metric: string;
  change: string;
  comment: string;
}
interface QuickAnalysis {
  verdict: string;
  points: QuickPoint[];
  outlook: string;
  raw?: string;
  asof: string;
}

const pct = (a: number, b: number) => (b ? ((a / b - 1) * 100).toFixed(2) + "%" : "—");
const signed = (v: number) => (v > 0 ? "+" : "") + v.toFixed(2) + "%";

function buildSummary(kpi: KpiGroup, market: MarketData, pos: PosData | null): string[] {
  const lines: string[] = [];
  const name = kpi.label || kpi.dataset;
  const future = kpi.items.find((i) => i.key === "future");
  const spot = kpi.items.find((i) => i.key === "spot");
  const price = future?.value ?? spot?.value;
  lines.push(`# 主力期货总体分析 ${name} · 实时行情截至 ${future?.date || ""}`);
  if (future) {
    lines.push(`现价 ${Math.round(future.value)} 涨跌 ${future.change_pct == null ? "—" : signed(future.change_pct)}% (${future.label})`);
  }
  // 当日分时统计(相对昨结/区间)
  const minute = market?.minute ?? [];
  if (minute.length >= 2) {
    let hi = minute[0], lo = minute[0];
    for (const p of minute) {
      if (p.v > hi.v) hi = p;
      if (p.v < lo.v) lo = p;
    }
    const last = minute[minute.length - 1].v;
    const prevC = market.prev_close;
    const span = hi.v - lo.v || 1;
    const posPct = Math.round(((last - lo.v) / span) * 100);
    lines.push(`当日分时: 区间 高${Math.round(hi.v)}(${hi.t}) 低${Math.round(lo.v)}(${lo.t}) 现价位于区间 ${posPct}% 位; 昨结 ${prevC != null ? Math.round(prevC) : "—"}`);
  }
  // 日K窗口
  const daily = market?.daily ?? [];
  if (daily.length >= 25) {
    const closes = daily.map((k) => k.c);
    const lastC = closes[closes.length - 1];
    const w = (n: number) => (closes.length > n ? pct(lastC, closes[closes.length - 1 - n]) : "—");
    lines.push(`日K窗口: 近5日 ${w(5)} · 近10日 ${w(10)} · 近20日 ${w(20)}`);
    const seg = daily.slice(-60);
    const hi60 = Math.max(...seg.map((k) => k.c));
    const lo60 = Math.min(...seg.map((k) => k.c));
    lines.push(`近60日区间: 高 ${Math.round(hi60)} 低 ${Math.round(lo60)}; 现价距区间高 ${(((lastC - hi60) / hi60) * 100).toFixed(1)}% 距低 ${(((lastC - lo60) / lo60) * 100).toFixed(1)}%`);
    lines.push("近10日收盘: " + daily.slice(-10).map((k) => `${k.d.slice(5)}:${Math.round(k.c)}`).join(" "));
  }
  // 主力持仓 = 实时表持仓量最大合约 → 资金参与(近似): 期货无官方资金净流入口径,
  // 用 成交额 + 成交量/持仓量较前一日增减 供 AI 推断资金进出倾向
  if (pos?.groups?.length) {
    for (const g of pos.groups) {
      const main = g.rows.reduce((a, b) => ((b.oi ?? -1) > (a.oi ?? -1) ? b : a), g.rows[0]);
      if (main) {
        const mv = main.vol != null ? Math.round(main.vol).toLocaleString("zh-CN") : "—";
        const mo = main.oi != null ? Math.round(main.oi).toLocaleString("zh-CN") : "—";
        const dvs = main.d_vol == null ? "—" : (main.d_vol > 0 ? "+" : "") + Math.round(main.d_vol).toLocaleString("zh-CN");
        const dos = main.d_oi == null ? "—" : (main.d_oi > 0 ? "+" : "") + Math.round(main.d_oi).toLocaleString("zh-CN");
        const ratio = main.ratio != null ? (main.ratio * 100).toFixed(1) + "%" : "—";
        const to = main.turnover != null
          ? main.turnover >= 1e8 ? (main.turnover / 1e8).toFixed(2) + "亿" : (main.turnover / 1e4).toFixed(1) + "万"
          : "—";
        lines.push(
          `主力合约资金参与(${g.product} ${main.contract}): 当日成交额约 ${to}; 成交量 ${mv}手(较前一日 ${dvs}手); ` +
          `持仓量 ${mo}手(较前一日 ${dos}手); 成交持仓比 ${ratio}`
        );
      }
    }
  }
  return lines;
}

export function KpiFutureAnalysis({ dataset, flush = false }: { dataset: string; flush?: boolean }) {
  const cacheKey = `future_analysis_v2_${dataset}`;
  const [analysis, setAnalysis] = useState<QuickAnalysis | null>(() => {
    try {
      const r = localStorage.getItem(cacheKey);
      if (r) return JSON.parse(r) as QuickAnalysis;
    } catch {
      /* ignore */
    }
    return null;
  });
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [basisText, setBasisText] = useState("");
  const [showBasis, setShowBasis] = useState(false);
  const snapRef = useRef<{ summary: string[]; asof: string } | null>(null);

  // 并行辅助: 任一源失败返回 null(小节自动跳过, 不阻塞整体)
  const fetchJ = async (url: string, body?: unknown): Promise<unknown> => {
    try {
      const r = await fetch(
        url,
        body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined,
      );
      return r.ok ? await r.json() : null;
    } catch {
      return null;
    }
  };
  const flowOf = (f: unknown): number | null => {
    if (typeof f === "number") return f;
    if (f && typeof f === "object") {
      const o = f as Record<string, unknown>;
      const v = o.main_net ?? o.net ?? o.value ?? o.net_inflow;
      return typeof v === "number" ? v : null;
    }
    return null;
  };

  const prepare = useCallback(async (): Promise<{ summary: string[]; asof: string } | null> => {
    try {
      const [kpiR, mktR, posR, tgtR, wrR] = await Promise.all([
        fetch("/api/industry/kpi").then((r) => (r.ok ? r.json() : null)),
        fetch(`/api/industry/future-market?dataset=${dataset}`).then((r) => (r.ok ? r.json() : null)),
        fetch(`/api/industry/positions-live?dataset=${dataset}`).then((r) => (r.ok ? r.json() : null)),
        fetchJ("/api/stock-targets"),
        fetchJ(`/api/warehouse-table-live?dataset=${dataset}`),
      ]);
      const kpi = (kpiR?.groups || []).find((g: KpiGroup) => g.dataset === dataset);
      const mkt: MarketData = mktR || { ok: false, minute: [], daily: [] };
      const pos: PosData | null = posR?.ok ? posR : null;
      if (!kpi || !kpi.items?.length) return null;
      const summary = buildSummary(kpi, mkt, pos);

      // ── 相关股票与主力资金 ──
      const tgr = tgtR as { groups?: Record<string, { 总览?: string[] }> } | null;
      const codes = (tgr?.groups?.[dataset]?.总览 || []).slice(0, 16);
      if (codes.length) {
        const [watchR, flowR] = await Promise.all([
          fetchJ("/api/watchlist", { stocks: codes }),
          fetchJ("/api/stocks/flow", { stocks: codes }),
        ]);
        const stocks = ((watchR as { stocks?: { code: string; name?: string; change_pct?: number }[] } | null)?.stocks || [])
          .filter((s) => typeof s.change_pct === "number") as { code: string; name?: string; change_pct: number }[];
        if (stocks.length) {
          const up = stocks.filter((s) => s.change_pct > 0).length;
          const avg = Math.round((stocks.reduce((a, s) => a + s.change_pct, 0) / stocks.length) * 100) / 100;
          const byChg = [...stocks].sort((a, b) => b.change_pct - a.change_pct);
          const tag = (s: { code: string; name?: string }) => s.name || s.code;
          summary.push(`相关股票(${stocks.length}只样本): 涨${up} 跌${stocks.length - up} 平均${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%`);
          summary.push(`涨幅居前: ${byChg.slice(0, 3).map((s) => `${tag(s)} ${s.change_pct.toFixed(2)}%`).join("  ")}`);
          summary.push(`跌幅居前: ${byChg.slice(-3).reverse().map((s) => `${tag(s)} ${s.change_pct.toFixed(2)}%`).join("  ")}`);
        }
        const flowList = Object.entries(((flowR as { flows?: Record<string, unknown> } | null)?.flows) || {})
          .map(([code, f]) => ({ code, v: flowOf(f) }))
          .filter((x): x is { code: string; v: number } => x.v != null)
          .sort((a, b) => b.v - a.v);
        if (flowList.length) {
          summary.push(`主力净流入居前(亿): ${flowList.slice(0, 5).map((x) => `${x.code} ${x.v >= 0 ? "+" : ""}${x.v.toFixed(2)}`).join("  ")}`);
        }
      }

      // ── 交易所仓单(公开) ──
      const wrRows = (((wrR as { rows?: unknown[] } | null)?.rows) || []) as {
        kind?: string; warehouse?: string; values?: (number | null)[]; daily_change?: number | null;
      }[];
      const wrTotal = wrRows.find((r) => r.kind === "total" && r.warehouse === "全国仓单量");
      if (wrTotal && wrTotal.values?.[0] != null) {
        const d = wrTotal.daily_change;
        summary.push(`交易所仓单(公开): 全国 ${Math.round(wrTotal.values[0]).toLocaleString("zh-CN")} 手, 日增减 ${d == null ? "—" : d > 0 ? "+" + d.toLocaleString("zh-CN") : d.toLocaleString("zh-CN")}`);
      }
      const wrTop = wrRows
        .filter((r) => r.kind === "warehouse" && r.daily_change != null && r.daily_change !== 0)
        .sort((a, b) => (b.daily_change ?? 0) - (a.daily_change ?? 0))
        .slice(0, 3);
      if (wrTop.length) {
        summary.push(`仓单变动前3: ${wrTop.map((r) => `${r.warehouse} ${(r.daily_change ?? 0) > 0 ? "+" : ""}${Math.round(r.daily_change ?? 0)}`).join("  ")}`);
      }

      const asof = mkt?.date || kpi.items[0]?.date || "";
      setReady(true);
      snapRef.current = { summary, asof };
      return snapRef.current;
    } catch {
      return null;
    }
  }, [dataset]);

  useEffect(() => {
    void prepare();
  }, [prepare]);

  const runRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    const h = () => {
      void runRef.current();
    };
    quickAnalysisBus.onRun(cacheKey, h);
    return () => quickAnalysisBus.offRun(cacheKey, h);
  }, [cacheKey]);

  const run = async () => {
    setLoading(true);
    setError(null);
    // 每次触发都重新拉取最新行情构造输入(与第一行 KPI 同步), 避免用挂载时的旧快照
    let snap = await prepare();
    if (!snap) {
      // 数据接口瞬时失败: 短重试(最多 6s)
      const startedAt = Date.now();
      while (!snap && Date.now() - startedAt < 6000) {
        await new Promise((r) => setTimeout(r, 400));
        snap = await prepare();
      }
    }
    if (!snap) {
      setLoading(false);
      setError("暂无实时行情数据");
      return;
    }
    try {
      const r = await fetch("/api/sector/quick-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: dataset,
          sector: `${dataset === "lithium" ? "碳酸锂" : dataset === "tin" ? "沪锡" : "工业硅/多晶硅"}主力期货`,
          kind: "market_overview",
          metrics_text: snap.summary.join("\n"),
        }),
      });
      if (!r.ok) {
        let detail = `请求失败 (${r.status})`;
        try {
          const e = await r.json();
          if (e?.detail) detail = String(e.detail);
        } catch {
          /* keep status */
        }
        throw new Error(detail);
      }
      const res = await r.json();
      const saved: QuickAnalysis = {
        verdict: res.verdict || "",
        points: Array.isArray(res.points) ? res.points : [],
        outlook: res.outlook || "",
        raw: res.raw || "",
        asof: snap.asof,
      };
      setAnalysis(saved);
      setBasisText(snap.summary.join("\n"));
      try {
        localStorage.setItem(cacheKey, JSON.stringify(saved));
      } catch {
        /* ignore */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
      quickAnalysisBus.done(cacheKey);
    }
  };
  runRef.current = run;

  return (
    <div className={flush ? "" : "rounded-xl border bg-card"}>
      {flush ? (
        // 融合模式: 与上方 KPI 行同一白卡, 无独立按钮(刷新由第一行统一驱动)
        <div className="px-4 pt-3">
          <span className="text-lg font-bold text-foreground">主力期货总体分析</span>
        </div>
      ) : (
        <CardHeader
          title="主力期货总体分析"
          action={
            <Button variant="outline" size="sm" onClick={run} disabled={loading || !ready}>
              {loading ? "分析中…" : analysis ? "重新分析" : "AI 分析"}
            </Button>
          }
        />
      )}
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            基于实时盘面(现价/涨跌/分时区间)、日K窗口(近5/10/20/60日)与主力合约资金参与(成交额与成交量/持仓量增减),生成总体点评
            {flush ? " · 点击上方「刷新」同步更新" : ""}
          </p>
        )}
        {error && <p className="py-1 text-xs text-red-500">AI 分析失败：{error}</p>}
        {analysis && (
          <div className="space-y-3">
            {analysis.raw ? (
              <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-slate-700">{analysis.raw}</p>
            ) : (
              <>
                {analysis.verdict && (
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-[15px] font-semibold leading-relaxed text-foreground">{analysis.verdict}</p>
                  </div>
                )}
                {analysis.points.length > 0 && (
                  <ul className="space-y-1.5">
                    {analysis.points.map((p, i) => (
                      <li key={i} className="flex items-baseline gap-2 text-[15px] leading-relaxed">
                        <span className="shrink-0 select-none font-bold text-primary">{i + 1}.</span>
                        <span className="shrink-0 font-medium text-foreground">{p.metric}</span>
                        <span className="shrink-0 tabular-nums">
                          {colorParts(p.change).map((seg, si) => (
                            <span key={si} className={seg.cls}>{seg.text}</span>
                          ))}
                        </span>
                        <span className="text-muted-foreground">{p.comment}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {analysis.outlook && (
                  <div className="flex items-baseline gap-2 border-t border-border/70 pt-2">
                    <span className="shrink-0 text-xs font-bold tracking-widest text-muted-foreground">前瞻</span>
                    <p className="text-[15px] leading-relaxed text-foreground/90">{analysis.outlook}</p>
                  </div>
                )}
              </>
            )}
            {basisText && (
              <div className="border-t border-border/60 pt-1.5">
                <button
                  onClick={() => setShowBasis((v) => !v)}
                  className="text-[11px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
                >
                  {showBasis ? "收起数据依据" : "查看数据依据"}
                </button>
                {showBasis && (
                  <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[10px] leading-relaxed text-muted-foreground">
                    {basisText}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
