import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { IndividualStocksView } from "@/components/dashboard/IndividualStocksView";
import { WarehouseReceiptTable } from "@/components/dashboard/WarehouseReceiptTable";
import { SectorAnalysisAllToolbar } from "@/components/dashboard/SectorAnalysisAllToolbar";
import { StockQuickAnalysis } from "@/components/dashboard/StockQuickAnalysis";
import { RefreshBtn } from "@/components/ui/RefreshBtn";
import { useLayoutMode } from "@/hooks/useLayoutMode";
import { clearChartSeriesCache, loadChartData } from "@/lib/excelCache";
import { buildIndustryGroups } from "@/lib/industryGroups";
import type { ChartMeta } from "@/lib/chartTypes";

interface WatchStockRow {
  code: string; name: string; price: number; change_pct: number;
  volume: number; turnover_pct: number;
  open: number; high: number; low: number; last_close: number; amount_yi: number;
}
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
  // 自选股票（原行情总览区块）: 明细列含 今开/最高/最低/昨收/成交额(亿)
  const [watchData, setWatchData] = useState<Record<string, WatchStockRow>>({});
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
  // 板块简评/评分维度 临时隐藏开关: localStorage bt_show_study==="1" 时显示(默认隐藏)
  const showStudy = (() => {
    try {
      return localStorage.getItem("bt_show_study") === "1";
    } catch {
      return false;
    }
  })();
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
  // async: 定时自动刷新需要"等行情更新完成"再联动个股速评
  const fetchWatchlist = useCallback(async () => {
    // 冷却期（5 秒）内忽略重复点击，避免高频刷新触发数据源风控；
    // 冷却状态用 ref（不参与依赖），否则 fetchingWatch 翻转会触发 useEffect 循环刷新
    if (watchCodes.length === 0 || watchCooldownRef.current) return;
    watchCooldownRef.current = true;
    setFetchingWatch(true);
    try {
      // 行情 + 资金并发拉取, 都完成后返回(供定时自动刷新联动下游)
      const [d, fd] = await Promise.all([
        fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: watchCodes, sparkline: false }) })
          .then((r) => (r.ok ? r.json() : null)),
        fetch("/api/stocks/flow", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: watchCodes }) })
          .then((r) => (r.ok ? r.json() : null)),
      ]);
      if (d) {
        const m: Record<string, WatchStockRow> = {};
        (d.stocks || []).forEach((s: Record<string, unknown>) => {
          m[s.code as string] = {
            code: s.code as string, name: s.name as string,
            price: s.price as number, change_pct: s.change_pct as number,
            volume: (s.volume as number) || 0, turnover_pct: (s.turnover_pct as number) || 0,
            open: (s.open as number) || 0, high: (s.high as number) || 0,
            low: (s.low as number) || 0, last_close: (s.last_close as number) || 0,
            amount_yi: (s.amount_yi as number) || 0,
          };
        });
        setWatchData(m);
        setLastWatchTime(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      }
      if (fd) setWatchFlows(fd.flows || {});
    } catch {
      /* ignore */
    } finally {
      setTimeout(() => {
        watchCooldownRef.current = false;
        setFetchingWatch(false);
      }, 5000);
    }
  }, [watchCodes]);
  useEffect(() => { void fetchWatchlist(); }, [fetchWatchlist]);
  // 首开自动拉取个股研报(总览, 无缓存时自动拉一次; 免费数据接口, 避免每次手动点)
  const reportsAutoRef = useRef(false);
  useEffect(() => {
    if (!isOverviewTab || reportsAutoRef.current) return;
    if (watchCodes.length === 0) return; // 股票池尚未就绪
    reportsAutoRef.current = true;
    if (reports.length === 0) void fetchReports();
  }, [isOverviewTab, watchCodes, reports, fetchReports]);
  // 定时自动刷新完成回调: 立即联动个股速评(其内部会再拉最新行情, 不会用旧数据)
  const refreshStockQuick = useCallback(() => {
    quickAnalysisBus.run("stock_analysis_v2_lithium");
  }, []);
  // 顶部 KPI 行手动刷新回调: 联动主力期货总体分析同步更新(30s 自动轮询不触发 AI)
  const refreshFutureAnalysis = useCallback(() => {
    quickAnalysisBus.run("future_analysis_v2_lithium");
  }, []);

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
            <RefreshBtn onClick={fetchNews} title="重新拉取产业新闻" />
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
            <RefreshBtn onClick={fetchReports} loading={fetchingReports} title="拉取近三个月个股研报" />
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
  // (自选与个股速评由外层白卡统一包裹, 组件自身 flush 不套卡壳)
  // 行业数据(指标图)标题行: 不再独立白卡, 直接置于灰底容器内与下方具体板块图同底融合
  // (标题/数据截至/刷新 + 数据来源说明 + 板块 Tab 的细分切换)
  const industryHeaderBlock = (
    <div id="industry-data-title" className="mt-5 space-y-2 px-1 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          {/* 标题字号大于具体板块标题(板块 major = 24px), 突出"行业数据"为总览数据总标题 */}
          <span className="text-3xl font-extrabold tracking-tight text-foreground">行业数据</span>
          {excelAsof && (
            <span className="whitespace-nowrap text-sm text-muted-foreground">
              数据截至 {excelAsof.replace(/-/g, "/")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground/70">
            数据来源：SMM、Mysteel、百川、i-Find、Wind及行业公开数据处理 · 环比：最新 vs 前 1/5/21 个交易日
          </span>
          <RefreshBtn onClick={() => fetchExcel()} loading={fetchingExcel} title="从 Excel 重新加载指标目录与数据；已生成的速评需单独点「重新分析」更新" />
        </div>
      </div>
      {SECTOR_GROUPS[activeTab] && (
        <div className="flex flex-wrap items-center gap-2">
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
        <div className="flex justify-center">
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
  );
  // 行业数据(具体板块指标图区): 总览顺序 = 一键速评全部 → 仓单日报 → 标题行 → 锂矿等具体板块图,
  // 使"行业数据"标题行(数据截至/刷新)紧贴其下方的锂矿板块; 板块 Tab(行业研究)保留标题行在顶部
  const industryDataPanel = (
    <div className="rounded-xl border border-border bg-slate-200/60 p-3 space-y-3">
      {isOverviewTab && <SectorAnalysisAllToolbar groups={industryGroups} autoFill />}
      {isOverviewTab && (
        <div className="overflow-hidden rounded-xl border bg-card">
          <WarehouseReceiptTable dataset="lithium" liveOnly />
        </div>
      )}
      {industryHeaderBlock}
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
      <IndustryTabBar
        tabs={TABS}
        activeTab={activeTab}
        onChange={switchTab}
        labels={{ "电解液产业链": "电解液" }}
      />

      <div className="border-t border-border" />
      {!isOverviewTab && (
        <IndustryViewToggle value={viewMode} onChange={setViewMode} />
      )}

      {isOverviewTab ? (
      <>
      {/* ════ 顶部核心价格区: KPI 行 + 主力期货总体分析 同一白卡(融合), 刷新按钮只在第一行 ════ */}
      <div className="mt-3 overflow-hidden rounded-xl border bg-card">
        <IndustryKpiBand dataset="lithium" onManualRefresh={refreshFutureAnalysis} />
        <div className="border-t border-border/70">
          <KpiFutureAnalysis dataset="lithium" flush />
        </div>
      </div>
      {/* ════ 总览：产业新闻 | 个股研报（板块简评/评分维度按需显示: localStorage bt_show_study="1"）═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {showStudy && briefPanel}
        {showStudy && scorePanel}
        {newsPanel}
        {stockReportsPanel}
      </div>

      {/* ════ 个股股票部分: 自选股票 + 个股速评 共用同一白卡(视觉连成一体) ════ */}
      <div id="stock-panel" className="mt-3 overflow-hidden rounded-xl border bg-card">
        <SectorWatchlist
          flush
          order={watchSectorOrder}
          sectors={watchSectors}
          data={watchData}
          flows={watchFlows}
          fetching={fetchingWatch}
          lastUpdate={lastWatchTime}
          onRefresh={fetchWatchlist}
          onAutoCycle={refreshStockQuick}
        />
        <div className="border-t border-border/70">
          <StockQuickAnalysis
            flush
            dataset="lithium"
            order={watchSectorOrder}
            sectors={watchSectors}
            codes={watchCodes}
            data={watchData}
            flows={watchFlows}
          />
        </div>
      </div>

      {/* 行业数据（指标图，置于最下方） */}
      {industryDataPanel}
      </>
      ) : (
      <>
      {(viewMode === "行业研究") && <>
      {/* ════ 行业研究 ════ */}
      {showStudy && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {briefPanel}
        {scorePanel}
      </div>
      )}
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
