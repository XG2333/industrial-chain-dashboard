import { useCallback, useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { CardHeader } from "@/components/ui/CardHeader";

// 成交持仓速评：显示在「各合约成交持仓」表格下方。
// 基于表格数据（主力/各月份合约的量/仓/价/比/额 + 日增减）调 DeepSeek 生成点评，
// 与仓单速评同一后端端点（kind=positions），结果按行业缓存到 localStorage。

interface PositionRow {
  contract: string;
  date?: string | null;
  price: number | null;
  vol: number | null;
  oi: number | null;
  ratio: number | null;
  turnover: number | null;
  d_vol: number | null;
  d_oi: number | null;
}

interface PositionGroup {
  product: string;
  date?: string;
  rows: PositionRow[];
}

interface PositionsData {
  ok: boolean;
  groups: PositionGroup[];
}

// 各机构成交持仓（交易所会员排名, 收盘后日度; 供速评第二输入部分）
interface InstRow {
  rank: number;
  vol_member: string;
  vol: number | null;
  vol_chg: number | null;
  long_member: string;
  long_oi: number | null;
  long_chg: number | null;
  short_member: string;
  short_oi: number | null;
  short_chg: number | null;
}

interface InstGroup {
  product: string;
  contract: string;
  date?: string;
  rows: InstRow[];
}

interface InstData {
  ok: boolean;
  groups: InstGroup[];
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

// 压缩摘要（省 token）：单位/说明只出现一次；成交量与持仓量为整数、增减带符号、比与额按表格口径。
const fmtSigned = (v: number | null): string => {
  if (v == null) return "";
  const s = v >= 0 ? "+" : "";
  return s + (Math.abs(v) >= 10000 ? (v / 10000).toFixed(1) + "万" : String(Math.round(v)));
};

const fmtFund = (v: number | null): string => {
  if (v == null) return "—";
  if (v >= 1e8) return (v / 1e8).toFixed(2) + "亿";
  if (v >= 1e4) return (v / 1e4).toFixed(1) + "万";
  return String(Math.round(v));
};

function buildLines(data: PositionsData): string[] {
  const lines: string[] = [];
  for (const g of data.groups ?? []) {
    const date = g.rows.find((r) => r.date)?.date ?? "";
    lines.push(
      `# 各合约成交持仓 ${(date || "").slice(5)}（单位: 手; 成交额=成交量×最新价×合约乘数(吨/手)近似; ` +
        `增减=最新 vs 前一日; 成交持仓比=当日成交量/持仓量 百分数）`
    );
    break; // 说明行只写一次
  }
  for (const g of data.groups ?? []) {
    // 主力 = 持仓量最大的合约(实时)/标题"主力"行(Excel 兜底)
    const main =
      g.rows.reduce((a, b) => ((b.oi ?? -1) > (a.oi ?? -1) ? b : a), g.rows[0]).contract ?? "";
    lines.push(`【${g.product}】共 ${g.rows.length} 个合约`);
    for (const r of g.rows) {
      const p = r.price != null ? String(Math.round(r.price)) : "—";
      const vol = r.vol != null ? String(Math.round(r.vol)) + `(${fmtSigned(r.d_vol)})` : "—";
      const oi = r.oi != null ? String(Math.round(r.oi)) + `(${fmtSigned(r.d_oi)})` : "—";
      const ratio = r.ratio != null ? (r.ratio * 100).toFixed(1) + "%" : "—";
      const to = r.turnover != null ? fmtFund(r.turnover) : "—";
      const tag = r.contract === main ? `主力(${r.contract})` : r.contract;
      lines.push(`${tag} ${p} | 成交量${vol} 持仓量${oi} 成交持仓比${ratio} 成交额${to}`);
    }
  }
  return lines;
}

// 机构会员持仓摘要（三栏独立排名; 与 server kind=positions 提示词的"第二部分"格式一致）
function buildInstLines(data: InstData | null): string[] {
  const lines: string[] = [];
  if (!data || data.groups?.length === 0) return lines;
  const date = data.groups[0]?.date ?? "";
  lines.push(`# 各机构成交持仓 ${date}（交易所会员持仓排名, 收盘后公布; 成交量/多头持仓/空头持仓三栏独立排名）`);
  for (const g of data.groups) {
    lines.push(`【${g.product} 主力 ${g.contract}】`);
    for (const r of g.rows.slice(0, 12)) {
      const v = r.vol != null ? String(Math.round(r.vol)) + (r.vol_chg != null ? `(${fmtSigned(r.vol_chg)})` : "") : "—";
      const l = r.long_oi != null ? String(Math.round(r.long_oi)) + (r.long_chg != null ? `(${fmtSigned(r.long_chg)})` : "") : "—";
      const s = r.short_oi != null ? String(Math.round(r.short_oi)) + (r.short_chg != null ? `(${fmtSigned(r.short_chg)})` : "") : "—";
      lines.push(`${r.rank} 成交量:${r.vol_member} ${v} | 多头持仓:${r.long_member} ${l} | 空头持仓:${r.short_member} ${s}`);
    }
  }
  return lines;
}

export function PositionQuickAnalysis({ dataset }: { dataset: string }) {
  const cacheKey = `positions_analysis_v2_${dataset}`;
  const [analysis, setAnalysis] = useState<QuickAnalysis | null>(() => {
    try {
      const r = localStorage.getItem(cacheKey);
      if (r) return JSON.parse(r) as QuickAnalysis;
    } catch {
      /* ignore */
    }
    return null;
  });
  const [data, setData] = useState<PositionsData | null>(null);
  const [inst, setInst] = useState<InstData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [basisText, setBasisText] = useState("");
  const [showBasis, setShowBasis] = useState(false);

  const fetchData = useCallback(async (): Promise<PositionsData | null> => {
    // 实时(新浪)优先, 失败回退 Excel 目录
    for (const url of [
      `/api/industry/positions-live?dataset=${dataset}`,
      `/api/industry/positions?dataset=${dataset}`,
    ]) {
      try {
        const r = await fetch(url);
        if (!r.ok) continue;
        const d = (await r.json()) as PositionsData;
        if (d?.ok && d.groups?.length > 0) {
          setData(d);
          return d;
        }
      } catch {
        /* try next */
      }
    }
    return null;
  }, [dataset]);

  // 机构会员持仓(交易所排名, 收盘后日度) — 供速评第二部分; 拉取失败不阻塞分析
  const fetchInst = useCallback(async (): Promise<InstData | null> => {
    try {
      const r = await fetch(`/api/industry/institution-positions?dataset=${dataset}`);
      if (!r.ok) return null;
      const d = (await r.json()) as InstData;
      if (d?.ok && d.groups?.length > 0) {
        setInst(d);
        return d;
      }
      return null;
    } catch {
      return null;
    }
  }, [dataset]);

  useEffect(() => {
    void fetchData();
    void fetchInst();
  }, [fetchData, fetchInst]);

  const runRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    const h = () => {
      void runRef.current();
    };
    quickAnalysisBus.onRun(cacheKey, h);
    return () => quickAnalysisBus.offRun(cacheKey, h);
  }, [cacheKey]);

  const asof =
    data?.groups?.find((g) => g.rows.find((r) => r.date))?.rows.find((r) => r.date)?.date ?? "";

  const run = async () => {
    // 每次触发都重新拉取最新数据(与上方合约/机构刷新同步), 避免用挂载时的旧快照
    let d = await fetchData();
    let i = await fetchInst();
    const startedAt = Date.now();
    while ((!d || d.groups.length === 0) && Date.now() - startedAt < 5000) {
      await new Promise((r) => setTimeout(r, 400));
      d = await fetchData();
    }
    if (!d || d.groups.length === 0) {
      setError("暂无成交持仓数据");
      return;
    }
    const lines = buildLines(d).concat(buildInstLines(i));
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/sector/quick-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: dataset,
          sector: "各合约成交持仓",
          kind: "positions",
          metrics_text: lines.join("\n"),
        }),
      });
      if (!r.ok) {
        let detail = `请求失败 (${r.status})`;
        try {
          const e = await r.json();
          if (e?.detail) detail = String(e.detail);
        } catch {
          /* keep status fallback */
        }
        throw new Error(detail);
      }
      const res = await r.json();
      const saved: QuickAnalysis = {
        verdict: res.verdict || "",
        points: Array.isArray(res.points) ? res.points : [],
        outlook: res.outlook || "",
        raw: res.raw || "",
        asof,
      };
      setAnalysis(saved);
      setBasisText(lines.join("\n"));
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
    <div className="mt-3 rounded-xl border bg-card">
      {/* 无独立按钮: 由上方「各合约成交持仓」刷新按钮联动更新 */}
      <CardHeader title="成交持仓速评" />
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            基于上方各合约成交量与持仓量数据及机构会员持仓排名（多空头部席位与增减）生成简洁点评 · 点击上方「刷新」同步更新
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
