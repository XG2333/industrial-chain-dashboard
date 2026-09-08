import { useEffect, useMemo, useRef, useState } from "react";
import type { ChartData, ChartMeta } from "@/lib/chartTypes";
import { loadChartData } from "@/lib/excelCache";
import { simplifyIndicatorName } from "@/lib/indicatorName";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { colorParts } from "@/lib/analysisColor";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";
import { sampleWeekly } from "@/components/dashboard/IndicatorSummaryTable";

// 板块速评：显示在"近期指标速览"与具体指标图之间。
// 输入规则（同族合并 + 全覆盖）：
//   1. 同大类 + 同频率下，仅"最后一段路线/环节词"不同的指标（如产量分盐湖/锂云母/
//      锂辉石/回收，成本分不同外购原料）合并为一行"族对比行"，各路线横向并列，
//      避免多路线互相挤占取样名额导致信息截断；
//   2. 单指标仍按大类均分取样，合并后单元总数上限 40 行。
// 调 DeepSeek 返回结构化点评（verdict / points / outlook），前端排版为层次卡片。

const MAX_UNITS = 40; // 合并后单元（单指标行 / 族行）上限
const MAX_FAMILY_MEMBERS = 8; // 族行内最多并列的路线数

interface QuickPoint {
  metric: string;
  change: string;
  comment: string;
}

interface QuickAnalysis {
  verdict: string;
  points: QuickPoint[];
  outlook: string;
  raw?: string; // AI 未按 JSON 返回时的兜底纯文本
  asof: string;
}

// 历史点评存档条目（按 数据源+板块 存 localStorage，上限 7 条，最新在前）
interface HistoryEntry {
  at: number;
  verdict: string;
  outlook: string;
}

const fmtNum = (v: number) => {
  const n = Math.round(v * 100) / 100;
  return Number.isInteger(n) ? String(n) : String(n);
};

// 月环比基准 = 最新值 vs 30 天前的最近数据点（数据降序，最新在前）
function monthlyBase(data: { date: string; value: number }[]): number | null {
  if (data.length < 2) return null;
  const t1 = new Date(data[0].date + "T00:00:00").getTime();
  const cutoff = t1 - 30 * 86400000;
  for (const p of data) {
    const t = new Date(p.date + "T00:00:00").getTime();
    if (t <= cutoff) return p.value;
  }
  return null;
}

// 近 5 期相邻方向箭头（数据升序后比较；上期低 → ↑）
function trendArrows(pts: { date: string; value: number }[]): string {
  const n = Math.min(5, pts.length);
  const last = pts.slice(0, n).reverse();
  const out: string[] = [];
  for (let i = 1; i < last.length; i++) {
    const a = last[i - 1].value;
    const b = last[i].value;
    out.push(a === b ? "→" : b > a ? "↑" : "↓");
  }
  return out.join("");
}

const pct = (cur: number | null, base: number | null): string => {
  if (cur == null || base == null || base === 0) return "—";
  const p = ((cur - base) / base) * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`;
};

const chgLabelOf = (weekly: boolean) => (weekly ? "周环比" : "日环比");

// ── 同族合并 ──
// 简化名中"括号外的最后一个 : 分隔段"视为路线/环节维度词（如"碳酸锂产量: 盐湖产"），
// 去掉该尾段后的前缀即"族 key"；同大类+同频率+同 key 的指标合并为族行。
function familyKeyOf(title: string): string {
  const t = simplifyIndicatorName(title) || title;
  let depth = 0;
  let lastColon = -1;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (ch === "（" || ch === "(") depth++;
    else if (ch === "）" || ch === ")") depth = Math.max(0, depth - 1);
    else if ((ch === ":" || ch === "：") && depth === 0) lastColon = i;
  }
  if (lastColon <= 0) return t; // 无分段 → 自成族（单行）
  return t.slice(0, lastColon).trim();
}

// 成员短名 = 族 key 之后的部分，并去掉括号规格等细节
function memberShortName(fullSimplified: string, familyKey: string): string {
  const rest = fullSimplified.slice(familyKey.length);
  const s = rest
    .replace(/^[\s:：\-—]+/, "")
    .replace(/[（(].*?[）)]/g, "")
    .trim();
  return s || "总计";
}

const FREQ_CN: Record<string, string> = {
  daily: "日度",
  weekly: "周度",
  monthly: "月度",
  quarterly: "季度",
  yearly: "年度",
};

// ── 行文本生成 ──

// 单指标行（非族）：名称(单位): 最新值(日期) | 日/周环比 | 月环比 | 走势
function singleLine(chart: ChartMeta, data: ChartData): string | null {
  const raw = data.data || [];
  if (raw.length === 0) return null;
  const weekly = chart.freq === "weekly";
  const pts = weekly ? sampleWeekly(raw) : raw;
  const v1 = pts[0]?.value ?? null;
  const v2 = pts[1]?.value ?? null;
  if (v1 == null) return null;
  const name = simplifyIndicatorName(chart.title) || chart.title;
  const unit = chart.unit ? `（${chart.unit}）` : "";
  return `${name}${unit}: 最新${fmtNum(v1)}(${(pts[0].date || "").slice(5)}) | ${chgLabelOf(weekly)} ${pct(v1, v2)} | 月环比 ${pct(v1, monthlyBase(raw))} | 走势 ${trendArrows(pts)}`;
}

// 族行（同族多路线横向对比）：族名[日期]: 路线1 值(环比) | 路线2 值(环比) | …
function familyLine(familyKey: string, members: ChartMeta[], dataMap: Map<string, ChartData>): string | null {
  const parts: string[] = [];
  let date = "";
  let weekly = false;
  for (const c of members) {
    if (parts.length >= MAX_FAMILY_MEMBERS) break;
    const d = dataMap.get(c.id);
    if (!d || !d.data || d.data.length === 0) continue;
    weekly = c.freq === "weekly";
    const pts = weekly ? sampleWeekly(d.data) : d.data;
    const v1 = pts[0]?.value ?? null;
    if (v1 == null) continue;
    const v2 = pts[1]?.value ?? null;
    const short = memberShortName(simplifyIndicatorName(c.title) || c.title, familyKey);
    parts.push(`${short} ${fmtNum(v1)}(${chgLabelOf(weekly)}${pct(v1, v2)})`);
    if (!date) date = (pts[0].date || "").slice(5);
  }
  if (parts.length === 0) return null;
  const freqCn = weekly ? "周度" : FREQ_CN[members[0].freq ?? ""] || members[0].freq || "";
  return `${familyKey}（${freqCn}）${date ? `[${date}]` : ""}: ${parts.join(" | ")}`;
}

// ── 合并 + 取样：按大类均分单元配额，控制输入 token ──
interface Unit {
  major: string;
  minOrder: number;
  line: string | null;
}

function buildUnits(charts: ChartMeta[], dataMap: Map<string, ChartData>): Unit[] {
  const withData = charts.filter((c) => (dataMap.get(c.id)?.data?.length ?? 0) > 0);
  // 预分组：(major, freq, familyKey)
  const famGroups = new Map<string, ChartMeta[]>();
  for (const c of withData) {
    const k = `${c.major || "其他"}|||${c.freq || ""}|||${familyKeyOf(c.title || "")}`;
    if (!famGroups.has(k)) famGroups.set(k, []);
    famGroups.get(k)!.push(c);
  }
  const units: Unit[] = [];
  for (const list of famGroups.values()) {
    const major = list[0].major || "其他";
    const minOrder = Math.min(...list.map((c) => c.catalogOrder ?? Number.MAX_SAFE_INTEGER));
    const line =
      list.length > 1
        ? familyLine(familyKeyOf(list[0].title || ""), list, dataMap)
        : singleLine(list[0], dataMap.get(list[0].id)!);
    if (line) units.push({ major, minOrder, line });
  }
  // 大类内按目录顺序排序（产业链顺序），大类外保持出现顺序
  const byMajor = new Map<string, Unit[]>();
  for (const u of units) {
    if (!byMajor.has(u.major)) byMajor.set(u.major, []);
    byMajor.get(u.major)!.push(u);
  }
  const out: Unit[] = [];
  for (const [major, list] of byMajor) {
    list.sort((a, b) => a.minOrder - b.minOrder);
    out.push(...list);
  }
  // 大类配额均分取样（超过大类数时每类轮转多取 1）
  if (out.length <= MAX_UNITS) return out;
  const majorKeys = [...byMajor.keys()];
  const per = Math.floor(MAX_UNITS / majorKeys.length);
  let rest = MAX_UNITS - per * majorKeys.length;
  const sampled: Unit[] = [];
  for (const major of majorKeys) {
    const list = byMajor.get(major)!;
    const take = per + (rest > 0 ? 1 : 0);
    if (rest > 0) rest -= 1;
    sampled.push(...list.slice(0, take));
  }
  return sampled;
}

interface SectorQuickAnalysisProps {
  sectorName: string;
  charts: ChartMeta[];
}

export function SectorQuickAnalysis({ sectorName, charts }: SectorQuickAnalysisProps) {
  const ids = useMemo(() => charts.map((c) => c.id), [charts]);
  // 数据源从指标 id 前缀推断（lithium_ / tin_ / silicon_）
  const dataset = ids[0]?.startsWith("tin_") ? "tin" : ids[0]?.startsWith("silicon_") ? "silicon" : "lithium";
  // v3：同族合并输入规则；缓存按 数据源+板块 粒度
  const cacheKey = `sector_analysis_v3_${dataset}_${sectorName}`;
  const [dataMap, setDataMap] = useState<Map<string, ChartData>>(new Map());
  const dataMapRef = useRef<Map<string, ChartData>>(dataMap);
  // 与板块简评一致：首帧渲染即从 localStorage 恢复上一次内容，
  // 刷新/重开页面无需重新调用 AI
  const [analysis, setAnalysis] = useState<QuickAnalysis | null>(() => {
    try {
      const r = localStorage.getItem(cacheKey);
      if (r) return JSON.parse(r) as QuickAnalysis;
    } catch {
      /* ignore */
    }
    return null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 本次分析送入 AI 的数据行（供"查看数据依据"核对 AI 是否忠于数据）
  const [basisText, setBasisText] = useState("");
  const [showBasis, setShowBasis] = useState(false);
  // 历史点评存档（生成新点评时自动追加，可回看前几天的判断）
  const historyKey = `sector_analysis_history_v1_${dataset}_${sectorName}`;
  const [history, setHistory] = useState<HistoryEntry[]>(() => {
    try {
      const r = localStorage.getItem(historyKey);
      if (r) return JSON.parse(r) as HistoryEntry[];
    } catch {
      /* ignore */
    }
    return [];
  });
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (ids.length === 0) return;
    loadChartData(ids)
      .then((loaded) => {
        if (!cancelled) setDataMap(new Map(loaded.map((c) => [c.id, c])));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [ids]);

  // 响应"一键速评全部板块"的全局触发（bus.run(cacheKey) → 本板块开始分析）
  const runRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    const h = () => {
      void runRef.current();
    };
    quickAnalysisBus.onRun(cacheKey, h);
    return () => quickAnalysisBus.offRun(cacheKey, h);
  }, [cacheKey]);

  if (charts.length === 0) return null;

  const curAsof = (() => {
    for (const c of charts) {
      const d0 = dataMap.get(c.id)?.data?.[0]?.date;
      if (d0) return d0;
    }
    return "";
  })();

  const run = async () => {
    // 图表数据可能尚未加载完成（一键触发时）：最多等待 10s 直到可取到指标行
    const startedAt = Date.now();
    let units = buildUnits(charts, dataMapRef.current);
    while (units.length === 0 && Date.now() - startedAt < 10000) {
      await new Promise((r) => setTimeout(r, 250));
      units = buildUnits(charts, dataMapRef.current);
    }
    const lines = units.map((u) => u.line).filter((l): l is string => !!l);
    if (lines.length === 0) {
      setError("暂无指标数据");
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
          sector: sectorName,
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
        asof: curAsof,
      };
      setAnalysis(saved);
      setBasisText(lines.join("\n"));
      // 生成时自动存档历史（最新在前，上限 7 条）
      setHistory((prev) => {
        const next = [
          { at: Date.now(), verdict: saved.verdict, outlook: saved.outlook },
          ...prev,
        ].slice(0, 7);
        try {
          localStorage.setItem(historyKey, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
      try {
        localStorage.setItem(cacheKey, JSON.stringify(saved));
      } catch {
        /* ignore */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
      // 通知协调器本板块分析结束（成功/失败都算完成），可进入下一个板块
      quickAnalysisBus.done(cacheKey);
    }
  };
  runRef.current = run;
  dataMapRef.current = dataMap;

  // 未生成过（无缓存/非加载/无错误）时折叠为一行，减少 13 个板块的占位空间；
  // 点击后展开卡片并生成内容；生成后正常展示完整卡片
  if (!analysis && !loading && !error) {
    return (
      <div className="mt-3">
        <Button
          variant="outline"
          size="sm"
          onClick={run}
          className="w-full justify-between rounded-xl border-dashed bg-card/60 text-muted-foreground hover:bg-card hover:text-foreground"
        >
          <span className="text-[13px] font-semibold">板块速评</span>
          <span className="text-xs font-normal">基于上方指标速览一键生成 AI 点评</span>
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border bg-card">
      <CardHeader
        title="板块速评"
        action={
          <Button variant="outline" size="sm" onClick={run} disabled={loading}>
            {loading ? "分析中…" : "重新分析"}
          </Button>
        }
      />
      <div className="px-4 py-3">
        {!analysis && !loading && !error && (
          <p className="py-1 text-xs text-muted-foreground">
            基于上方指标速览（最新值、日/周环比、月环比与近期走势）生成简洁板块点评
          </p>
        )}
        {error && <p className="py-1 text-xs text-red-500">AI 分析失败：{error}</p>}
        {analysis && (
          <div className="space-y-3">
            {/* AI 未按 JSON 返回：兜底纯文本 */}
            {analysis.raw ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{analysis.raw}</p>
            ) : (
              <>
                {/* 板块状态判断（主导逻辑） */}
                {analysis.verdict && (
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-sm font-semibold leading-relaxed text-foreground">{analysis.verdict}</p>
                  </div>
                )}
                {/* 关键指标要点 */}
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
                {/* 前瞻判断 */}
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
            {/* 数据依据：可核对 AI 引用的输入数据（族对比行/单指标行） */}
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
            {/* 历史点评：自动存档每次生成，可回看判断演变 */}
            {history.length > 0 && (
              <div className="border-t border-border/60 pt-1.5">
                <button
                  onClick={() => setShowHistory((v) => !v)}
                  className="text-[11px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
                >
                  {showHistory ? "收起历史点评" : `历史点评（${history.length}）`}
                </button>
                {showHistory && (
                  <ul className="mt-1.5 space-y-1">
                    {history.map((h, i) => (
                      <li key={`${h.at}-${i}`} className="flex items-baseline gap-2 text-[11px] leading-relaxed text-muted-foreground">
                        <span className="shrink-0 tabular-nums">
                          {new Date(h.at).toLocaleString("zh-CN", {
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: false,
                          })}
                        </span>
                        <span className="truncate" title={`${h.verdict || ""} ${h.outlook || ""}`}>
                          {h.verdict || h.outlook || "—"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
