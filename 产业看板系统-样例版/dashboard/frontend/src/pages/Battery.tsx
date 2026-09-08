import React, { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, Bot, FileText, RefreshCw } from "lucide-react";
import { useRef } from "react";
import { ConclusionText } from "@/components/charts/ConclusionText";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";
import {
  IndustryTabBar,
  IndustryViewToggle,
  PageContainer,
} from "@/components/dashboard";
import { FloatingTargetNav } from "@/components/layout/FloatingTargetNav";
import { IndustryDataScheme1 } from "@/components/layout/IndustryDataScheme1";
import { IndustryDataScheme2 } from "@/components/layout/IndustryDataScheme2";
import { BriefPanel } from "@/components/dashboard/BriefPanel";
import { IndustryKpiBand } from "@/components/dashboard/IndustryKpiBand";
import { KpiFutureAnalysis } from "@/components/dashboard/KpiFutureAnalysis";
import { ScorePanel } from "@/components/dashboard/ScorePanel";
import { SectorWatchlist } from "@/components/dashboard/SectorWatchlist";
import { IndividualStocksView } from "@/components/dashboard/IndividualStocksView";
import { WarehouseReceiptTable } from "@/components/dashboard/WarehouseReceiptTable";
import { SectorAnalysisAllToolbar } from "@/components/dashboard/SectorAnalysisAllToolbar";
import { useLayoutMode } from "@/hooks/useLayoutMode";
import { clearChartSeriesCache, loadChartData } from "@/lib/excelCache";
import { buildIndustryGroups } from "@/lib/industryGroups";
import type { ChartMeta } from "@/lib/chartTypes";

interface StockBrief { code: string; name: string; price: number; change_pct: number; }
interface StockDetail {
  code: string; name: string; price: number; change_pct: number;
  open: number; high: number; low: number; last_close: number;
  turnover_pct: number; amount_yi: number;
  pe_ttm: number; pb: number; mcap_yi: number; float_mcap_yi: number;
  limit_up: number; limit_down: number; sparkline: number[];
}
interface ScoreItem { dimension: string; score: number; reason: string; }
interface AnalysisResult { scores: ScoreItem[]; conclusion: string; summary?: { verdict: string; key_points: { title: string; text: string }[]; outlook: string } | null; at?: number; }
interface ReportItem { date: string; org: string; stockName: string; title: string; infoCode: string; }
const TABS = [
  "总览", "锂矿", "锂盐", "磷酸铁锂", "三元正极", "钴酸锂", "锰酸锂",
  "负极材料", "隔膜",
  "电解液产业链", "辅材", "电池电芯", "储能", "新能源汽车",
];
const SUB_SECTORS = TABS.slice(1);
const SECTOR_GROUPS: Record<string, string[]> = {
  "锂盐": ["碳酸锂", "氢氧化锂", "其他锂盐"],
};
const DEFAULT_STOCKS: Record<string, string[]> = {};
const SCORE_LABELS: Record<string, string> = {
  "供需格局": "供过于求 → 供不应求", "价格趋势": "价格下行 → 上行",
  "库存周期": "累库 → 去库", "资金关注": "资金流出 → 流入", "政策催化": "利空 → 利好",
};

function loadStocks(tab: string, targets: Record<string, string[]> = DEFAULT_STOCKS): string[] {
  try {
    const r = localStorage.getItem("bt_stocks_v3_" + tab);
    if (r) {
      const parsed = JSON.parse(r);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch { /* fall through to default pool */ }
  return targets[tab] || [];
}
function saveStocks(tab: string, codes: string[]) { localStorage.setItem("bt_stocks_v3_" + tab, JSON.stringify(codes)); }
function loadAnalysis(tab: string): AnalysisResult | null {
  try { const r = localStorage.getItem("bt_analysis_v2_" + tab); return r ? JSON.parse(r) : null; }
  catch { return null; }
}
function saveAnalysis(tab: string, data: AnalysisResult) { localStorage.setItem("bt_analysis_v2_" + tab, JSON.stringify(data)); }
function loadReports(tab: string): ReportItem[] {
  try { const r = localStorage.getItem("bt_reports_v2_" + tab); return r ? JSON.parse(r) : []; }
  catch { return []; }
}
function saveReports(tab: string, data: ReportItem[]) { localStorage.setItem("bt_reports_v2_" + tab, JSON.stringify(data)); }

const cc = (pct: number) => pct === 0 ? "text-muted-foreground" : pct > 0 ? "text-red-500" : "text-green-500";

// 个股排序（总览与各板块统一）：
// 一级按产业链上下游环节（上游 -> 中游 -> 下游，无环节最后），
// 二级按环节内板块（细分板块）产业链顺序，三级同板块内按市值降序
// （市值优先实时行情 mcap_yi，缺失回退 Excel"总市值(亿)"）。
const SEGMENT_RANK_PREFIXES = ["上游", "中游", "下游"];
// 细分板块产业链顺序（与后端 server.py STOCK_SUB_ORDER 保持一致）
const STOCK_SUB_ORDER = [
  "锂矿锂盐", "锂矿", "锂盐", "三元正极", "磷酸铁锂正极", "负极",
  "隔膜", "电解液", "铜箔铝箔", "电池&电芯", "储能&集成", "新能源车",
];

function segmentRankOf(segment?: string): number {
  const s = segment || "";
  for (let i = 0; i < SEGMENT_RANK_PREFIXES.length; i++) {
    if (s.startsWith(SEGMENT_RANK_PREFIXES[i])) return i;
  }
  return SEGMENT_RANK_PREFIXES.length;
}

function subRankOf(subs?: string[]): number {
  const list = subs || [];
  if (list.length === 0) return STOCK_SUB_ORDER.length;
  return Math.min(...list.map(s => {
    const i = STOCK_SUB_ORDER.indexOf(s);
    return i >= 0 ? i : STOCK_SUB_ORDER.length;
  }));
}

// 股票代码排序（总览与各板块统一）：(环节 rank, 板块 rank, Excel 市值降序)
function sortBySegmentAndCap(
  codes: string[],
  meta: Record<string, { segment?: string; subs?: string[]; market_cap?: number }>,
): string[] {
  return [...codes].sort((a, b) => {
    const ra = segmentRankOf(meta[a]?.segment);
    const rb = segmentRankOf(meta[b]?.segment);
    if (ra !== rb) return ra - rb;
    const sa = subRankOf(meta[a]?.subs);
    const sb = subRankOf(meta[b]?.subs);
    if (sa !== sb) return sa - sb;
    const ca = meta[a]?.market_cap ?? 0;
    const cb = meta[b]?.market_cap ?? 0;
    return cb - ca;
  });
}

export function Battery() {
  const [activeTab, setActiveTab] = useState(() => {
    const stored = localStorage.getItem("bt_tab_v2");
    return stored && TABS.includes(stored) ? stored : "总览";
  });
  const [activeSector, setActiveSector] = useState<string | null>(() => SECTOR_GROUPS[activeTab]?.[0] ?? null);
  const [stockCodes, setStockCodes] = useState<string[]>(() => loadStocks(activeTab));
  const [stockTargets, setStockTargets] = useState<Record<string, string[]>>({});
  const [stockMeta, setStockMeta] = useState<Record<string, { name?: string; segment?: string; subs?: string[]; market_cap?: number }>>({});
  const [stocksBrief, setStocksBrief] = useState<StockBrief[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(() => loadAnalysis(activeTab));
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [newsItems, setNewsItems] = useState<{title:string;date:string;source:string;url:string}[]>([]);
  // 自选股票（原行情总览区块）
  const [watchData, setWatchData] = useState<Record<string, { code: string; name: string; price: number; change_pct: number; volume: number; turnover_pct: number }>>({});
  const [watchFlows, setWatchFlows] = useState<Record<string, number | null>>({});
  const [fetchingWatch, setFetchingWatch] = useState(false);
  const [lastWatchTime, setLastWatchTime] = useState("");
  const [fetchingReports, setFetchingReports] = useState(false);
  const [lastReportsTime, setLastReportsTime] = useState("");
  const [excelCharts, setExcelCharts] = useState<ChartMeta[]>([]);
  const [fetchingExcel, setFetchingExcel] = useState(false);
  const [selectedOnly, setSelectedOnly] = useState(true);
  const [excelAsof, setExcelAsof] = useState("");
  const [activeMajor, setActiveMajor] = useState<string | null>(null);
  const [activeSub, setActiveSub] = useState<string | null>(null);
  const [layoutMode] = useLayoutMode();
  const reqSeq = useRef(0);
  // 总览 Tab 数据源已按"二次筛选是否保留"过滤，前端同样强制只画该列=是的指标；板块 Tab 保留"是否选中"切换
  // 总览 Tab 无分区按钮（行业数据+个股固定展示）；板块 Tab 保留"行业研究/个股标的"切换
  const [viewMode, setViewMode] = useState<"行业研究" | "个股标的">("行业研究");
  const isOverviewTab = activeTab === "总览";
  const visibleCharts = isOverviewTab
    ? excelCharts.filter(c => c.finalSelected)
    : selectedOnly ? excelCharts.filter(c => c.selected) : excelCharts;
  const industryGroups = buildIndustryGroups(visibleCharts, 0);

  // 行业数据"数据截至" = 板块首个指标的最新日期（meta 不含数据，轻量拉一个）
  useEffect(() => {
    if (!excelCharts.length) {
      setExcelAsof("");
      return;
    }
    let cancelled = false;
    loadChartData([excelCharts[0].id])
      .then((items) => {
        if (!cancelled && items[0]?.data?.length) setExcelAsof(items[0].data[0].date);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [excelCharts]);

  useEffect(() => {
    fetch("/api/stock-targets")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        const groups = data?.groups?.lithium || {};
        const meta = data?.stocks?.lithium || {};
        setStockTargets(groups);
        setStockMeta(meta);
        // 总览固定为全部板块股票之和（不读本地旧缓存），板块 tab 保留本地自定义；
        // 统一按（环节 rank, 市值降序）排序
        setStockCodes(sortBySegmentAndCap(
          activeTab === "总览"
            ? (groups["总览"] || [])
            : (loadStocks(activeTab, groups).length > 0 ? loadStocks(activeTab, groups) : (groups[activeTab] || [])),
          meta
        ));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (activeMajor && !industryGroups.some((g) => g.major === activeMajor)) {
      setActiveMajor(industryGroups[0]?.major ?? null);
    }
  }, [industryGroups, activeMajor]);

  const switchTab = (t: string) => {
    setActiveTab(t); localStorage.setItem("bt_tab_v2", t);
    const nextSector = SECTOR_GROUPS[t]?.[0] ?? null;
    setActiveSector(nextSector);
    setStockCodes(sortBySegmentAndCap(t === "总览" ? (stockTargets["总览"] || []) : loadStocks(t, stockTargets), stockMeta));
    setAnalysis(loadAnalysis(t));
    setReports(loadReports(t));
    setExcelCharts([]); setStocksBrief([]);
    setActiveMajor(null);
    setActiveSub(null);
    // Auto-fetch Excel data for this tab
    const seq = ++reqSeq.current;
    setTimeout(() => {
      const sector = nextSector ?? (SUB_SECTORS.includes(t) ? t : undefined);
      fetch("/api/battery/excel/meta", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tab: t, sector, dataset: sector ? undefined : "lithium", selected_only: sector ? undefined : true }) })
        .then(r => r.ok ? r.json() : null).then(d => { if (d && seq === reqSeq.current) setExcelCharts(d.charts || []); }).catch(() => {});
    }, 0);
  };

  const fetchReports = async () => {
    setFetchingReports(true);
    try {
      const r = await fetch("/api/battery/reports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tab: activeTab, stocks: stockCodes }) });
      if (r.ok) {
        const d = await r.json();
        setReports(d.reports || []);
        saveReports(activeTab, d.reports || []);
        setLastReportsTime(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      }
    } catch { /* ignore */ }
    finally { setFetchingReports(false); }
  };

  // 产业新闻（近 7 天，原行情总览页区块）
  const fetchNews = useCallback(() => {
    fetch("/api/overview/news")
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setNewsItems(d.news || []); })
      .catch(() => {});
  }, []);
  useEffect(() => { fetchNews(); }, [fetchNews]);

  // 自选股票：锂电个股池（stockMeta 细分板块分组，板块顺序 STOCK_SUB_ORDER），
  // 行情（腾讯）+ 资金流向（新浪），原接口拉取
  const watchCodes = useMemo(() => Object.keys(stockMeta), [stockMeta]);
  const watchSectors = useMemo(() => {
    const groups: Record<string, string[]> = {};
    for (const [code, meta] of Object.entries(stockMeta)) {
      const subs = meta.subs && meta.subs.length > 0 ? meta.subs : ["其他"];
      for (const s of subs) {
        if (!groups[s]) groups[s] = [];
        groups[s].push(code);
      }
    }
    return groups;
  }, [stockMeta]);
  const watchSectorOrder = useMemo(
    () => [
      ...STOCK_SUB_ORDER.filter((s) => watchSectors[s]),
      ...Object.keys(watchSectors).filter((s) => !STOCK_SUB_ORDER.includes(s)),
    ],
    [watchSectors],
  );
  const watchCooldownRef = useRef(false);
  const fetchWatchlist = useCallback(() => {
    // 冷却期（5 秒）内忽略重复点击，避免高频刷新触发数据源风控；
    // 冷却状态用 ref（不参与依赖），否则 fetchingWatch 翻转会触发 useEffect 循环刷新
    if (watchCodes.length === 0 || watchCooldownRef.current) return;
    watchCooldownRef.current = true;
    setFetchingWatch(true);
    // 行情请求独立（快），先显示价格/涨跌/成交量
    fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: watchCodes, sparkline: false }) })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          const m: Record<string, { code: string; name: string; price: number; change_pct: number; volume: number; turnover_pct: number }> = {};
          (d.stocks || []).forEach((s: Record<string, unknown>) => {
            m[s.code as string] = { code: s.code as string, name: s.name as string, price: s.price as number, change_pct: s.change_pct as number, volume: s.volume as number || 0, turnover_pct: s.turnover_pct as number || 0 };
          });
          setWatchData(m);
          setLastWatchTime(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
        }
      })
      .catch(() => {});
    // 资金流向独立（东财批量，后端带 60s 缓存），到达后单独更新
    fetch("/api/stocks/flow", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: watchCodes }) })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setWatchFlows(d.flows || {}); })
      .catch(() => {});
    setTimeout(() => {
      watchCooldownRef.current = false;
      setFetchingWatch(false);
    }, 5000);
  }, [watchCodes]);
  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);

  const fetchExcel = async (sectorOverride?: string | null) => {
    const seq = ++reqSeq.current;
    setFetchingExcel(true);
    setExcelCharts([]);
    try {
      const childSectors = SECTOR_GROUPS[activeTab];
      const sector = sectorOverride ?? (childSectors && activeSector && childSectors.includes(activeSector)
        ? activeSector
        : SUB_SECTORS.includes(activeTab) ? activeTab : undefined);
      clearChartSeriesCache();
      const r = await fetch("/api/battery/excel/meta", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tab: activeTab, sector, dataset: sector ? undefined : "lithium", selected_only: sector ? undefined : true }) });
      if (r.ok) { const d = await r.json(); if (seq === reqSeq.current) setExcelCharts(d.charts || []); }
    } catch { /* ignore */ }
    finally { setFetchingExcel(false); }
  };

  const selectSector = (sector: string) => {
    setActiveSector(sector);
    setExcelCharts([]);
    setActiveMajor(null);
    setActiveSub(null);
    fetchExcel(sector);
  };

  const fetchStocksBrief = useCallback(async () => {
    if (stockCodes.length === 0) { setStocksBrief([]); return; }
    try {
      const r = await fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: stockCodes, sparkline: false }) });
      if (r.ok) { const d = await r.json(); setStocksBrief((d.stocks || []).map((s: Record<string,unknown>) => ({ code: s.code, name: s.name, price: s.price, change_pct: s.change_pct }))); }
    } catch { /* ignore */ }
  }, [stockCodes]);

  useEffect(() => { fetchStocksBrief(); }, [fetchStocksBrief]);
  useEffect(() => { saveStocks(activeTab, stockCodes); }, [stockCodes, activeTab]);
  useEffect(() => { fetchExcel(); }, [activeTab]);

  const runAnalysis = async () => {
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const r = await fetch("/api/battery/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tab: activeTab, industry: "lithium", stocks: stocksBrief }) });
      if (r.ok) { const data = await r.json(); const at = Date.now(); const summary = data.summary ?? null; setAnalysis({ scores: data.scores || [], conclusion: data.conclusion || "", summary, at }); saveAnalysis(activeTab, { scores: data.scores || [], conclusion: data.conclusion || "", summary, at }); }
      else {
        let detail = `请求失败 (${r.status})`;
        try { const e = await r.json(); if (e?.detail) detail = String(e.detail); } catch { /* keep status fallback */ }
        setAnalysisError(detail);
      }
    } catch (e) { setAnalysisError(e instanceof Error ? e.message : "网络错误"); }
    finally { setAnalyzing(false); }
  };

  const selectMajor = (major: string) => {
    setActiveMajor(major);
    setActiveSub(null);
    const idx = industryGroups.findIndex((g) => g.major === major);
    if (idx >= 0) {
      document.getElementById(`industry-${idx}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // ── 复用区块（总览 2×2 与板块 Tab 共用，避免 JSX 重复）──
  const briefPanel = <BriefPanel analysis={analysis} analyzing={analyzing} error={analysisError} onAnalyze={runAnalysis} />;
  const scorePanel = <ScorePanel scores={analysis?.scores ?? []} />;
  const newsPanel = (
    <div id="overview-news" className="rounded-xl border bg-card scroll-mt-28">
      <CardHeader
        title="产业新闻"
        action={
          <>
            <span className="text-sm text-muted-foreground mr-2">近一周 · 东方财富 · {newsItems.length} 条</span>
            <Button variant="ghost" onClick={fetchNews}>
              <RefreshCw className="h-3 w-3" />
              刷新
            </Button>
          </>
        }
      />
      <div className="p-4 max-h-[320px] overflow-y-auto">
        {newsItems.length === 0 && <p className="text-xs text-muted-foreground py-6 text-center">加载中…</p>}
        {newsItems.map((n, i) => (
          <div key={i} className="flex items-start gap-3 py-2 border-b last:border-0 text-sm">
            <span className="text-xs text-muted-foreground shrink-0 w-[4.5rem]">{n.date}</span>
            <span className="text-xs text-muted-foreground shrink-0 w-[4.5rem] truncate" title={n.source}>{n.source}</span>
            <a href={n.url} target="_blank" rel="noreferrer" className="flex-1 min-w-0 truncate hover:text-primary transition-colors">{n.title}</a>
          </div>
        ))}
      </div>
    </div>
  );
  const stockReportsPanel = (
    <div className="rounded-xl border bg-card">
      <CardHeader
        title="个股研报"
        action={
          <div className="flex items-center gap-3">
            {lastReportsTime && (
              <span className="text-xs text-muted-foreground">更新于 {lastReportsTime}</span>
            )}
            <Button variant="outline" onClick={fetchReports} disabled={fetchingReports}>
              <FileText className={"h-3.5 w-3.5 " + (fetchingReports ? "animate-pulse" : "")} />
              {fetchingReports ? "获取中…" : "一键获取"}
            </Button>
          </div>
        }
      />
      <div className="p-4 max-h-[320px] overflow-y-auto">
        {!fetchingReports && reports.length === 0 && <p className="text-xs text-muted-foreground py-6 text-center">点击「一键获取」拉取近三个月个股研报</p>}
        {fetchingReports && <p className="text-xs text-muted-foreground py-6 text-center">正在从东方财富拉取研报…</p>}
        {reports.slice(0, 40).map((r, i) => (
          <div key={i} className="flex items-start gap-3 py-2 border-b last:border-0 text-sm">
            <span className="text-xs text-muted-foreground shrink-0 w-[4.5rem]">{r.date}</span>
            <span className="text-xs text-muted-foreground shrink-0 w-[4.5rem] truncate" title={r.org}>{r.org}</span>
            <span className="text-xs font-medium shrink-0 w-[4rem] truncate" title={r.stockName}>{r.stockName}</span>
            <a href={"https://pdf.dfcfw.com/pdf/H3_" + r.infoCode + "_1.pdf"} target="_blank" rel="noreferrer" className="flex-1 min-w-0 truncate hover:text-primary transition-colors">{r.title}</a>
          </div>
        ))}
      </div>
    </div>
  );
  // 自选股票：个股文件细分板块分组，每只显示 价格/涨跌/成交量/换手率/主力净流入
  const watchlistPanel = <SectorWatchlist order={watchSectorOrder} sectors={watchSectors} data={watchData} flows={watchFlows} fetching={fetchingWatch} lastUpdate={lastWatchTime} onRefresh={fetchWatchlist} />;
  // 行业数据（指标图）：总览置于最下方，板块"行业研究"视图保留原位
  const industryDataPanel = (
    <div className="rounded-xl border border-border bg-slate-200/60 p-3 space-y-3">
      {/* 行业数据区：浅灰容器（与上方研究区/自选股的白卡视觉分组），内部为独立白卡 */}
      <div className="rounded-xl border bg-card">
      <CardHeader
        title="行业数据"
        action={
          <div className="flex items-center gap-3">
            {excelAsof && (
              <span className="whitespace-nowrap text-xs text-muted-foreground">
                数据截至 {excelAsof.replace(/-/g, "/")}
              </span>
            )}
            <Button
              variant="outline"
              onClick={() => fetchExcel()}
              disabled={fetchingExcel}
              title="从 Excel 重新加载指标目录与数据；已生成的速评需单独点「重新分析」更新"
            >
              <BarChart3 className={"h-3.5 w-3.5 " + (fetchingExcel ? "animate-pulse" : "")} />
              {fetchingExcel ? "加载中…" : "刷新行业数据"}
            </Button>
          </div>
        }
      />
      <div className="px-5 py-1 border-b">
        <p className="text-[10px] text-muted-foreground/70">
          数据来源：SMM、Mysteel、百川、i-Find、Wind及行业公开数据处理 · 环比口径：最新 vs 前 1/5/21 个交易日
        </p>
      </div>
      {SECTOR_GROUPS[activeTab] && (
        <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b">
          <span className="text-sm font-semibold text-slate-600">{activeTab}细分</span>
          {SECTOR_GROUPS[activeTab].map((sector) => (
            <button
              key={sector}
              onClick={() => selectSector(sector)}
              className={
                "px-4 py-1.5 text-sm font-semibold rounded-lg border transition " +
                (activeSector === sector
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-muted-foreground border-border hover:bg-accent hover:text-accent-foreground")
              }
            >
              {sector}
            </button>
          ))}
        </div>
      )}
      {!isOverviewTab && (
        <div className="px-5 py-3 border-b flex justify-center">
          <Button
            variant={selectedOnly ? "default" : "outline"}
            size="md"
            onClick={() => setSelectedOnly(v => !v)}
          >
            {selectedOnly ? "显示全部指标" : "仅显示已选中指标"}
          </Button>
        </div>
      )}
      </div>
      {/* 一键速评全部（仓单日报/成交持仓/各板块）：行业数据卡下方、仓单日报上方 */}
      {isOverviewTab && <SectorAnalysisAllToolbar groups={industryGroups} />}
      {/* 分仓库仓单明细表格（独立白卡）：仅总览 Tab 显示，具体板块不展示仓单 */}
      {isOverviewTab && (
        <div className="overflow-hidden rounded-xl border bg-card">
          <WarehouseReceiptTable dataset="lithium" />
        </div>
      )}
      {layoutMode === "1" ? (
        <>
          <IndustryDataScheme1
            excelCharts={excelCharts}
            fetchingExcel={fetchingExcel}
            industryGroups={industryGroups}
            activeMajor={activeMajor}
            setActiveMajor={setActiveMajor}
            activeSub={activeSub}
            setActiveSub={setActiveSub}
            showIndicatorTable={isOverviewTab}
          />
        </>
      ) : (
        <>
          <IndustryDataScheme2
            excelCharts={excelCharts}
            fetchingExcel={fetchingExcel}
            industryGroups={industryGroups}
            showIndicatorTable={isOverviewTab}
          />
        </>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-muted">
    <FloatingTargetNav items={industryGroups.map(g => g.major)} onSelect={selectMajor} groups={industryGroups} overviewLinks={isOverviewTab} receiptLinks={isOverviewTab} />
    <PageContainer maxWidth="wide">
      <IndustryTabBar tabs={TABS} activeTab={activeTab} onChange={switchTab} />

      <div className="border-t border-border" />
      {!isOverviewTab && (
        <IndustryViewToggle value={viewMode} onChange={setViewMode} />
      )}

      {isOverviewTab ? (
      <>
      {/* 顶部核心商品 KPI（本页面对应产业链 现货+期货主力，来自本地 Excel） */}
      <IndustryKpiBand dataset="lithium" />
      {/* 主力期货总体分析(总览 KPI 下方, 参考速评) */}
      <div className="mt-3">
        <KpiFutureAnalysis dataset="lithium" />
      </div>
      {/* ════ 总览：板块简评 | 评分维度 / 产业新闻 | 个股研报（2×2）═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {briefPanel}
        {scorePanel}
        {newsPanel}
        {stockReportsPanel}
      </div>

      {/* 自选股票 */}
      {watchlistPanel}

      {/* 行业数据（指标图，置于最下方） */}
      {industryDataPanel}
      </>
      ) : (
      <>
      {(viewMode === "行业研究") && <>
      {/* ════ 行业研究 ════ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {briefPanel}
        {scorePanel}
      </div>
      {industryDataPanel}
      </>}

      {(viewMode === "个股标的") && <>
      {/* ════ 个股标的：核心标的池/行情/财务 + 个股研报 ════ */}
      <IndividualStocksView codes={stockCodes} meta={stockMeta} onCodesChange={setStockCodes} />
      {stockReportsPanel}
      </>}
      </>
      )}
    </PageContainer>
    </div>
  );
}
