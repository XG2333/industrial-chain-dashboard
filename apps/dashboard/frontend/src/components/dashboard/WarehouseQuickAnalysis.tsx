import { useCallback, useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { CardHeader } from "@/components/ui/CardHeader";

// 仓单速评：显示在仓单日报表格下方。
// 基于仓单表格数据（各仓库/地区汇总的最新值 + 日/周/月环比）调 DeepSeek 生成点评，
// 与板块速评同一后端端点（kind=warehouse）；结果按行业缓存到 localStorage，
// 首次渲染即恢复上次内容（刷新/重开不丢失）。

interface WarehouseRow {
  kind: string;
  warehouse: string;
  region: string;
  product: string;
  values: (number | null)[];
  // 手数差(与仓单日报表同口径, 用于速评输入); rate 为兼容保留
  daily_change: number | null;
  weekly_change: number | null;
  monthly_change: number | null;
  daily_rate: number | null;
  weekly_rate: number | null;
  monthly_rate: number | null;
}

interface WarehouseTableData {
  dates: string[];
  rows: WarehouseRow[];
  title?: string;
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

// 分层全量摘要：全国总量 → 量价 → 各地区汇总(组头) → 该地区全部仓库行。
// 压缩规则（省 token）：单位/日期只出现一次；环比用"手数差"（与上方仓单日报列数值口径一致,
// 非百分比），格式 "日+420 周+1590 月+449"（null 环比省略该词）。
// 所有行都保留（0 手仓库也列出——零仓单本身是信息），不再截断。
const fmtChg = (v: number | null): string => {
  if (v == null || v === 0) return "";
  return `${v > 0 ? "+" : ""}${Math.round(v)}`;
};

const ratePart = (dc: number | null, wc: number | null, mc: number | null): string => {
  const parts: string[] = [];
  const d = fmtChg(dc);
  const w = fmtChg(wc);
  const m = fmtChg(mc);
  if (d) parts.push(`日${d}手`);
  if (w) parts.push(`周${w}手`);
  if (m) parts.push(`月${m}手`);
  return parts.length ? ` | ${parts.join(" ")}` : "";
};

function buildLines(table: WarehouseTableData): string[] {
  const date = table.dates?.[0] ?? "";
  const lines: string[] = [
    `# 仓单日报 ${(date || "").slice(5)}（单位: 手; 日/周/月环比 = 最新 vs 前1/5/21个交易日的手数差, 与仓单日报表同口径, 非百分比）`,
  ];
  const emit = (row: WarehouseRow) => {
    const v = row.values?.[0] ?? null;
    lines.push(`${row.warehouse} ${v ?? "—"}${ratePart(row.daily_change, row.weekly_change, row.monthly_change)}`);
  };
  // 1) 全国总量与量价行
  for (const row of table.rows) {
    if (row.kind === "total" || row.kind === "metric") emit(row);
  }
  // 2) 地区分组：汇总行做组头 + 该地区全部仓库行（全量，不截断）
  const whByRegion = new Map<string, WarehouseRow[]>();
  for (const row of table.rows) {
    if (row.kind === "warehouse") {
      const region = row.region || "其他";
      if (!whByRegion.has(region)) whByRegion.set(region, []);
      whByRegion.get(region)!.push(row);
    }
  }
  const regionHead = new Map<string, WarehouseRow>();
  for (const row of table.rows) {
    if (row.kind === "region") regionHead.set(row.warehouse.replace(/仓单量$/, ""), row);
  }
  for (const [region, rows] of whByRegion) {
    const head = regionHead.get(region);
    if (head) {
      const v = head.values?.[0] ?? null;
      lines.push(`【${region}】汇总 ${v ?? "—"}${ratePart(head.daily_change, head.weekly_change, head.monthly_change)}`);
    } else {
      lines.push(`【${region}】`);
    }
    for (const row of rows) {
      const v = row.values?.[0] ?? null;
      lines.push(`  ${row.warehouse} ${v ?? "—"}${ratePart(row.daily_change, row.weekly_change, row.monthly_change)}`);
    }
  }
  return lines;
}

interface WarehouseQuickAnalysisProps {
  dataset: "lithium" | "tin" | "silicon";
  // 数据源: excel=本地 Excel(默认); live=公开 API(仓单日报切换后简评同源)
  source?: "excel" | "live";
}

export function WarehouseQuickAnalysis({ dataset, source = "excel" }: WarehouseQuickAnalysisProps) {
  // v2：全量分层输入（旧 v1 缓存为截断格式结果，不兼容需失效）
  const cacheKey = `warehouse_analysis_v2_${dataset}`;
  // 与板块简评一致：首帧渲染即恢复 localStorage 内容
  const [analysis, setAnalysis] = useState<QuickAnalysis | null>(() => {
    try {
      const r = localStorage.getItem(cacheKey);
      if (r) return JSON.parse(r) as QuickAnalysis;
    } catch {
      /* ignore */
    }
    return null;
  });
  const [table, setTable] = useState<WarehouseTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 本次分析送入 AI 的数据行（供"查看数据依据"核对）
  const [basisText, setBasisText] = useState("");
  const [showBasis, setShowBasis] = useState(false);

  // 拉取仓单表数据并缓存到 state；返回数据（供分析前等待/重试）。
  // 数据源与上方仓单日报联动: 公开 API 模式简评使用公开 API 的当日+30日历史数据
  const fetchTable = useCallback(async (): Promise<WarehouseTableData | null> => {
    try {
      const url =
        source === "live"
          ? `/api/warehouse-table-live?dataset=${dataset}`
          : `/api/warehouse-table?dataset=${dataset}`;
      const r = await fetch(url);
      if (!r.ok) return null;
      const d = (await r.json()) as WarehouseTableData;
      if (d && d.rows?.length > 0) {
        setTable(d);
        return d;
      }
      return null;
    } catch {
      return null;
    }
  }, [dataset, source]);

  useEffect(() => {
    void fetchTable();
  }, [fetchTable]);

  // 响应"一键速评全部"的全局触发（bus.run(cacheKey) → 开始本卡分析）
  const runRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    const h = () => {
      void runRef.current();
    };
    quickAnalysisBus.onRun(cacheKey, h);
    return () => quickAnalysisBus.offRun(cacheKey, h);
  }, [cacheKey]);

  const asof = table?.dates?.[0] ?? "";

  const run = async () => {
    // 每次触发都重新拉取最新仓单(与上方仓单日报刷新同步), 避免用挂载时的旧快照
    let t = await fetchTable();
    const startedAt = Date.now();
    while ((!t || t.rows.length === 0) && Date.now() - startedAt < 5000) {
      await new Promise((r) => setTimeout(r, 400));
      t = await fetchTable();
    }
    if (!t || t.rows.length === 0) {
      setError("暂无仓单数据");
      return;
    }
    const lines = buildLines(t);
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/sector/quick-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: dataset,
          sector: "仓单日报",
          kind: "warehouse",
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
      const data = await r.json();
      const saved: QuickAnalysis = {
        verdict: data.verdict || "",
        points: Array.isArray(data.points) ? data.points : [],
        outlook: data.outlook || "",
        raw: data.raw || "",
        asof: t.dates?.[0] ?? "",
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
      // 通知协调器本卡分析结束，可进入下一项
      quickAnalysisBus.done(cacheKey);
    }
  };
  runRef.current = run;

  return (
    <div className="mt-3 rounded-xl border bg-card">
      {/* 无独立按钮: 由上方「仓单日报」刷新按钮联动更新 */}
      <CardHeader title="仓单速评" />
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            {source === "live"
              ? "基于上方公开API仓单数据（交易所当日快照 + 30日历史环比与走势）生成简洁点评 · 点击上方「刷新」同步更新"
              : "基于上方仓单数据（各仓库/地区最新值与日周月环比）生成简洁点评 · 点击上方「刷新」同步更新"}
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
            {/* 数据依据：可核对 AI 引用的输入数据（仓单分层行） */}
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
