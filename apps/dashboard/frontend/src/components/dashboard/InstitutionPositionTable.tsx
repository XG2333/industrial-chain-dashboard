import { useCallback, useEffect, useRef, useState } from "react";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";

// 各机构成交持仓（各合约成交持仓下方）：交易所会员持仓排名(收盘后公布, akshare→交易所官网)。
// 形态与交易所/东财一致：成交量 / 多头持仓 / 空头持仓 三栏各自独立排名(同行会员可不同)。
// 仅收盘后更新(盘中显示上一交易日)；每品种展示其主力合约的前 12 名。
// 数值条：量/多/空 各栏按自身最大值归一；多头红、空头绿、成交量灰(资金方向语义)。

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

// 涨跌着色：正红、负绿、零/无灰
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

// 栏格：机构名(定宽、文字右对齐贴条) → 条形缩短为固定宽并从同一起点左对齐 →
// 主数值(右对齐) → 红涨绿跌括号紧随。名称定宽使每行条形起点完全一致。
function InstCell({
  max,
  member,
  value,
  delta,
  barColor,
}: {
  max: number;
  member: string;
  value: number | null;
  delta: number | null;
  barColor: string;
}) {
  return (
    <div className="flex items-center gap-1.5" title={`${member} ${fmtNum(value)} 手${delta == null ? "" : `，较前日 ${fmtSigned(delta)} 手`}`}>
      <p className="w-[7em] shrink-0 truncate text-right text-[15px] font-medium leading-none text-foreground">{member}</p>
      <div className="h-4 w-36 shrink-0 overflow-hidden rounded-full bg-muted">
        <div
          className={"h-full rounded-full " + barColor}
          style={{ width: value == null ? "0%" : `${Math.min(100, (Math.max(0, value) / max) * 100)}%` }}
        />
      </div>
      <span className="min-w-[4.2rem] shrink-0 text-right text-[15px] font-medium tabular-nums text-foreground">
        {fmtNum(value)}
      </span>
      {delta != null && (
        <span className={"shrink-0 text-xs tabular-nums " + cc(delta)}>({fmtSigned(delta)})</span>
      )}
    </div>
  );
}

export function InstitutionPositionTable({ dataset }: { dataset: string }) {
  const [groups, setGroups] = useState<InstGroup[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/industry/institution-positions?dataset=${dataset}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d?.ok) setGroups(d.groups || []);
    } catch {
      /* ignore */
    }
  }, [dataset]);

  useEffect(() => {
    void load();
  }, [load]);

  // 手动刷新(机构为收盘后日度, 主要用于收盘后/次日获取新一日报表)
  const refreshNow = async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  // 由上方「各合约成交持仓」刷新按钮联动触发(本区不再单设按钮)
  const runRef = useRef<() => Promise<void>>(async () => {});
  runRef.current = refreshNow;
  useEffect(() => {
    const h = () => {
      void runRef.current();
    };
    quickAnalysisBus.onRun(`institution_refresh_v2_${dataset}`, h);
    return () => quickAnalysisBus.offRun(`institution_refresh_v2_${dataset}`, h);
  }, [dataset]);

  if (!groups || groups.length === 0) return null;

  const dateNote = (() => {
    for (const g of groups) {
      if (g.date) return `数据截至 ${g.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1/$2/$3")} 收盘`;
    }
    return "";
  })();

  return (
    <div id="institution-positions" className="mt-4 scroll-mt-28 border-t border-border/60 pt-3">
      {/* 标题行（与"仓单日报"同款字号） */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 text-lg">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground">各机构成交持仓</span>
          <span className="text-[10px] text-muted-foreground/70">
            {dateNote
              ? `交易所会员持仓排名 · ${dateNote} · 量/多/空三栏独立排名`
              : "交易所会员持仓排名 · 收盘后更新"}
          </span>
        </div>
        {/* 刷新统一由上方「各合约成交持仓」按钮联动, 本区不再单设 */}
      </div>
      <div className="space-y-2 px-4 py-2">
        {groups.map((g) => {
          const volMax = Math.max(1, ...g.rows.map((r) => r.vol ?? 0));
          const longMax = Math.max(1, ...g.rows.map((r) => r.long_oi ?? 0));
          const shortMax = Math.max(1, ...g.rows.map((r) => r.short_oi ?? 0));
          // 全部排名展开显示(不做收起)
          const shown = g.rows;
          return (
            <div key={`${g.product}-${g.contract}`}>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-sm font-bold text-foreground">{g.product}</span>
                <span className="text-[10px] text-muted-foreground/70">
                  主力 {g.contract} · 共 {g.rows.length} 名
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1400px] table-fixed whitespace-nowrap text-sm">
                  <colgroup>
                    <col style={{ width: "7%" }} />
                    <col style={{ width: "31%" }} />
                    <col style={{ width: "31%" }} />
                    <col style={{ width: "31%" }} />
                  </colgroup>
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="sticky top-0 z-10 bg-card px-3 py-1 text-[15px] font-bold">名次</th>
                      {/* 表头与"机构名→条形"缝隙对齐: 缩进 = 12(px-3) + 名称7em(≈105) + 6(gap) */}
                      <th className="sticky top-0 z-10 bg-card py-1 text-[15px] font-medium" style={{ paddingLeft: 123 }}>成交量</th>
                      <th className="sticky top-0 z-10 bg-card py-1 text-[15px] font-medium" style={{ paddingLeft: 123 }}>多头持仓</th>
                      <th className="sticky top-0 z-10 bg-card py-1 text-[15px] font-medium" style={{ paddingLeft: 123 }}>空头持仓</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.rank} className="border-b border-border/60 hover:bg-muted/40">
                        <td className="px-3 py-1 text-center text-[15px] font-semibold tabular-nums text-foreground">
                          {r.rank}
                        </td>
                        <td className="px-3 py-1">
                          <InstCell max={volMax} member={r.vol_member} value={r.vol} delta={r.vol_chg} barColor="bg-slate-400/80" />
                        </td>
                        <td className="px-3 py-1">
                          <InstCell max={longMax} member={r.long_member} value={r.long_oi} delta={r.long_chg} barColor="bg-red-400/70" />
                        </td>
                        <td className="px-3 py-1">
                          <InstCell max={shortMax} member={r.short_member} value={r.short_oi} delta={r.short_chg} barColor="bg-green-500/70" />
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
    </div>
  );
}
