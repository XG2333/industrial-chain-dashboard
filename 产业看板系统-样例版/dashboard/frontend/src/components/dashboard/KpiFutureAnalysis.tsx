import { useCallback, useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";

// 主力期货总体分析: 显示在总览第一行(现货/主力 KPI)下方。
// 输入 = 实时行情(KPI) + 当日分时 + 日K窗口(近5/10/20/60日) + 主力合约量仓,
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
  // 主力持仓(实时表持仓最大合约)
  if (pos?.groups?.length) {
    for (const g of pos.groups) {
      const main = g.rows.reduce((a, b) => ((b.oi ?? -1) > (a.oi ?? -1) ? b : a), g.rows[0]);
      if (main) {
        lines.push(`主力持仓(${g.product} ${main.contract}): 量${main.vol != null ? Math.round(main.vol) : "—"} 仓${main.oi != null ? Math.round(main.oi) : "—"} 成交持仓比${main.ratio != null ? (main.ratio * 100).toFixed(1) + "%" : "—"}`);
      }
    }
  }
  return lines;
}

export function KpiFutureAnalysis({ dataset }: { dataset: string }) {
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

  const prepare = useCallback(async (): Promise<{ summary: string[]; asof: string } | null> => {
    try {
      const [kpiR, mktR, posR] = await Promise.all([
        fetch("/api/industry/kpi").then((r) => (r.ok ? r.json() : null)),
        fetch(`/api/industry/future-market?dataset=${dataset}`).then((r) => (r.ok ? r.json() : null)),
        fetch(`/api/industry/positions-live?dataset=${dataset}`).then((r) => (r.ok ? r.json() : null)),
      ]);
      const kpi = (kpiR?.groups || []).find((g: KpiGroup) => g.dataset === dataset);
      const mkt: MarketData = mktR || { ok: false, minute: [], daily: [] };
      const pos: PosData | null = posR?.ok ? posR : null;
      if (!kpi || !kpi.items?.length) return null;
      const summary = buildSummary(kpi, mkt, pos);
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
    let snap = snapRef.current;
    if (!snap) {
      setError(null);
      const startedAt = Date.now();
      while (!snap && Date.now() - startedAt < 6000) {
        snap = await prepare();
        if (snap) break;
        await new Promise((r) => setTimeout(r, 300));
      }
    }
    if (!snap) {
      setError("暂无实时行情数据");
      return;
    }
    setLoading(true);
    setError(null);
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
    <div className="rounded-xl border bg-card">
      <CardHeader
        title="主力期货总体分析"
        action={
          <Button variant="outline" size="sm" onClick={run} disabled={loading || !ready}>
            {loading ? "分析中…" : analysis ? "重新分析" : "AI 分析"}
          </Button>
        }
      />
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            基于实时盘面(现价/涨跌/分时区间)与日K窗口(近5/10/20/60日)及主力量仓,生成总体点评
          </p>
        )}
        {error && <p className="py-1 text-xs text-red-500">AI 分析失败：{error}</p>}
        {analysis && (
          <div className="space-y-3">
            {analysis.raw ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{analysis.raw}</p>
            ) : (
              <>
                {analysis.verdict && (
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-sm font-semibold leading-relaxed text-foreground">{analysis.verdict}</p>
                  </div>
                )}
                {analysis.points.length > 0 && (
                  <ul className="space-y-1.5">
                    {analysis.points.map((p, i) => (
                      <li key={i} className="flex items-baseline gap-2 text-sm leading-relaxed">
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
                    <p className="text-sm leading-relaxed text-foreground/90">{analysis.outlook}</p>
                  </div>
                )}
              </>
            )}
            {analysis.asof && (
              <p className="text-[11px] text-muted-foreground">
                数据截至 {analysis.asof.replace(/-/g, "/")} · 缓存于本机，点击「重新分析」更新
              </p>
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
