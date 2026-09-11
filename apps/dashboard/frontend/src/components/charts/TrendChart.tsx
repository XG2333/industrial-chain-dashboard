import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { cleanAxisValues, formatAxisValue } from "@/lib/chartFormat";
import { CHART_FONTS, useChartTheme } from "@/theme/chartTheme";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface DataPoint { date: string; value: number; }

export function TrendChart({
  data,
  title,
  unit,
  trendUp,
  showYearLabel = false,
}: {
  data: DataPoint[];
  title: string;
  unit: string;
  // 颜色方向：true=红(涨)、false=绿(跌)、null=中性灰；不传时按首尾对比
  trendUp?: boolean | null;
  // 横轴标签显示年份（YYYY-MM）；默认只显示 MM-DD
  //（数据跨多年时 MM-DD 无法看出时间跨度，如速览表展开大图的全量历史）
  showYearLabel?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    // 统一按日期升序（旧→新）绘制：调用方数据可能为降序（最新在前），
    // 不排序会导致时间轴颠倒、趋势与迷你图等镜像相反
    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
    const dates = sorted.map(d => d.date);
    const values = sorted.map(d => d.value);
    const cleanVals = cleanAxisValues(values);
    const hasData = cleanVals.length > 0;
    const yMin = Math.min(...cleanVals);
    const yMax = Math.max(...cleanVals);
    const yPad = hasData ? Math.max((yMax - yMin) * 0.05, Math.abs(yMax) * 0.005, 0.05) : 0.05;
    const axisMin = yMin >= 0 ? Math.max(0, yMin - yPad) : yMin - yPad;
    const axisMax = yMax <= 0 ? Math.min(0, yMax + yPad) : yMax + yPad;
    const up = trendUp ?? (values.length >= 2 && values[values.length - 1] >= values[0]);
    const color = up == null ? "#94a3b8" : up ? "#ef4444" : "#22c55e";

    echarts.dispose(ref.current);
    const chart = echarts.init(ref.current);
    chart.setOption({ backgroundColor: theme.background,
      tooltip: {
        trigger: "axis", backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { name: string; data: number }[]) => {
          const p = ps[0]; if (p.data == null) return "";
          return (p.name || "") + "<br/><b>" + (p.data?.toFixed(2) || "0") + "</b> " + unit;
        },
      },
      grid: { left: 0, right: 6, top: 4, bottom: 14, containLabel: true },
      xAxis: {
        type: "category", data: dates,
        axisLine: { lineStyle: { color: theme.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          show: true, fontSize: CHART_FONTS.axis, color: theme.secondaryText,
          interval: Math.max(Math.floor(dates.length / 4), 1),
          formatter: (v: string) => (showYearLabel ? v.slice(0, 7) : v.slice(5)), // YYYY-MM 或 MM-DD
        },
      },
      yAxis: {
        type: "value",
        min: hasData ? axisMin : undefined,
        max: hasData ? axisMax : undefined,
        splitNumber: 5,
        splitLine: { lineStyle: { color: theme.splitLine } },
        axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => formatAxisValue(v) },
      },
      series: [{
        type: "line", data: values,
        symbol: "none", smooth: true,
        lineStyle: { width: 1.8, color },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + "20" }, { offset: 1, color: color + "02" }
        ])},
      }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [data, title, unit, theme]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 140, backgroundColor: theme.background }}>
      <div ref={ref} style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: theme.background }} />
    </div>
  );
}
