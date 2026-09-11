import { useCallback, useEffect, useState } from "react";
import { PositionQuickAnalysis } from "@/components/dashboard/PositionQuickAnalysis";
import { InstitutionPositionTable } from "@/components/dashboard/InstitutionPositionTable";
import { RefreshBtn } from "@/components/ui/RefreshBtn";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";

// 各合约成交持仓（仓单日报下方的汇总表，参考"成交持仓参考图片"形态）：
// 数据源 = 新浪公开行情实时(主力/各上市月合约 最新价/当日量/持仓, 30s 轮询);
// 实时不可用时自动回退 本地 Excel 目录聚合(收盘价/成交量/持仓量)。
// 列序 = 合约 | 最新价 | 成交量 | 持仓量 | 成交额(资金) | 成交持仓比。
// 量能格：条形在前 → 主数值 → 红涨绿跌的增减以括号形式紧随数值；列名居中。
// 成交额(元) = 成交量(手)×最新价×合约乘数(吨/手)，为最新价近似口径。
// 日增减(实时)来自本地每日收盘快照（收盘后自动存档；接入当日无快照显示 —）。

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

type SourceMode = "live" | "excel";

// 涨跌着色：正值红色、负值绿色、零/无灰色（与页面行情配色一致）
const cc = (v: number | null) => {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-red-500" : "text-green-500";
};

const fmtNum = (v: number | null) => (v == null ? "—" : Math.round(v).toLocaleString("zh-CN"));

const fmtSigned = (v: number | null) => {
  if (v == null) return "—";
  const s = v > 0 ? "+" : "";
  return s + (Math.abs(v) >= 10000 ? (v / 10000).toFixed(1) + "万" : String(Math.round(v)));
};

// 成交持仓比统一按百分数展示（ratio = 成交量/持仓量 → ×100%）
const fmtRatioPct = (v: number | null) => (v == null ? "—" : (v * 100).toFixed(1) + "%");

// 成交额(元)：≥1亿 显示 x.xx亿；≥1万 显示 x.x万；以下显示整数元
const fmtFund = (v: number | null) => {
  if (v == null) return "—";
  if (v >= 1e8) return (v / 1e8).toFixed(2) + "亿";
  if (v >= 1e4) return (v / 1e4).toFixed(1) + "万";
  return String(Math.round(v));
};

// 量能格：条形在前(轨道铺满列内剩余) → 主数值 → 红绿增减以括号形式紧随数值
function BarCell({
  max,
  value,
  colorClass,
  delta,
  title,
  format = fmtNum,
}: {
  max: number;
  value: number | null;
  colorClass: string;
  delta?: number | null;
  title?: string;
  format?: (v: number | null) => string;
}) {
  return (
    <div className="flex items-center gap-1.5" title={title}>
      <div className="h-4 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={"h-full rounded-full " + colorClass}
          style={{ width: value == null ? "0%" : `${Math.min(100, (Math.max(0, value) / max) * 100)}%` }}
        />
      </div>
      <span className="min-w-[3.8rem] shrink-0 text-right text-sm font-medium tabular-nums text-foreground">
        {format(value)}
      </span>
      {delta !== undefined &&
        (delta == null ? (
          // 无前日基线(新接入/新上市合约): 括号内显示 —, 不静默消失
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">(—)</span>
        ) : (
          <span className={"shrink-0 text-[11px] tabular-nums " + cc(delta)}>({fmtSigned(delta)})</span>
        ))}
    </div>
  );
}

export function ContractPositionTable({ dataset }: { dataset: string }) {
  const [groups, setGroups] = useState<PositionGroup[] | null>(null);
  const [mode, setMode] = useState<SourceMode>("live");
  const [dataDate, setDataDate] = useState("");
  const [dataTime, setDataTime] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  // 排序：默认按持仓量降序；可切 合约(主力置顶+月份序)/最新价/成交量/成交额/成交比
  const [sortKey, setSortKey] = useState<"contract" | "price" | "vol" | "oi" | "turnover" | "ratio">("oi");
  const [sortAsc, setSortAsc] = useState(false);
  const SORT_KEYS: { key: typeof sortKey; label: string }[] = [
    { key: "contract", label: "合约" },
    { key: "price", label: "最新价" },
    { key: "vol", label: "成交量" },
    { key: "oi", label: "持仓量" },
    { key: "turnover", label: "成交额" },
    { key: "ratio", label: "成交比" },
  ];
  const toggleSort = (key: typeof sortKey) => {
    if (key === sortKey) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(key === "contract"); // 合约键默认升序，其余键默认降序
    }
  };
  const cmpSort = (a: number | null, b: number | null): number => {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    const d = a - b;
    return sortAsc ? d : -d;
  };

  // 加载: 实时(新浪)优先, 失败/为空回退 Excel
  const load = useCallback(async () => {
    let d: { ok?: boolean; groups?: PositionGroup[]; date?: string; time?: string } | null = null;
    try {
      const r = await fetch(`/api/industry/positions-live?dataset=${dataset}`);
      d = r.ok ? await r.json() : null;
    } catch {
      d = null;
    }
    if (d?.ok && d.groups?.length) {
      setGroups(d.groups || []);
      setMode("live");
      setDataDate(d.date || "");
      setDataTime(d.time || "");
      return;
    }
    try {
      const r = await fetch(`/api/industry/positions?dataset=${dataset}`);
      d = r.ok ? await r.json() : null;
    } catch {
      d = null;
    }
    if (d?.ok && d.groups?.length) {
      setGroups(d.groups || []);
      setMode("excel");
      setDataDate("");
      setDataTime("");
    }
  }, [dataset]);

  useEffect(() => {
    void load();
    // 30s 轮询(实时跳动; Excel 兜底模式也继续尝试恢复实时源)
    const t = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(t);
  }, [load]);

  // 手动刷新(立即重拉; 转圈表示进行中); 完成后再联动机构持仓与成交持仓速评同步更新
  const refreshNow = async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
      quickAnalysisBus.run(`institution_refresh_v2_${dataset}`);
      quickAnalysisBus.run(`positions_analysis_v2_${dataset}`);
    }
  };

  if (!groups || groups.length === 0) return null;

  const dateNote =
    mode === "live"
      ? `数据截至 ${dataDate.replace(/-/g, "/")}${dataTime.length >= 4 ? ` ${dataTime.slice(0, 2)}:${dataTime.slice(2, 4)}` : ""}`
      : (() => {
          for (const g of groups) {
            const d = g.rows.find((r) => r.date)?.date;
            if (d) return `数据截至 ${d.replace(/-/g, "/")}`;
          }
          return "来源：本地 Excel";
        })();

  return (
    <div id="contract-positions" className="scroll-mt-28">
      {/* 标题行：字号/排序控件与"仓单日报"同款 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-3 text-lg">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground">各合约成交持仓</span>
          {mode === "live" && (
            <span className="flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1 text-[10px] font-semibold text-primary">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              实时
            </span>
          )}
          <span className="text-[10px] text-muted-foreground/70">{dateNote}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* 手动刷新按钮(立即重拉实时数据) */}
          <RefreshBtn onClick={refreshNow} loading={refreshing} title="立即刷新实时数据" />
          {/* 排序控件 */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground/70">排序</span>
          {SORT_KEYS.map(({ key, label }) => {
            const active = sortKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleSort(key)}
                title="点击切换排序键；再次点击切换升/降序"
                className={
                  "flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm font-medium transition " +
                  (active
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted/40")
                }
              >
                {label}
                {active && <span className="text-xs">{sortAsc ? "↑" : "↓"}</span>}
              </button>
            );
          })}
          </div>
        </div>
      </div>
      {/* 每组一表（如硅 = 多晶硅/工业硅 两表） */}
      <div className="space-y-2 px-4 py-2">
        {groups.map((g) => {
          // 主力 = 组内持仓量最大的合约（实时）；Excel 模式为标题"主力"行
          const mainContract =
            mode === "live"
              ? g.rows.reduce((a, b) => ((b.oi ?? -1) > (a.oi ?? -1) ? b : a), g.rows[0]).contract
              : g.rows.some((r) => r.contract === "主力")
                ? "主力"
                : null;
          // 合约排序值: 主力=0 置顶, 其余按到期月序(Excel 01..12 / 实时 YYMM)
          const contractRankOf = (r: PositionRow): number =>
            r.contract === mainContract ? 0 : parseInt(r.contract, 10) || 99;
          const sortValueOf = (r: PositionRow): number | null => {
            if (sortKey === "contract") return contractRankOf(r);
            if (sortKey === "price") return r.price;
            if (sortKey === "vol") return r.vol;
            if (sortKey === "turnover") return r.turnover;
            if (sortKey === "ratio") return r.ratio;
            return r.oi;
          };
          const sorted = [...g.rows].sort((x, y) => cmpSort(sortValueOf(x), sortValueOf(y)));
          const shown = sorted; // 全部合约展开(不做收起)
          const volMax = Math.max(1, ...sorted.map((r) => r.vol ?? 0));
          const oiMax = Math.max(1, ...sorted.map((r) => r.oi ?? 0));
          const turnMax = Math.max(1, ...sorted.map((r) => r.turnover ?? 0));
          return (
            <div key={g.product}>
              {/* 品种区分行 */}
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-sm font-bold text-foreground">{g.product}</span>
                <span className="text-[10px] text-muted-foreground/70">
                  {mode === "live" ? "主力(持仓最大) + 上市月合约" : "主力+各月份"} · 共 {sorted.length} 个合约
                  {mode === "live" ? " · 30s 自动刷新" : ""}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1340px] table-fixed whitespace-nowrap text-sm [&_td]:px-3 [&_th]:px-3">
                  <colgroup>
                    <col style={{ width: "8%" }} />
                    <col style={{ width: "9%" }} />
                    <col style={{ width: "22%" }} />
                    <col style={{ width: "22%" }} />
                    <col style={{ width: "23%" }} />
                    <col style={{ width: "16%" }} />
                  </colgroup>
                  <thead>
                    <tr className="border-b border-border text-center text-muted-foreground">
                      <th className="sticky top-0 z-10 bg-card px-1.5 py-1 text-[15px] font-bold">合约</th>
                      <th className="sticky top-0 z-10 bg-card px-1.5 py-1 font-medium">最新价</th>
                      <th className="sticky top-0 z-10 bg-card px-1.5 py-1 font-medium">成交量(手)</th>
                      <th className="sticky top-0 z-10 bg-card px-1.5 py-1 font-medium">持仓量(手)</th>
                      <th
                        className="sticky top-0 z-10 bg-card px-1.5 py-1 font-medium"
                        title="成交额 ≈ 当日成交量 × 最新价 × 合约乘数(吨/手)"
                      >
                        成交额(资金)
                      </th>
                      <th className="sticky top-0 z-10 bg-card px-1.5 py-1 font-medium">成交持仓比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.contract} className="border-b border-border/60 hover:bg-muted/40">
                        <td className="max-w-[150px] px-1.5 py-1 text-center">
                          {r.contract === mainContract ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="inline-flex items-center rounded bg-primary/10 px-1.5 py-px font-bold text-primary">
                                主力
                              </span>
                              {mode === "live" && (
                                <span className="font-medium tabular-nums">{r.contract}</span>
                              )}
                            </span>
                          ) : (
                            <span className="font-medium tabular-nums">{r.contract}</span>
                          )}
                        </td>
                        {/* 最新价：纯数值、列内居中，无条形 */}
                        <td className="px-1.5 py-1 text-center text-sm font-medium tabular-nums text-foreground">
                          {r.price != null ? Math.round(r.price).toLocaleString("zh-CN") : "—"}
                        </td>
                        <td className="px-1.5 py-1">
                          <BarCell
                            max={volMax}
                            value={r.vol}
                            colorClass="bg-slate-400/80"
                            delta={r.d_vol}
                            title={`成交量 ${fmtNum(r.vol)} 手${r.d_vol == null ? "（当日接入暂无日增减）" : `，较前日 ${fmtSigned(r.d_vol)} 手`}`}
                          />
                        </td>
                        <td className="px-1.5 py-1">
                          <BarCell
                            max={oiMax}
                            value={r.oi}
                            colorClass="bg-slate-500/80"
                            delta={r.d_oi}
                            title={`持仓量 ${fmtNum(r.oi)} 手${r.d_oi == null ? "（当日接入暂无日增减）" : `，较前日 ${fmtSigned(r.d_oi)} 手`}`}
                          />
                        </td>
                        <td className="px-1.5 py-1">
                          <BarCell
                            max={turnMax}
                            value={r.turnover}
                            colorClass="bg-slate-600/85"
                            format={fmtFund}
                            title={`成交额 ≈ 成交量 ${fmtNum(r.vol)} 手 × 最新价 ${fmtNum(r.price)} × 合约乘数（近似）`}
                          />
                        </td>
                        {/* 成交持仓比：纯数值、列内居中，无条形 */}
                        <td className="px-1.5 py-1 text-center text-sm tabular-nums text-muted-foreground">
                          {fmtRatioPct(r.ratio)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>
      {/* 各机构成交持仓：交易所会员持仓排名(收盘后日度, akshare→交易所官网) */}
      <InstitutionPositionTable dataset={dataset} />
      {/* 成交持仓速评 */}
      <PositionQuickAnalysis dataset={dataset} />
    </div>
  );
}
