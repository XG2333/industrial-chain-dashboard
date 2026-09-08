import { Coins, Landmark, Package, Scale, TrendingUp, type LucideIcon } from "lucide-react";

// 评分维度面板（板块简评的 5 维评分）：
// 1. 综合强度分（5 维平均）  4. 1-10 刻度条 + 当前分圆点 + 大号得分 + hover reason
// 5. 两列布局（2+2+1）缩短高度  6. 颜色图例  7. 维度图标
// 颜色档位与页面直觉一致：红=偏强(≥7) 黄=中性(4-6) 绿=偏弱(<4)

interface ScoreItem {
  dimension: string;
  score: number;
  reason: string;
}

const SCORE_LABELS: Record<string, string> = {
  "供需格局": "供过于求 → 供不应求",
  "价格趋势": "价格下行 → 上行",
  "库存周期": "累库 → 去库",
  "资金关注": "资金流出 → 流入",
  "政策催化": "利空 → 利好",
};

const DIM_ICONS: Record<string, LucideIcon> = {
  "供需格局": Scale,
  "价格趋势": TrendingUp,
  "库存周期": Package,
  "资金关注": Coins,
  "政策催化": Landmark,
};

const FALLBACK_ICON: LucideIcon = TrendingUp;

const barColor = (score: number) =>
  score >= 7 ? "#ef4444" : score >= 4 ? "#f59e0b" : "#22c55e";
const textColor = (score: number) =>
  score >= 7 ? "text-red-500" : score >= 4 ? "text-amber-500" : "text-green-600";

export function ScorePanel({ scores }: { scores: ScoreItem[] }) {
  if (scores.length === 0) {
    return (
      <div className="rounded-xl border bg-card">
        <div className="border-b px-5 py-3">
          <h3 className="text-lg font-semibold text-foreground">评分维度</h3>
        </div>
        <p className="px-5 py-8 text-center text-xs text-muted-foreground">
          点击「AI 分析」自动生成
        </p>
      </div>
    );
  }

  const avg = scores.reduce((a, s) => a + s.score, 0) / scores.length;

  return (
    <div className="rounded-xl border bg-card">
      <div className="border-b px-5 py-3">
        <h3 className="text-lg font-semibold text-foreground">评分维度</h3>
      </div>
      <div className="p-4">
        {/* 1. 综合强度分 */}
        <div className="mb-3 flex items-center justify-between rounded-md bg-muted/30 px-3 py-2">
          <span className="text-sm font-semibold text-foreground">综合强度</span>
          <span className={`text-lg font-bold tabular-nums ${textColor(avg)}`}>
            {avg.toFixed(1)}
            <span className="text-xs font-medium text-muted-foreground"> / 10</span>
          </span>
        </div>
        {/* 5. 两列布局（最后一项跨列） */}
        <div className="grid grid-cols-1 gap-x-5 gap-y-3 md:grid-cols-2">
          {scores.map((s, i) => {
            const Icon = DIM_ICONS[s.dimension] ?? FALLBACK_ICON;
            const color = barColor(s.score);
            const isWide = scores.length % 2 === 1 && i === scores.length - 1;
            return (
              <div key={s.dimension} className={isWide ? "md:col-span-2" : ""}>
                <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                  <span className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
                    <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{s.dimension}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground" title={s.dimension}>
                    {SCORE_LABELS[s.dimension] || ""}
                  </span>
                </div>
                {/* 4. 刻度条 + 圆点；右侧大号得分 */}
                <div className="flex items-center gap-2">
                  <div className="relative h-2 flex-1 rounded-full bg-muted">
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((t) => (
                      <span
                        key={t}
                        className="absolute top-0 h-full w-px bg-black/15"
                        style={{ left: `${t * 10}%` }}
                      />
                    ))}
                    <div
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{ width: `${s.score * 10}%`, backgroundColor: color }}
                    />
                    <span
                      className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background shadow-sm"
                      style={{ left: `${s.score * 10}%`, backgroundColor: color }}
                    />
                  </div>
                  <span className={`w-7 shrink-0 text-right text-base font-bold tabular-nums ${textColor(s.score)}`}>
                    {s.score}
                  </span>
                </div>
                {/* 理由完整换行显示（不截断） */}
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{s.reason}</p>
              </div>
            );
          })}
        </div>
        {/* 6. 颜色图例 */}
        <p className="mt-3 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
          <span className="font-semibold text-red-500">●</span> 偏强（≥7）
          <span className="ml-2 font-semibold text-amber-500">●</span> 中性（4-6）
          <span className="ml-2 font-semibold text-green-600">●</span> 偏弱（&lt;4）
        </p>
      </div>
    </div>
  );
}
