import { Fragment, useState } from "react";
import type { IndustryChart, IndustryGroup } from "@/lib/industryGroups";

const COLUMNS = 3;
const DEFAULT_ROWS = 4;
const EXPAND_STEP = 4;
const FREQ_ORDER = [
  { value: "daily", label: "日度数据" },
  { value: "weekly", label: "周度数据" },
  { value: "monthly", label: "月度数据" },
  { value: "quarterly", label: "季度数据" },
  { value: "yearly", label: "年度数据" },
];
const FREQ_LADDER = ["daily", "weekly", "monthly", "yearly"];
const FREQ_LABELS: Record<string, string> = {
  daily: "日度",
  weekly: "周度",
  monthly: "月度",
  yearly: "年度",
};

type ChartRow = IndustryChart & { sub: string };

interface GridCell {
  type: "header" | "chart" | "subHeader";
  key: string;
  label?: string;
  chart?: ChartRow;
}

interface GridRow {
  cells: GridCell[];
}

function scrollToChart(id: string) {
  const el = document.getElementById(id);
  if (!el) return;

  el.scrollIntoView({ behavior: "smooth", block: "start" });

  const previousTimer = Number(el.dataset.flashTimer || 0);
  if (previousTimer) window.clearTimeout(previousTimer);

  el.classList.remove("chart-flash");
  void el.offsetWidth;
  el.classList.add("chart-flash");

  const timer = window.setTimeout(() => {
    el.classList.remove("chart-flash");
    delete el.dataset.flashTimer;
  }, 2000);
  el.dataset.flashTimer = String(timer);
}

export function IndustryChartTable({ group }: { group: IndustryGroup }) {
  const [expandedRows, setExpandedRows] = useState(DEFAULT_ROWS);
  const [startRow, setStartRow] = useState(0);

  const gridRows: GridRow[] = [];
  const freqRowRanges: Record<string, { start: number; end: number }> = {};
  const subRowRanges: Record<string, { start: number; end: number }> = {};
  const subFreqRowRanges: Record<string, Record<string, { start: number; end: number }>> = {};
  let currentCells: GridCell[] = [];

  const flush = () => {
    if (currentCells.length) {
      gridRows.push({ cells: currentCells });
      currentCells = [];
    }
  };

  for (const sub of group.subs) {
    const subStartRow = gridRows.length;
    gridRows.push({
      cells: [{ type: "subHeader", key: `sub-${sub.sub}`, label: sub.sub }],
    });

    for (const freq of FREQ_ORDER) {
      const freqCharts: ChartRow[] = sub.charts.map((chart) => ({
        ...chart,
        sub: sub.sub,
      }));
      const filtered = freqCharts.filter((chart) => chart.freq === freq.value);
      if (!filtered.length) continue;

      flush();
      const freqStartRow = gridRows.length;
      gridRows.push({
        cells: [{ type: "header", key: `header-${sub.sub}-${freq.value}`, label: freq.label }],
      });

      for (const chart of filtered) {
        currentCells.push({ type: "chart", key: chart.id, chart });
        if (currentCells.length === COLUMNS) flush();
      }
      flush();
      const freqEndRow = gridRows.length - 1;
      freqRowRanges[freq.value] = { start: freqStartRow, end: freqEndRow };
      if (!subFreqRowRanges[sub.sub]) subFreqRowRanges[sub.sub] = {};
      subFreqRowRanges[sub.sub][freq.value] = { start: freqStartRow, end: freqEndRow };
    }
    subRowRanges[sub.sub] = { start: subStartRow, end: gridRows.length - 1 };
  }
  flush();

  const maxRows = gridRows.length;
  const endRow = startRow + expandedRows - 1;
  const visibleGridRows = gridRows.slice(startRow, startRow + expandedRows);
  const subNames = group.subs.map((sub) => sub.sub).filter((name) => subRowRanges[name]);
  let currentSubIndex = subNames.findIndex(
    (name) => startRow <= subRowRanges[name].end && endRow >= subRowRanges[name].start,
  );
  if (currentSubIndex < 0) currentSubIndex = Math.max(0, subNames.length - 1);
  const currentSubName = subNames[currentSubIndex];
  const subFreqRanges = subFreqRowRanges[currentSubName] || {};
  const ladderRanges = FREQ_LADDER.filter((value) => subFreqRanges[value]);
  let currentFreqIndex = ladderRanges.findIndex(
    (value) => startRow <= subFreqRanges[value].end && endRow >= subFreqRanges[value].start,
  );
  if (currentFreqIndex < 0) currentFreqIndex = Math.max(0, ladderRanges.length - 1);
  const nextFreq = ladderRanges[currentFreqIndex + 1];
  const prevFreq = ladderRanges[Math.max(0, currentFreqIndex - 1)];

  const expand = () => {
    setExpandedRows((prev) => Math.min(maxRows - startRow, prev + EXPAND_STEP));
  };

  const collapseStep = () => {
    setExpandedRows((prev) => Math.max(DEFAULT_ROWS, prev - EXPAND_STEP));
  };

  const collapseAll = () => {
    setStartRow(0);
    setExpandedRows(DEFAULT_ROWS);
  };

  const expandToNextFrequency = () => {
    if (!nextFreq) return;
    const target = subFreqRanges[nextFreq].end;
    setExpandedRows((prev) => Math.max(prev, target - startRow + 1));
  };

  const collapseToPreviousFrequency = () => {
    if (!prevFreq || currentFreqIndex <= 0) return;
    const target = subFreqRanges[prevFreq].end;
    setExpandedRows((prev) =>
      Math.max(DEFAULT_ROWS, Math.min(prev, target - startRow + 1)),
    );
  };

  const expandToNextSub = () => {
    if (currentSubIndex >= subNames.length - 1) return;
    const currentStart = subRowRanges[subNames[currentSubIndex]].start;
    const nextEnd = subRowRanges[subNames[currentSubIndex + 1]].end;
    setStartRow(currentStart);
    setExpandedRows(nextEnd - currentStart + 1);
  };

  const collapseToNextSub = () => {
    if (currentSubIndex >= subNames.length - 1) return;
    const nextStart = subRowRanges[subNames[currentSubIndex + 1]].start;
    const nextEnd = subRowRanges[subNames[currentSubIndex + 1]].end;
    setStartRow(nextStart);
    setExpandedRows(nextEnd - nextStart + 1);
  };

  return (
    <>
      <div className="mt-4 grid grid-cols-3 gap-1.5">
        {visibleGridRows.map((row, rowIndex) => (
          <Fragment key={rowIndex}>
            {row.cells.map((cell) =>
              cell.type === "subHeader" ? (
                <div
                  key={cell.key}
                  className="col-span-full rounded-md border border-[#002FA7]/20 bg-[#002FA7]/10 px-2 py-1.5 text-left text-sm font-bold text-[#002FA7]"
                >
                  {cell.label}
                </div>
              ) : cell.type === "header" ? (
                <div
                  key={cell.key}
                  className="col-span-full rounded-md bg-slate-100 px-2 py-1.5 text-center text-sm font-bold text-slate-600"
                >
                  {cell.label}
                </div>
              ) : (
                <button
                  key={cell.key}
                  onClick={() => scrollToChart(cell.chart!.id)}
                  title={cell.chart!.title}
                  className="min-h-0 rounded-md border bg-slate-50 px-2 py-1.5 text-left transition hover:border-[#002FA7] hover:bg-[#eef4ff]"
                >
                  <span className="line-clamp-2 block text-[11px] font-medium leading-tight text-slate-700">
                    {cell.chart!.title}
                  </span>
                  <span className="mt-1 block truncate text-[9px] text-slate-400">
                    {cell.chart!.unit}
                  </span>
                </button>
              ),
            )}
          </Fragment>
        ))}
      </div>
      <div className="mt-2 flex items-start justify-between gap-3">
        <button
          onClick={expandToNextSub}
          disabled={currentSubIndex >= subNames.length - 1}
          className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          展开到下一子类
        </button>
        <button
          onClick={collapseToNextSub}
          disabled={currentSubIndex >= subNames.length - 1}
          className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          收起到下一子类
        </button>
      </div>
      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={expand}
            disabled={startRow + expandedRows >= maxRows}
            className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            展开下部分
          </button>
          <button
            onClick={expandToNextFrequency}
            disabled={!nextFreq}
            className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {nextFreq ? `展开到${FREQ_LABELS[nextFreq]}` : "展开到年度"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={collapseStep}
            disabled={expandedRows <= DEFAULT_ROWS}
            className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            收起上部分
          </button>
          <button
            onClick={collapseToPreviousFrequency}
            disabled={currentFreqIndex <= 0}
            className="rounded-md border bg-white px-3.5 py-1.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {prevFreq ? `收起到${FREQ_LABELS[prevFreq]}` : "收起到日度"}
          </button>
          <button
            onClick={collapseAll}
            disabled={expandedRows <= DEFAULT_ROWS}
            className="rounded-md border bg-white px-4 py-2 text-base font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            收起全部
          </button>
        </div>
      </div>
    </>
  );
}
