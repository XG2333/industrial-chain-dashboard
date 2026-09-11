import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { getYearColor } from "@/lib/chartColors";
import { cleanAxisValues, formatAxisValue } from "@/lib/chartFormat";
import { CHART_FONTS, useChartTheme } from "@/theme/chartTheme";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface DataPoint { date: string; value: number; }

export function YearlyChart({ data, unit }: { title: string; unit: string; data: DataPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;

    const sorted = [...data]
      .filter((d) => d.value != null)
      .sort((a, b) => a.date.localeCompare(b.date));
    if (sorted.length === 0) return;

    const years = sorted.map((d) => d.date.slice(0, 4));
    const values = sorted.map((d) => d.value);
    const cleanVals = cleanAxisValues(values);
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
        trigger: "axis",
        axisPointer: { type: "shadow" }, // 悬停/滑过柱状即高亮该柱并显示数值
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { fontSize: CHART_FONTS.tooltip, color: theme.tooltipText },
        formatter: (ps: { name: string; data: number }[]) => {
          const p = ps[0];
          if (p.data == null) return "";
          return (p.name || "") + "<br/><b>" + (p.data?.toFixed(2) || "0") + "</b> " + unit;
        },
      },
      grid: { left: 0, right: 6, top: 6, bottom: 16, containLabel: true },
      xAxis: {
        type: "category",
        data: years,
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
        min: hasData ? axisMin : undefined,
        max: hasData ? axisMax : undefined,
        splitNumber: 5,
        splitLine: { lineStyle: { color: theme.splitLine } },
        axisLabel: { fontSize: CHART_FONTS.axis, color: theme.secondaryText, showMinLabel: false, showMaxLabel: false, margin: 1, formatter: (v: number) => formatAxisValue(v) },
      },
      series: [
        {
          type: "bar",
          data: years.map((year, index) => ({
            value: values[index],
            itemStyle: {
              color: getYearColor(year, index),
              borderRadius: [3, 3, 0, 0],
            },
          })),
          // barWidth 交给 echarts 按带宽自适应（多年份时固定宽度会溢出/挤压）
          emphasis: { itemStyle: { color: "#2563eb" } },
        },
      ],
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data, unit, theme]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 140, backgroundColor: theme.background }}>
      <div
        ref={ref}
        style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: theme.background }}
      />
    </div>
  );
}
