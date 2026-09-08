import { useMemo, useState } from "react";
import type { IndustryGroup } from "@/lib/industryGroups";
import { quickAnalysisBus } from "@/lib/quickAnalysisBus";
import { Button } from "@/components/ui/Button";
import { Sparkles } from "lucide-react";

// 一键速评工具栏：显示在行业数据板块列表上方（总览），
// 按页面顺序逐个触发：仓单速评 → 各板块速评（通过 quickAnalysisBus 通信），
// 避免每个卡片手动点击；进度与当前项实时显示。

const SECTOR_KEY_PREFIX = "sector_analysis_v3"; // 与 SectorQuickAnalysis 缓存 key 前缀一致
const WAREHOUSE_KEY_PREFIX = "warehouse_analysis_v2"; // 与 WarehouseQuickAnalysis 缓存 key 前缀一致
const POSITIONS_KEY_PREFIX = "positions_analysis_v2"; // 与 PositionQuickAnalysis 缓存 key 前缀一致
const FUTURE_KEY_PREFIX = "future_analysis_v2"; // 与 KpiFutureAnalysis 缓存 key 前缀一致

const sectorCacheKeyOf = (dataset: string, sector: string) => `${SECTOR_KEY_PREFIX}_${dataset}_${sector}`;

function datasetOf(groups: IndustryGroup[]): string {
  const id = groups[0]?.subs?.[0]?.charts?.[0]?.id || "";
  return id.startsWith("tin_") ? "tin" : id.startsWith("silicon_") ? "silicon" : "lithium";
}

// 触发某项并等待其完成（60s 超时防卡死）
function waitDone(key: string): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        quickAnalysisBus.offDone(h);
        resolve();
      }
    }, 60000);
    const h = (k: string) => {
      if (k === key && !settled) {
        settled = true;
        window.clearTimeout(timer);
        quickAnalysisBus.offDone(h);
        resolve();
      }
    };
    quickAnalysisBus.onDone(h);
    quickAnalysisBus.run(key);
  });
}

export function SectorAnalysisAllToolbar({ groups }: { groups: IndustryGroup[] }) {
  const [idx, setIdx] = useState<number | null>(null);
  const running = idx != null;
  const dataset = datasetOf(groups);

  // 按页面顺序：主力期货 → 仓单日报 → 各合约成交持仓 → 各板块
  const items = useMemo(
    () => [
      { key: `${FUTURE_KEY_PREFIX}_${dataset}`, label: "主力期货" },
      { key: `${WAREHOUSE_KEY_PREFIX}_${dataset}`, label: "仓单日报" },
      { key: `${POSITIONS_KEY_PREFIX}_${dataset}`, label: "成交持仓" },
      ...groups.map((g) => ({ key: sectorCacheKeyOf(dataset, g.major), label: g.major })),
    ],
    [groups, dataset],
  );

  const runAll = async () => {
    if (running || items.length === 0) return;
    // 逐项串行（避免并发打爆 DeepSeek 接口）
    for (let i = 0; i < items.length; i++) {
      setIdx(i);
      await waitDone(items[i].key);
    }
    setIdx(null);
  };

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-2.5">
      <p className="text-xs text-muted-foreground">
        一键生成仓单日报、成交持仓与全部板块速评；已生成过的可一键全部刷新
      </p>
      <Button
        variant="outline"
        size="sm"
        onClick={runAll}
        disabled={running || items.length === 0}
        className="shrink-0"
      >
        <Sparkles className={`h-3.5 w-3.5 ${running ? "animate-pulse" : ""}`} />
        {running
          ? `正在速评 ${idx! + 1}/${items.length} · ${items[idx!].label}…`
          : "一键速评全部（含仓单成交持仓）"}
      </Button>
    </div>
  );
}
