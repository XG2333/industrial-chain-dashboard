import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { IndustryGroup } from "@/lib/industryGroups";
import { subDisplayName } from "@/lib/industryGroups";
import { useVerticalDrag } from "@/hooks/useVerticalDrag";

// 悬浮板块导航（索引栏）：右侧圆点按钮 → 展开分组树，点击板块/子类平滑定位。
// 子项按钮直接映射 group.subs 全序（含成交持仓复合组），与 IndustryDataScheme1
// 渲染的 industry-{groupIdx}-{subIdx} id 严格对齐，保证点击跳转准确。

interface FloatingTargetNavProps {
  items: string[];
  onSelect: (tab: string) => void;
  groups?: IndustryGroup[];
  // 总览 tab 显示 产业资讯/自选股票/行情数据 跳转（板块 Tab 无这些区块）
  overviewLinks?: boolean;
  // 总览 tab 显示 仓单日报/各合约成交持仓 跳转（两区块只在总览 tab 渲染）
  receiptLinks?: boolean;
}

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function FloatingTargetNav({
  items,
  onSelect,
  groups = [],
  overviewLinks = false,
  receiptLinks = false,
}: FloatingTargetNavProps) {
  const { top, onMouseDown, onClickCapture } = useVerticalDrag(16, 300);
  const [openMajor, setOpenMajor] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  if (!items.length) return null;

  if (!panelOpen) {
    return (
      <button
        className="fixed right-0 top-16 z-50 flex h-20 w-10 flex-col items-center justify-center gap-0.5 rounded-l-xl bg-primary text-sm font-semibold text-primary-foreground shadow-lg hover:bg-primary/90"
        onClick={() => setPanelOpen(true)}
        title="索引栏"
      >
        <span>索引</span>
        <span>栏</span>
      </button>
    );
  }

  return (
    <div
      className="fixed right-4 z-40 w-64 cursor-grab select-none touch-none rounded-xl border bg-white/95 px-2 py-2 text-slate-700 shadow-lg backdrop-blur max-h-[calc(100vh-24px)] overflow-y-auto"
      style={{ top }}
      onMouseDown={onMouseDown}
      onClickCapture={onClickCapture}
    >
      <div className="mb-1 flex items-center justify-between">
        <p className="text-center text-sm font-semibold text-slate-500">索引栏</p>
        <button
          onClick={() => setPanelOpen(false)}
          className="rounded border bg-white px-1.5 py-0.5 text-sm text-slate-500 hover:bg-slate-50"
        >
          收起
        </button>
      </div>
      {overviewLinks && (
        <div className="mb-2 space-y-1">
          <p className="text-center text-[10px] font-semibold text-slate-400">基本面分析</p>
          <button
            onClick={() => scrollToId("overview-news")}
            className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            产业资讯
          </button>
          <button
            onClick={() => scrollToId("overview-watchlist")}
            className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            自选股票
          </button>
          {receiptLinks && (
            <>
              <button
                onClick={() => scrollToId("warehouse-receipts")}
                className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                仓单日报
              </button>
              <button
                onClick={() => scrollToId("contract-positions")}
                className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                各合约成交持仓
              </button>
            </>
          )}
        </div>
      )}
      {!overviewLinks && receiptLinks && (
        <div className="mb-2 space-y-1">
          <button
            onClick={() => scrollToId("warehouse-receipts")}
            className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            仓单日报
          </button>
          <button
            onClick={() => scrollToId("contract-positions")}
            className="w-full rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            各合约成交持仓
          </button>
        </div>
      )}
      {groups.length > 0 && (
        <div className="space-y-1">
          <p className="text-center text-[10px] font-semibold text-slate-400">板块行业数据</p>
          {groups.map((group) => {
            const groupIdx = items.indexOf(group.major);
            if (groupIdx < 0) return null;
            const expanded = openMajor === group.major;
            return (
              <div key={group.major} className="space-y-1">
                <button
                  onClick={() => {
                    setOpenMajor(expanded ? null : group.major);
                    onSelect(group.major);
                  }}
                  className="flex w-full items-center justify-between rounded-md border bg-white px-2 py-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <span className="truncate">{group.major}</span>
                  {expanded ? (
                    <ChevronUp className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  )}
                </button>
                {expanded && (
                  <div className="space-y-1 pl-2">
                    {/* 进出口：子类标题带"中国海关"等前缀信息量低，整组只显示一个
                        "进出口"按钮，点击定位到该组首块（与 IndustryDataScheme1 一致） */}
                    {group.major === "进出口" ? (
                      <button
                        onClick={() => scrollToId(`industry-${groupIdx}`)}
                        className="w-full rounded border bg-white px-2 py-1 text-left text-sm text-slate-600 hover:bg-slate-50"
                      >
                        {group.major}
                      </button>
                    ) : (
                      /* 其余：子项 = group.subs 全序（与 Scheme 的
                          industry-{groupIdx}-{subIdx} 一一对应）。
                          成交持仓复合组（碳酸锂: 主力合约/01/05/09 等合约行）
                          在导航中合并为单个"成交持仓"入口，指向该组首个复合块 */
                      group.subs.map((sub, subIdx) => {
                        if (sub.composite) {
                          const isFirstComposite =
                            group.subs.findIndex((s) => s.composite) === subIdx;
                          return isFirstComposite ? (
                            <button
                              key={sub.sub}
                              onClick={() => scrollToId(`industry-${groupIdx}-${subIdx}`)}
                              title={sub.title ?? sub.sub}
                              className="w-full truncate rounded border bg-white px-2 py-1 text-left text-sm text-slate-600 hover:bg-slate-50"
                            >
                              成交持仓
                            </button>
                          ) : null;
                        }
                        return (
                          <button
                            key={sub.sub}
                            onClick={() => scrollToId(`industry-${groupIdx}-${subIdx}`)}
                            title={sub.title ?? sub.sub}
                            className="w-full truncate rounded border bg-white px-2 py-1 text-left text-sm text-slate-600 hover:bg-slate-50"
                          >
                            {subDisplayName(sub.sub)}
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
