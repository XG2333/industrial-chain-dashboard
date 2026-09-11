import { useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { CardHeader } from "@/components/ui/CardHeader";

// 个股速评(自选股票下方, 参考仓单/成交持仓速评): 输入 = 自选卡现成的分组+实时行情+主力资金,
// 输出整体速评 + 分板块明细两段; 走 /api/sector/quick-analysis(kind=stock_overview), 结果按行业缓存。

interface WatchStock {
  code: string;
  name: string;
  price: number;
  change_pct: number;
}
interface StockQuickResult {
  overall: string;
  sectors: { name: string; change: string; comment: string }[];
  raw?: string;
  asof: string;
}

// 板块行评语按「领涨/领跌/短线」拆成带标签的分段(涨红/跌绿/短线灰, 段间留明显间距);
// AI 未按三段式输出时整句按正文灰显示
interface CommentPart {
  label: string; // 领涨|领跌|短线|""(无标签正文)
  cls: string;
  body: string;
}
// 按 领涨/领跌/短线/前瞻 标签切段(带可选冒号), 标签段分别 红/绿/灰 染色; 无标签前缀正文照常灰显
function commentParts(comment: string): CommentPart[] {
  const parts: CommentPart[] = [];
  const raw = comment.split(/(领涨|领跌|短线|前瞻)[:：]?/);
  let head = (raw[0] || "").trim();
  if (head) parts.push({ label: "", cls: "text-muted-foreground", body: head });
  for (let i = 1; i + 1 < raw.length; i += 2) {
    const label = raw[i];
    const body = (raw[i + 1] || "").replace(/^[;；\s]+/, "").replace(/[;；\s]+$/, "");
    if (!body) continue;
    parts.push({
      label,
      cls: label === "领涨" ? "text-red-600" : label === "领跌" ? "text-green-600" : "text-muted-foreground",
      body,
    });
  }
  if (!parts.length) parts.push({ label: "", cls: "text-muted-foreground", body: comment });
  return parts;
}

const fmtPct = (v: number) => (v > 0 ? "+" : "") + v.toFixed(2) + "%";

export function StockQuickAnalysis({
  dataset,
  order,
  sectors,
  codes,
  data,
  flows,
  flush = false,
}: {
  dataset: string;
  order: string[];
  sectors: Record<string, string[]>;
  codes: string[];
  data: Record<string, WatchStock>;
  flows: Record<string, number | null>;
  // flush: 不自带卡壳(与自选股票共用外层白卡, 视觉连成一体)
  flush?: boolean;
}) {
  const cacheKey = `stock_analysis_v2_${dataset}`;
  const [analysis, setAnalysis] = useState<StockQuickResult | null>(() => {
    try {
      const r = localStorage.getItem(cacheKey);
      if (r) {
        const o = JSON.parse(r) as StockQuickResult;
        if (o.overall || o.raw || (o.sectors && o.sectors.length)) return o;
      }
    } catch {
      /* ignore */
    }
    return null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [basisText, setBasisText] = useState("");
  const [showBasis, setShowBasis] = useState(false);
  const runningRef = useRef(false);

  // ── 由行情数据构造速评输入(默认用自选卡现成数据; 分析前会强制拉一次最新行情) ──
  const buildMetrics = (quoteMap: Record<string, WatchStock>): { text: string; asof: string } | null => {
    const all = Object.values(quoteMap).filter((s) => s && s.price > 0);
    if (all.length === 0) return null;
    let up = 0, down = 0, flat = 0, sum = 0;
    for (const s of all) {
      if (s.change_pct > 0) up++;
      else if (s.change_pct < 0) down++;
      else flat++;
      sum += s.change_pct;
    }
    const sorted = [...all].sort((a, b) => b.change_pct - a.change_pct);
    const asof = new Date().toLocaleString("zh-CN", { hour12: false });
    const L: string[] = [];
    L.push(`# 个股速评 ${dataset} · 自选样本 ${all.length} 只 · 数据截至 ${asof}`);
    L.push(`样本: 涨${up} 跌${down} 平${flat} 平均 ${sum >= 0 ? "+" : ""}${(sum / all.length).toFixed(2)}%`);
    L.push(`涨幅居前: ${sorted.slice(0, 3).map((s) => `${s.name} ${fmtPct(s.change_pct)}`).join("  ")}`);
    L.push(`跌幅居前: ${sorted.slice(-3).reverse().map((s) => `${s.name} ${fmtPct(s.change_pct)}`).join("  ")}`);
    const flowList = Object.entries(flows)
      .map(([code, v]) => ({ code, v }))
      .filter((x): x is { code: string; v: number } => typeof x.v === "number")
      .sort((a, b) => b.v - a.v);
    if (flowList.length) {
      L.push(`主力净流入居前(亿): ${flowList.slice(0, 5).map((x) => `${x.code} ${x.v >= 0 ? "+" : ""}${x.v.toFixed(2)}`).join("  ")}`);
    }
    L.push("板块明细:");
    for (const sector of order) {
      const codes = sectors[sector] || [];
      const rows = codes.map((c) => quoteMap[c]).filter((s): s is WatchStock => !!s && s.price > 0);
      if (rows.length === 0) continue;
      let u = 0, d = 0, ssum = 0;
      for (const s of rows) {
        if (s.change_pct > 0) u++;
        else if (s.change_pct < 0) d++;
        ssum += s.change_pct;
      }
      const sSorted = [...rows].sort((a, b) => b.change_pct - a.change_pct);
      const lead = sSorted.slice(0, 2).map((s) => `${s.name}${fmtPct(s.change_pct)}`).join(" ");
      const lag = sSorted.slice(-2).reverse().map((s) => `${s.name}${fmtPct(s.change_pct)}`).join(" ");
      L.push(`【${sector} ${codes.length}只 ${u}涨${d}跌 平均${ssum / rows.length >= 0 ? "+" : ""}${(ssum / rows.length).toFixed(2)}%】 领涨: ${lead}; 领跌: ${lag}`);
    }
    return { text: L.join("\n"), asof };
  };

  const run = async () => {
    if (runningRef.current) return; // 防重入: 自动时点/自选联动/手动三路并发时只跑一次
    runningRef.current = true;
    setLoading(true);
    setError(null);
    // 分析前强制拉取一次最新自选行情(与上方自选卡同源), 保证每次分析都以最新数据为基础
    let quoteMap = data;
    try {
      if (codes.length > 0) {
        const qr = await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stocks: codes, sparkline: false }),
        });
        if (qr.ok) {
          const qd = await qr.json();
          const m: Record<string, WatchStock> = {};
          ((qd.stocks || []) as { code?: string; name?: string; price?: number; change_pct?: number }[]).forEach((s) => {
            if (s && s.code) m[s.code] = { code: s.code, name: s.name || "", price: s.price || 0, change_pct: s.change_pct || 0 };
          });
          if (Object.keys(m).length > 0) quoteMap = m;
        }
      }
    } catch {
      /* 拉最新失败则用自选卡当前数据 */
    }
    const snap = buildMetrics(quoteMap);
    if (!snap) {
      setLoading(false);
      setError("暂无自选个股行情(请先在上方自选股票加载后重试)");
      return;
    }
    try {
      const r = await fetch("/api/sector/quick-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: dataset,
          sector: "自选个股",
          kind: "stock_overview",
          metrics_text: snap.text,
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
      // 兜底: 后端降级 raw 但内容形如 JSON 时, 前端自行提取(overall/sectors)
      let overall = res.overall || "";
      let sectors = Array.isArray(res.sectors) ? res.sectors : [];
      let raw = res.raw || "";
      if (!overall && !sectors.length && raw.trim().startsWith("{")) {
        try {
          const o = JSON.parse(raw.trim());
          overall = o.overall || "";
          sectors = Array.isArray(o.sectors) ? o.sectors : [];
          raw = "";
        } catch {
          /* keep raw */
        }
      }
      const saved: StockQuickResult = { overall, sectors, raw, asof: snap.asof };
      setAnalysis(saved);
      setBasisText(snap.text);
      try {
        localStorage.setItem(cacheKey, JSON.stringify(saved));
      } catch {
        /* ignore */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
      runningRef.current = false;
      quickAnalysisBus.done(cacheKey);
    }
  };
  const runRef = useRef<() => Promise<void>>(async () => {});
  runRef.current = run;
  useEffect(() => {
    const h = () => {
      // 自选股票刷新(手动或盘中时点)完成后由父级调用, 立即以最新行情重新分析
      void runRef.current();
    };
    quickAnalysisBus.onRun(cacheKey, h);
    return () => quickAnalysisBus.offRun(cacheKey, h);
  }, [cacheKey]);

  return (
    <div id="stock-quick-analysis" className={flush ? "" : "rounded-xl border bg-card"}>
      {/* 无独立按钮: 与自选股票统一由上方「刷新」驱动(手动/盘中时点), 点击后自动重新分析 */}
      <CardHeader title="个股速评" />
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            基于自选个股实时行情(涨跌结构/领涨领跌/主力资金)与板块分布, 生成整体速评与分板块点评
          </p>
        )}
        {error && <p className="py-1 text-xs text-red-500">AI 分析失败：{error}</p>}
        {analysis && (
          <div className="space-y-3">
            {analysis.raw ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{analysis.raw}</p>
            ) : (
              <>
                {analysis.overall && (
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <div className="mb-1 flex items-baseline gap-2">
                      <span className="shrink-0 text-xs font-bold tracking-widest text-muted-foreground">整体</span>
                      <p className="text-sm font-medium leading-relaxed text-foreground">{analysis.overall}</p>
                    </div>
                  </div>
                )}
                {analysis.sectors.length > 0 && (
                  <div>
                    <div className="mb-1 flex items-baseline gap-2 border-b border-border/70 pb-1">
                      <span className="shrink-0 text-xs font-bold tracking-widest text-muted-foreground">板块明细</span>
                    </div>
                    {/* 每板块统一结构: 首行 板块名列 + 涨跌数据列(定宽右对齐), 次行 评语列缩进对齐,
                        名称/数据/评语纵向整齐; 数据段间加间距便于阅读 */}
                    <ul className="divide-y divide-border/40">
                      {analysis.sectors.map((s, i) => (
                        <li key={i} className="py-2">
                          <div className="flex items-start gap-3">
                            <span
                              className="w-24 shrink-0 truncate pl-1 pt-0.5 text-[15px] font-bold text-foreground"
                              title={s.name}
                            >
                              {s.name}
                            </span>
                            {/* 涨跌数据: 普通文本流(不逐 token 折行), 段与段间 6px 间距 */}
                            <span className="min-w-0 flex-1 text-[15px] leading-relaxed">
                              {colorParts(s.change).map((seg, si) => (
                                <span key={si} className={(seg.cls || "text-foreground") + (si > 0 ? " ml-1.5" : "")}>
                                  {seg.text}
                                </span>
                              ))}
                            </span>
                          </div>
                          {/* 评语: 领涨/领跌/短线分块展示, 块间明显间距 */}
                          {s.comment && (
                            <div className="mt-1 flex gap-3">
                              <span className="w-24 shrink-0" />
                              <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-4 gap-y-1 text-sm leading-relaxed">
                                {commentParts(s.comment).map((part, pi) => (
                                  <span key={pi} className={part.cls}>
                                    {part.label && <b className={part.cls}>{part.label}：</b>}
                                    {part.body}
                                  </span>
                                ))}
                              </span>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
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
