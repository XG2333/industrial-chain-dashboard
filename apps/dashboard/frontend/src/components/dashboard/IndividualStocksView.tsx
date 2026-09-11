import { useEffect, useState } from "react";
import { Plus, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";
import { FinChart } from "@/components/charts/FinChart";
import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { TrendChart } from "@/components/charts/TrendChart";

// 个股标的视图（板块 Tab"个股标的"切换）：恢复旧版三大区块内容 —
// 核心标的池(详细宽卡) / 行情数据(季节性+近一年+近一月) / 财务数据(营收净利 4 图)。
// 数据自管理拉取：行情 /api/watchlist(sparkline)、K线 /api/battery/market-data、
// 财报 /api/battery/financials；代码池由页面传入（板块默认池/用户自管，可编辑）。

interface StockDetail {
  code: string; name: string; price: number; change_pct: number;
  open: number; high: number; low: number; last_close: number;
  turnover_pct: number; amount_yi: number;
  pe_ttm: number; pb: number; mcap_yi: number; float_mcap_yi: number;
  limit_up: number; limit_down: number; sparkline: number[];
}
interface Kline { date: string; value: number }
interface FinPeriod { period: string; rev: number; rev_yoy: number | null; profit: number; profit_yoy: number | null }

interface IndividualStocksViewProps {
  codes: string[];
  meta: Record<string, { name?: string; segment?: string; subs?: string[] }>;
  onCodesChange: (codes: string[]) => void;
}

const cc = (pct: number) => pct === 0 ? "text-muted-foreground" : pct > 0 ? "text-red-500" : "text-green-500";

function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  const w = 160, h = 40;
  if (data.length < 2) return <div style={{ width: w, height: h }} className="shrink-0 rounded border bg-muted/30" />;
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
  const pw = w - 2, ph = h - 2, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (pw - pad * 2);
    const y = ph - pad - ((v - min) / range) * (ph - pad * 2);
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  return (
    <div className="shrink-0 rounded border bg-muted/20" style={{ width: w, height: h }}>
      <svg width={pw} height={ph} className="m-[1px]">
        <polyline points={pts} fill="none" stroke={up ? "#ef4444" : "#22c55e"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity={0.8} />
      </svg>
    </div>
  );
}

function DetailCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return <div className="flex justify-between gap-2"><span className="text-muted-foreground whitespace-nowrap">{label}</span><span className={"font-medium text-right " + (color || "")}>{value}</span></div>;
}

export function IndividualStocksView({ codes, meta, onCodesChange }: IndividualStocksViewProps) {
  const [details, setDetails] = useState<StockDetail[]>([]);
  const [market, setMarket] = useState<Record<string, Kline[]>>({});
  const [fin, setFin] = useState<Record<string, FinPeriod[]>>({});
  const [reload, setReload] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [addCode, setAddCode] = useState("");

  useEffect(() => {
    if (codes.length === 0) { setDetails([]); return; }
    let cancelled = false;
    fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: codes, sparkline: true }) })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!cancelled && d) setDetails((d.stocks || []).map((s: Record<string, unknown>) => ({
        code: s.code as string, name: s.name as string, price: s.price as number, change_pct: s.change_pct as number,
        open: s.open as number, high: s.high as number, low: s.low as number, last_close: s.last_close as number,
        turnover_pct: s.turnover_pct as number, amount_yi: s.amount_yi as number,
        pe_ttm: s.pe_ttm as number, pb: s.pb as number, mcap_yi: s.mcap_yi as number, float_mcap_yi: s.float_mcap_yi as number,
        limit_up: s.limit_up as number, limit_down: s.limit_down as number, sparkline: (s.sparkline || []) as number[],
      }))); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [codes, reload]);

  // K线(近 250 交易日, 供季节性/一年/一月走势)
  useEffect(() => {
    if (codes.length === 0) { setMarket({}); return; }
    let cancelled = false;
    fetch("/api/battery/market-data", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: codes }) })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!cancelled && d) { const m: Record<string, Kline[]> = {}; (d.stocks || []).forEach((s: Record<string, unknown>) => { m[s.code as string] = (s.klines || []) as Kline[]; }); setMarket(m); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [codes, reload]);

  // 财报(前 6 只, 营收/净利 年度+季度)
  useEffect(() => {
    const six = codes.slice(0, 6);
    if (six.length === 0) { setFin({}); return; }
    let cancelled = false;
    fetch("/api/battery/financials", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stocks: six }) })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!cancelled && d) { const m: Record<string, FinPeriod[]> = {}; (d.stocks || []).forEach((s: Record<string, unknown>) => { m[s.code as string] = ((s.periods || []) as Record<string, unknown>[]).map(p => ({ period: p.period as string, rev: (p["营业总收入"] as number) || 0, rev_yoy: (p["营业总收入_yoy"] as number) ?? null, profit: (p["净利润"] as number) || 0, profit_yoy: (p["净利润_yoy"] as number) ?? null })); }); setFin(m); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [codes, reload]);

  const addStock = () => {
    const c = addCode.trim();
    if (c && /^\d{6}$/.test(c) && !codes.includes(c)) onCodesChange([...codes, c]);
    setAddCode("");
  };
  const removeStock = (code: string) => onCodesChange(codes.filter(c => c !== code));

  const seg = (code: string) => meta[code]?.segment;
  const nm = (code: string) => details.find(d => d.code === code)?.name || meta[code]?.name || code;

  return (
    <div className="space-y-4">
      {/* ── 核心标的池：详细宽卡（价格/明细/走势） ── */}
      <div className="rounded-xl border bg-card">
        <CardHeader
          title="核心标的池"
          action={
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={() => setReload(v => v + 1)}>
                <RefreshCw className="h-3 w-3" />
                刷新
              </Button>
              <Button variant={editMode ? "default" : "ghost"} onClick={() => setEditMode(v => !v)}>
                {editMode ? "完成" : "管理"}
              </Button>
            </div>
          }
        />
        <div className="max-h-[600px] space-y-4 overflow-y-auto p-4">
          {editMode && (
            <div className="flex gap-2">
              <input
                value={addCode}
                onChange={e => setAddCode(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addStock(); }}
                placeholder="输入6位股票代码"
                maxLength={6}
                className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs text-foreground outline-none"
              />
              <Button variant="outline" size="md" onClick={addStock}>
                <Plus className="h-3 w-3" />添加
              </Button>
            </div>
          )}
          {details.length === 0 && codes.length === 0 && (
            <p className="py-4 text-center text-xs text-muted-foreground">该板块暂无标的（可在总览自选股票中查看）</p>
          )}
          {details.length === 0 && codes.length > 0 && (
            <p className="py-4 text-center text-xs text-muted-foreground">加载中…</p>
          )}
          {details.map(s => {
            const up = s.change_pct > 0, flat = s.change_pct === 0; const cls = cc(s.change_pct);
            return (
              <div key={s.code} className="rounded-lg border p-4 transition-shadow hover:shadow-sm">
                <div className="flex gap-4">
                  <div className="flex shrink-0 flex-col items-start gap-1.5" style={{ width: 180 }}>
                    <div className="flex items-baseline gap-1">
                      <span className="text-xs text-muted-foreground">{s.code}</span>
                      <span className="ml-1 text-sm font-medium">{s.name}</span>
                      {seg(s.code) && <span className="ml-1 text-xs text-muted-foreground/70">{seg(s.code)}</span>}
                    </div>
                    <div><span className="text-2xl font-bold tracking-tight">{s.price.toFixed(2)}</span></div>
                    <span className={"text-sm font-semibold " + cls}>{flat ? "0.00" : (up ? "+" : "") + s.change_pct.toFixed(2) + "%"}</span>
                    <Sparkline data={s.sparkline} up={up} />
                  </div>
                  <div className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3 lg:grid-cols-4">
                    <DetailCell label="今开" value={s.open?.toFixed(2) || "-"} />
                    <DetailCell label="最高" value={s.high?.toFixed(2) || "-"} color="text-red-500" />
                    <DetailCell label="最低" value={s.low?.toFixed(2) || "-"} color="text-green-500" />
                    <DetailCell label="昨收" value={s.last_close?.toFixed(2) || "-"} />
                    <DetailCell label="换手率" value={(s.turnover_pct || 0).toFixed(2) + "%"} />
                    <DetailCell label="成交额" value={(s.amount_yi || 0).toFixed(2) + " 亿"} />
                    <DetailCell label="PE(TTM)" value={s.pe_ttm > 0 ? s.pe_ttm.toFixed(1) : "-"} />
                    <DetailCell label="PB" value={s.pb > 0 ? s.pb.toFixed(2) : "-"} />
                    <DetailCell label="总市值" value={s.mcap_yi > 0 ? s.mcap_yi.toFixed(0) + " 亿" : "-"} />
                    <DetailCell label="流通市值" value={s.float_mcap_yi > 0 ? s.float_mcap_yi.toFixed(0) + " 亿" : "-"} />
                    <DetailCell label="涨停" value={s.limit_up > 0 ? s.limit_up.toFixed(2) : "-"} color="text-red-500" />
                    <DetailCell label="跌停" value={s.limit_down > 0 ? s.limit_down.toFixed(2) : "-"} color="text-green-500" />
                  </div>
                  {editMode && <button onClick={() => removeStock(s.code)} className="shrink-0 self-start text-muted-foreground hover:text-red-500"><X className="h-4 w-4" /></button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 行情数据：季节性 / 近一年 / 近一月 ── */}
      <div className="rounded-xl border bg-card">
        <CardHeader title="行情数据" />
        <div className="max-h-[720px] space-y-6 overflow-y-auto p-4">
          {codes.slice(0, 8).map(code => {
            const klines = market[code] || [];
            const d1m = klines.slice(-22);
            const d1y = klines.slice(-250);
            const seasonal = klines.filter(k => k.date >= "2022-01-01");
            const chg1y = d1y.length >= 2 ? ((d1y[d1y.length - 1].value / d1y[0].value - 1) * 100) : null;
            const chg1m = d1m.length >= 2 ? ((d1m[d1m.length - 1].value / d1m[0].value - 1) * 100) : null;
            const chgCls = (v: number | null) => v == null ? "" : (v >= 0 ? "text-red-500" : "text-green-500");
            const chgSign = (v: number | null) => v == null ? "" : (v >= 0 ? "+" : "");
            return (
              <div key={code}>
                <p className="mb-2 text-sm font-semibold">
                  {code} {nm(code)}
                  {seg(code) && <span className="ml-2 text-xs font-normal text-muted-foreground/70">{seg(code)}</span>}
                </p>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">2022-2026 收盘价季节性</p>
                    <SeasonalChart title="" unit="元" data={seasonal.map(k => ({ date: k.date, value: k.value }))} freq="daily" />
                  </div>
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">
                      近一年收盘价走势
                      {chg1y != null && <span className={"ml-1 " + chgCls(chg1y)}>({chgSign(chg1y)}{chg1y.toFixed(2)}%)</span>}
                    </p>
                    <TrendChart title={code} unit="元" data={d1y} />
                  </div>
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">
                      近一月收盘价走势
                      {chg1m != null && <span className={"ml-1 " + chgCls(chg1m)}>({chgSign(chg1m)}{chg1m.toFixed(2)}%)</span>}
                    </p>
                    <TrendChart title={code} unit="元" data={d1m} />
                  </div>
                </div>
              </div>
            );
          })}
          {codes.length > 0 && Object.keys(market).length === 0 && (
            <p className="py-6 text-center text-xs text-muted-foreground">加载中…</p>
          )}
        </div>
      </div>

      {/* ── 财务数据：营收/净利 年度+季度 ── */}
      <div className="rounded-xl border bg-card">
        <CardHeader title="财务数据" />
        <div className="max-h-[1000px] space-y-8 overflow-y-auto p-4">
          {codes.slice(0, 6).map(code => {
            const periods = fin[code] || [];
            const annual = periods.filter(p => p.period >= "2021-01-01" && p.period <= "2025-12-31" && p.period.endsWith("-12-31")).reverse();
            const quarterly = periods.filter(p => p.period >= "2023-01-01" && p.period <= "2026-06-30").reverse();
            return (
              <div key={code}>
                <p className="mb-2 text-sm font-semibold">
                  {code} {nm(code)}
                  {seg(code) && <span className="ml-2 text-xs font-normal text-muted-foreground/70">{seg(code)}</span>}
                </p>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">营业收入（年度）单位：亿</p>
                    <FinChart data={annual.map(p => ({ period: p.period, value: p.rev, yoy: p.rev_yoy }))} title="营收年度" isAnnual />
                  </div>
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">累计营业收入（季度）单位：亿</p>
                    <FinChart data={quarterly.map(p => ({ period: p.period, value: p.rev, yoy: p.rev_yoy }))} title="营收季度" />
                  </div>
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">净利润（年度）单位：亿</p>
                    <FinChart data={annual.map(p => ({ period: p.period, value: p.profit, yoy: p.profit_yoy }))} title="净利年度" isAnnual />
                  </div>
                  <div className="rounded-lg border p-2">
                    <p className="mb-1 text-[10px] text-muted-foreground">累计净利润（季度）单位：亿</p>
                    <FinChart data={quarterly.map(p => ({ period: p.period, value: p.profit, yoy: p.profit_yoy }))} title="净利季度" />
                  </div>
                </div>
              </div>
            );
          })}
          {codes.length > 0 && Object.keys(fin).length === 0 && (
            <p className="py-6 text-center text-xs text-muted-foreground">加载中…</p>
          )}
        </div>
      </div>
    </div>
  );
}
