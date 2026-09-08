import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { getYearColor } from "@/lib/chartColors";
import { cleanAxisValues, formatAxisValue } from "@/lib/chartFormat";
import { CHART_FONTS, useChartTheme } from "@/theme/chartTheme";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface FinPoint { period: string; value: number; yoy: number | null; }

export function FinChart({ data, title, isAnnual }: { data: FinPoint[]; title: string; isAnnual?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    const labels = data.map((d, i) => {
      if (isAnnual) return d.period.slice(0, 4);
      const y = d.period.slice(2, 4); const m = d.period.slice(5, 7);
      const q = Math.ceil(parseInt(m) / 3);
      const prev = i > 0 ? data[i - 1].period.slice(0, 4) : "";
      return (d.period.slice(0, 4) !== prev) ? y + "Q" + q : "Q" + q;
    });
    const values = data.map(d => d.value);
    const yoyVals = data.map(d => d.yoy);
    const cleanVals = cleanAxisValues(values.filter((v): v is number => v != null));
    const hasData = cleanVals.length > 0;
    const yMin = Math.min(...cleanVals);
    const yMax = Math.max(...cleanVals);
    const yPad = hasData ? Math.max((yMax - yMin) * 0.05, Math.abs(yMax) * 0.005, 0.05) : 0.05;
    const axisMin = yMin >= 0 ? Math.max(0, yMin - yPad) : yMin - yPad;
    const axisMax = yMax <= 0 ? Math.min(0, yMax + yPad) : yMax + yPad;
    const cleanYoy = cleanAxisValues(yoyVals.filter((v): v is number => v != null));
    const yoyHasData = cleanYoy.length > 0;
    const yoyMin = Math.min(...cleanYoy);
    const yoyMax = Math.max(...cleanYoy);
    const yoyPad = yoyHasData ? Math.max((yoyMax - yoyMin) * 0.05, Math.abs(yoyMax) * 0.005, 0.005) : 0.005;
    const yoyAxisMin = yoyMin >= 0 ? Math.max(0, yoyMin - yoyPad) : yoyMin - yoyPad;
    const yoyAxisMax = yoyMax <= 0 ? Math.min(0, yoyMax + yoyPad) : yoyMax + yoyPad;

    const chart = echarts.init(ref.current);
    chart.setOption({ backgroundColor: theme.background,
      tooltip: {
        trigger: "axis", backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: {seriesName:string; value:number}[]) => {
          return ps.map(p => {
            const v = p.value;
            if (p.seriesName === "同比") return p.seriesName + ": " + (v != null ? (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%" : "-");
            return p.seriesName + ": " + (v != null ? v.toFixed(2) + " 亿" : "-");
          }).join("<br/>");
        },
      },
      legend: {
        show: true, orient: "horizontal", top: -2, right: 4,
        itemWidth: 10, itemHeight: 10,
        textStyle: { fontSize: CHART_FONTS.legend, color: theme.legendText },
        data: ["绝对值", "同比"],
      },
      grid: { left: 2, right: 0, top: 18, bottom: 16, containLabel: true },
      xAxis: {
        type: "category", data: labels,
        axisLabel: {
          fontSize: isAnnual ? 8 : 7, color: theme.secondaryText, interval: 0, rotate: 0,
          rich: { b: { fontWeight: "bold", fontSize: isAnnual ? 8 : 7, color: theme.secondaryText } },
          formatter: (v: string) => v.includes("Q1") ? "{b|" + v + "}" : v,
        },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: theme.axisLine } },
      },
      yAxis: [
        { type: "value", min: hasData ? axisMin : undefined, max: hasData ? axisMax : undefined, splitNumber: 5, splitLine: { lineStyle: { color: theme.splitLine } }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => formatAxisValue(v) } },
        { type: "value", min: yoyHasData ? yoyAxisMin : undefined, max: yoyHasData ? yoyAxisMax : undefined, splitNumber: 5, splitLine: { show: false }, axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => (v * 100).toFixed(0) + "%" } },
      ],
      series: [
        {
          name: "绝对值",
          type: "bar",
          data: values.map((value, index) => ({
            value,
            itemStyle: {
              color: getYearColor(data[index].period.slice(0, 4), index),
              borderRadius: [3, 3, 0, 0],
            },
          })),
          barMaxWidth: 28,
          yAxisIndex: 0,
        },
        { name: "同比", type: "line", data: yoyVals, symbol: "circle", symbolSize: 5, lineStyle: { width: 1.8, color: "#4da6d9" }, itemStyle: { color: "#4da6d9" }, yAxisIndex: 1 },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [data, title, theme]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 140, backgroundColor: theme.background }}>
      <div ref={ref} style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: theme.background }} />
    </div>
  );
}
