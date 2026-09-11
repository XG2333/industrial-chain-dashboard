import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { getYearColor } from "@/lib/chartColors";
import { axisScaleFor, cleanAxisValues, formatAxisValue } from "@/lib/chartFormat";
import type { ChartVisualTheme } from "@/theme/chartTheme";
import { CHART_FONTS, useChartTheme } from "@/theme/chartTheme";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

interface DataPoint { date: string; value: number; yoy?: number | null; cum_yoy?: number | null; }

const MONTHS = ["1","2","3","4","5","6","7","8","9","10","11","12"];
const MONTH_START_DAY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const MONTH_LABEL_DAY = [16, 45, 75, 106, 136, 167, 197, 228, 259, 289, 320, 350];
const DAILY_CATEGORY_DATA = Array.from({ length: 366 }, (_, index) => String(index + 1));
// 周度：年内连续周序号（周一为一周开始，跨月续排），共 53 格（含闰年 53 周）。
// 月份标签按真实月首所在周序号定位（4 周/月会错位：12 月 1 日已是第 48 周，
// 若标签铺在 0,4,…,44 会让 12 月数据点落在"12 月"标签之后）；
// 同周多点合并为该周最后一条（如周四+周五 → 周五）。
const WEEKLY_CATEGORY_DATA = Array.from({ length: 53 }, (_, index) => String(index + 1));
// 各月首近似周序号（doy≈1,32,60,91,121,152,182,213,244,274,305,335 → /7 取整，
// 与 1 月 1 日星期几 ±1 格）：用于 x 轴月份标签与 tooltip 月份换算
const WEEKLY_MONTH_LABELS = [0, 4, 8, 13, 17, 22, 26, 30, 35, 39, 43, 48];
function weeklyMonthOf(weekIndex: number): number {
  let month = 1;
  for (let i = 0; i < WEEKLY_MONTH_LABELS.length; i++) {
    if (weekIndex >= WEEKLY_MONTH_LABELS[i]) month = i + 1;
  }
  return month;
}

// 年内连续周序号（周一为一周开始，跨月续排；跨年周归入 0-52）
function weekIndex(y: number, m: number, d: number): number {
  const dow = new Date(y, m - 1, d).getDay(); // 0=周日
  const mondayDoy = dayOfYear(m, d) - ((dow + 6) % 7);
  return Math.max(0, Math.min(52, Math.floor((mondayDoy - 1) / 7)));
}

function monthForDayOfYear(day: number): string {
  const clamped = Math.max(1, Math.min(366, Math.round(day)));
  let month = 12;
  for (let index = MONTH_START_DAY.length - 1; index >= 0; index--) {
    if (clamped >= MONTH_START_DAY[index]) {
      month = index + 1;
      break;
    }
  }
  return MONTHS[month - 1] || "";
}

const DAY_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
function dayOfYear(m: number, d: number): number {
  return DAY_BEFORE_MONTH[m - 1] + d;
}
function daysInMonth(y: number, m: number) {
  return new Date(y, m, 0).getDate();
}

export function SeasonalChart({
  title,
  data,
  unit,
  freq,
  keepExtremes = false,
}: {
  title: string;
  unit: string;
  data: DataPoint[];
  freq?: string;
  keepExtremes?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();
  // 频率判断（含兜底）：目录 freq 标记可能与实际数据不符（如标 daily 但数据为月度、
  // 标 monthly 但数据实为周度），统一按相邻日期平均间隔判定——
  // 短历史周度数据（如氢氧化锂样本库存仅 13 点/3 个月）按"年化点数"口径 ≤13 会被
  // 误判为月度，平均间隔是数据自身属性，与历史长度无关。
  const avgGapDays = (() => {
    if (data.length < 2) return Infinity; // 单点无间隔信息，按月度格展示
    const sorted = [...data].map((d) => Date.parse(d.date)).sort((a, b) => a - b);
    let total = 0;
    for (let i = 1; i < sorted.length; i++) total += (sorted[i] - sorted[i - 1]) / 86400000;
    return total / (sorted.length - 1);
  })();
  // daily：366 日序轴；weekly：53 格连续周序号轴；其余（间隔 >14 天或单点）按月度渲染
  const isDaily = avgGapDays <= 3;
  const isWeekly = avgGapDays > 3 && avgGapDays <= 14;
  // 真年度判定：freq 标记 + 数据间隔佐证（≥300 天或点数 ≤2），
  // 防止错标 yearly 的月度/日度数据误入年份柱状渲染
  const isYearly = freq === "yearly" && (data.length <= 2 || avgGapDays >= 300);
  const keepAxisExtremes =
    keepExtremes ||
    title.includes("期现价差") ||
    title.includes("基差") ||
    title.includes("月差") ||
    title.includes("价差");
  // 年份集合（HTML 年份标签行使用）
  const legendYears = useMemo(() => {
    const set = new Set<string>();
    for (const d of data) set.add(d.date.slice(0, 4));
    return [...set].sort();
  }, [data]);
  // ── 年份标签通用规则：HTML 自定义行 + CSS scale 缩放，保证所有年份完全显示在同一行 ──
  // 先按自然宽度渲染，超宽时用 transform: scale 等比压缩，物理上不可能换行。
  const yearRowRef = useRef<HTMLDivElement>(null);
  const [yearScale, setYearScale] = useState(1);
  useEffect(() => {
    const computeScale = () => {
      const node = yearRowRef.current;
      if (!node || legendYears.length === 0) return;
      const available = node.parentElement?.clientWidth ?? node.scrollWidth;
      const natural = node.scrollWidth;
      setYearScale(natural > available ? Math.max(available / natural, 0.3) : 1);
    };
    computeScale();
    window.addEventListener("resize", computeScale);
    return () => window.removeEventListener("resize", computeScale);
  }, [legendYears, data]);

  if (isYearly) {
    const sorted = [...data].filter((d) => d.value != null).sort((a, b) => a.date.localeCompare(b.date));
    const years = sorted.map((d) => d.date.slice(0, 4));
    const values = sorted.map((d) => d.value);
    return (
      <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 140, backgroundColor: theme.background }}>
        <YearlyBar innerRef={ref} years={years} values={values} unit={unit} theme={theme} />
      </div>
    );
  }

  useEffect(() => {
    if (!ref.current || data.length === 0) return;

    // ── Unified: value x-axis 1-12, daily=smooth+nodots, monthly=dots ──
    // 周度数据源部分指标每周两个日期（如周四+周五各一条），按周序号映射会落在同一格，
    // 因此先按 (年, 周序号) 合并为该周最后一条（数据降序，首个即该周最新），
    // 保证每周一格一点，消除同格双值重叠。
    const weeklyMerged = isWeekly
      ? (() => {
          const seen = new Map<string, DataPoint>();
          for (const pt of data) {
            const k = pt.date.slice(0, 4) + "|" + weekIndex(
              parseInt(pt.date.slice(0, 4), 10),
              parseInt(pt.date.slice(5, 7), 10),
              parseInt(pt.date.slice(8, 10), 10),
            );
            if (!seen.has(k)) seen.set(k, pt);
          }
          return [...seen.values()];
        })()
      : data;
    const byYear: Record<string, [number, number][]> = {};
    const lookup: Record<string, DataPoint> = {};
    for (const pt of weeklyMerged) {
      const y = pt.date.slice(0, 4);
      const m = parseInt(pt.date.slice(5, 7), 10);
      const d = parseInt(pt.date.slice(8, 10), 10);
      const x = isDaily
        ? dayOfYear(m, d) - 1
        : isWeekly
          ? weekIndex(parseInt(y, 10), m, d)
          : m - 1;
      if (!byYear[y]) byYear[y] = [];
      byYear[y].push([x, pt.value]);
      if (!isDaily) lookup[y + "-" + String(m).padStart(2, "0")] = pt;
    }
    const yearKeys = Object.keys(byYear).sort();
    if (yearKeys.length === 0) return;
    const latestYear = yearKeys[yearKeys.length - 1];
    const rawValues: number[] = [];
    for (const pts of Object.values(byYear)) pts.forEach(([x, v]) => { if (v != null) rawValues.push(v); });
    const cleanVals = cleanAxisValues(rawValues, keepAxisExtremes);
    const hasData = cleanVals.length > 0;
    const yMin = Math.min(...cleanVals);
    const yMax = Math.max(...cleanVals);
    const yPad = hasData ? Math.max((yMax - yMin) * 0.05, Math.abs(yMax) * 0.005, 0.05) : 0.05;
    const axisMin = yMin >= 0 ? Math.max(0, yMin - yPad) : yMin - yPad;
    const axisMax = yMax <= 0 ? Math.min(0, yMax + yPad) : yMax + yPad;

    echarts.dispose(ref.current);
    const chart = echarts.init(ref.current);
    chart.setOption({ backgroundColor: theme.background,
      tooltip: {
        trigger: "axis", backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { seriesName: string; data: [number, number] }[]) => {
          const parts = ps.filter(p => p.data[1] != null).map(p => {
            const color = getYearColor(p.seriesName);
            const monthNumber = isWeekly ? weeklyMonthOf(Math.floor(p.data[0])) : Math.round(p.data[0]) + 1;
            const key = p.seriesName + "-" + String(monthNumber).padStart(2, "0");
            const pt = lookup[key];
            let line = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + color + ';margin-right:6px"></span>' + p.seriesName + '  <b>' + (p.data[1]?.toFixed(2) || "0") + '</b> ' + unit;
            if (pt?.yoy != null) {
              const cls = pt.yoy >= 0 ? "color:#e57373" : "color:#66bb6a";
              line += '  <span style="font-size:10px;' + cls + '">同比 ' + (pt.yoy >= 0 ? "+" : "") + pt.yoy.toFixed(1) + '%</span>';
            }
            if (pt?.cum_yoy != null) {
              const cls = pt.cum_yoy >= 0 ? "color:#e57373" : "color:#66bb6a";
              line += '  <span style="font-size:10px;' + cls + '">累计 ' + (pt.cum_yoy >= 0 ? "+" : "") + pt.cum_yoy.toFixed(1) + '%</span>';
            }
            return line;
          });
          return parts.join("<br/>");
        },
      },
      legend: { show: false },
      grid: { left: 0, right: 6, top: 26, bottom: 12, containLabel: true },
      xAxis: isDaily
        ? { type: "category", data: DAILY_CATEGORY_DATA, axisLine: { lineStyle: { color: theme.axisLine } }, axisTick: { show: false }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, hideOverlap: false, interval: (index: number) => MONTH_LABEL_DAY.includes(index + 1), formatter: (_value: string, index: number) => monthForDayOfYear(index + 1) }, splitLine: { show: false } }
        : isWeekly
          ? { type: "category", data: WEEKLY_CATEGORY_DATA, axisLine: { lineStyle: { color: theme.axisLine } }, axisTick: { show: false }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, hideOverlap: false, interval: (index: number) => WEEKLY_MONTH_LABELS.includes(index), formatter: (_value: string, index: number) => String(WEEKLY_MONTH_LABELS.indexOf(index) + 1) }, splitLine: { show: false } }
          : { type: "category", data: MONTHS, axisLine: { lineStyle: { color: theme.axisLine } }, axisTick: { show: false }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, hideOverlap: false, interval: 0 }, splitLine: { show: false } },
      yAxis: { type: "value", min: hasData ? axisMin : undefined, max: hasData ? axisMax : undefined, splitNumber: 5, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: theme.splitLine } }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => formatAxisValue(v) } },
      series: yearKeys.map((y, yi) => {
        const isLatest = y === latestYear;
        const smooth = isDaily || isWeekly;
        return { name: y, type: "line", data: byYear[y], smooth, symbol: smooth ? "none" : "circle", symbolSize: smooth ? 0 : (isLatest ? 5 : 3), lineStyle: { width: isLatest ? 3 : 1.6, color: getYearColor(y, yi) }, itemStyle: { color: getYearColor(y, yi) }, emphasis: { focus: "series" } };
      }),
    }, {notMerge: true});

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [data, unit, isDaily, theme]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 140, backgroundColor: theme.background }}>
      <div ref={ref} style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: theme.background }} />
      {/* 年份标签通用规则：所有年份完全显示在同一行（超宽时 CSS scale 等比压缩） */}
      {legendYears.length > 0 && (
        <div style={{ position: "absolute", top: 2, left: 4, right: 8, height: 20, overflow: "hidden", zIndex: 5, pointerEvents: "none" }}>
          <div
            ref={yearRowRef}
            style={{
              display: "flex", alignItems: "center", gap: 12, whiteSpace: "nowrap",
              width: "max-content", transform: `scale(${yearScale})`, transformOrigin: "left center",
            }}
          >
            {legendYears.map((year) => (
              <span key={year} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: CHART_FONTS.legend, color: theme.legendText, whiteSpace: "nowrap" }}>
                <span style={{ display: "inline-block", width: 12, height: 8, borderRadius: 1, background: getYearColor(year) }} />
                {year}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function YearlyBar({ innerRef, years, values, unit, theme }: { innerRef: { current: HTMLDivElement | null }; years: string[]; values: number[]; unit: string; theme: ChartVisualTheme }) {
  useEffect(() => {
    if (!innerRef.current || years.length === 0) return;
    echarts.dispose(innerRef.current);
    const cleanVals = cleanAxisValues(values);
    const yMin = Math.min(...cleanVals);
    const yMax = Math.max(...cleanVals);
    const yPad = Math.max((yMax - yMin) * 0.05, Math.abs(yMax) * 0.005, 0.05);
    const axisMin = yMin >= 0 ? Math.max(0, yMin - yPad) : yMin - yPad;
    const axisMax = yMax <= 0 ? Math.min(0, yMax + yPad) : yMax + yPad;
    void axisMin;
    void axisMax;
    const chart = echarts.init(innerRef.current);
    chart.setOption({ backgroundColor: theme.background,
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { name: string; data: number }[]) => {
          const p = ps[0]; if (p.data == null) return "";
          return (p.name || "") + "<br/><b>" + (p.data?.toFixed(2) || "0") + "</b> " + unit;
        },
      },
      grid: { left: 0, right: 6, top: 6, bottom: 16, containLabel: true },
      xAxis: {
        type: "category", data: years,
        axisLine: { lineStyle: { color: theme.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          fontSize: CHART_FONTS.axis,
          color: theme.secondaryText,
          // 年份过多时抽稀到 ≤10 个标签，避免拥挤重叠；45° 旋转只在 20+ 年时启用
          rotate: years.length > 20 ? 45 : 0,
          interval: (index: number) => index % Math.max(1, Math.ceil(years.length / 10)) === 0,
        },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: theme.splitLine } },
        splitNumber: 5,
        axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => formatAxisValue(v) },
      },
      series: [{
        type: "bar", data: years.map((year, index) => ({ value: values[index], itemStyle: { color: getYearColor(year, index), borderRadius: [3, 3, 0, 0] } })),
        // barWidth 交给 echarts 按带宽自适应（多年份时固定宽度会溢出/挤压）
      }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [years, values, unit, innerRef, theme]);
  return <div ref={innerRef} style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: theme.background }} />;
}
