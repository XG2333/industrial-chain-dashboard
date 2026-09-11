const AXIS_PLACEHOLDER_VALUES = new Set([
  9998,
  9999,
  99998,
  99999,
  999998,
  999999,
  9999998,
  9999999,
]);

export function cleanAxisValues(values: number[], keepExtremes = false): number[] {
  const nums = values.filter((v): v is number => v != null && Number.isFinite(v));
  if (keepExtremes || nums.length < 3) return nums;

  const hasPlaceholder = nums.some((value) =>
    AXIS_PLACEHOLDER_VALUES.has(Math.abs(value)),
  );
  if (!hasPlaceholder) return nums;

  return nums.filter(
    (value) => !AXIS_PLACEHOLDER_VALUES.has(Math.abs(value)),
  );
}

// 根据轴最大值决定量级：标签不再逐个携带"千/万/亿"后缀，
// 统一按该量级缩放显示整数，量级名写在 y 轴下方（yAxis.name）。
export function axisScaleFor(maxAbs: number): { divisor: number; unit: string } {
  if (maxAbs >= 100000000) return { divisor: 100000000, unit: "亿" };
  if (maxAbs >= 10000) return { divisor: 10000, unit: "万" };
  if (maxAbs >= 1000) return { divisor: 1000, unit: "千" };
  return { divisor: 1, unit: "" };
}

// y 轴刻度标签：完整显示数字并加千分位（如 8,000），不缩放、不带量级单位；
// 绝对值 <10 且非整数时保留 1 位小数（避免小范围指标整数标签重复）
export function formatAxisValue(value: number, divisor = 1): string {
  const scaled = value / divisor;
  const text =
    Math.abs(scaled) < 10 && !Number.isInteger(scaled)
      ? scaled.toFixed(1)
      : String(Math.round(scaled));
  const parts = text.split(".");
  const grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return parts.length > 1 ? grouped + "." + parts[1] : grouped;
}
