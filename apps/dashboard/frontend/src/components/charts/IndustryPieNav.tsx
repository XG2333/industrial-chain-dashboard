import { useEffect, useMemo, useState } from "react";
import type { IndustryGroup } from "@/lib/industryGroups";

const MAJOR_COLORS = [
  "#2563eb",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#84cc16",
  "#f97316",
];

interface SliceItem {
  label: string;
  value: number;
  color: string;
  start: number;
  end: number;
  subIndex?: number;
}

function polar(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function donutPath(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  start: number,
  end: number,
) {
  if (end - start >= 359.999) {
    return `M ${cx - outerR} ${cy} A ${outerR} ${outerR} 0 1 1 ${cx + outerR} ${cy} A ${outerR} ${outerR} 0 1 1 ${cx - outerR} ${cy} M ${cx - innerR} ${cy} A ${innerR} ${innerR} 0 1 1 ${cx + innerR} ${cy} A ${innerR} ${innerR} 0 1 1 ${cx - innerR} ${cy}`;
  }
  const s = polar(cx, cy, outerR, start);
  const e = polar(cx, cy, outerR, end);
  const si = polar(cx, cy, innerR, end);
  const ei = polar(cx, cy, innerR, start);
  const largeArc = end - start > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${outerR} ${outerR} 0 ${largeArc} 1 ${e.x} ${e.y} L ${si.x} ${si.y} A ${innerR} ${innerR} 0 ${largeArc} 0 ${ei.x} ${ei.y} Z`;
}

function shade(hex: string, amount: number) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, Math.max(0, ((n >> 16) & 255) + amount));
  const g = Math.min(255, Math.max(0, ((n >> 8) & 255) + amount));
  const b = Math.min(255, Math.max(0, (n & 255) + amount));
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function shadeRange(hex: string, index: number, total: number) {
  const t = total > 1 ? index / (total - 1) : 0;
  return shade(hex, Math.round(72 - t * 122));
}

function formatPct(value: number, total: number) {
  if (!total) return "0.0%";
  return `${((value / total) * 100).toFixed(1)}%`;
}

function ExternalSliceLabels({
  slices,
  total,
  cx,
  cy,
  outerR,
  onSelect,
}: {
  slices: SliceItem[];
  total: number;
  cx: number;
  cy: number;
  outerR: number;
  onSelect?: (index: number) => void;
}) {
  const placed: { x: number; y: number }[] = [];
  return (
    <>
      {slices.map((slice, index) => {
        const mid = slice.start + (slice.end - slice.start) / 2;
        const edge = polar(cx, cy, outerR + 6, mid);
        let labelR = outerR + 58 + (index % 2) * 88;
        let label = polar(cx, cy, labelR, mid);
        let guard = 0;
        while (
          placed.some((p) => Math.hypot(p.x - label.x, p.y - label.y) < 62) &&
          guard < 8
        ) {
          labelR += 52;
          label = polar(cx, cy, labelR, mid);
          guard++;
        }
        placed.push(label);
        const anchor =
          mid < 18 || mid > 342 ? "middle" : mid <= 180 ? "start" : "end";

        return (
          <g
            key={slice.label}
            className={onSelect ? "cursor-pointer" : undefined}
            onClick={onSelect ? () => onSelect(index) : undefined}
          >
            <line
              x1={edge.x}
              y1={edge.y}
              x2={label.x}
              y2={label.y}
              stroke={slice.color}
              strokeWidth={1.5}
              strokeOpacity={0.85}
              strokeLinecap="round"
              className="pointer-events-none"
            />
            <text
              x={label.x}
              y={label.y - 5}
              textAnchor={anchor}
              fontSize={20}
              fontWeight={600}
              fill="#334155"
              className="pointer-events-auto select-none"
            >
              {slice.label}
            </text>
            <text
              x={label.x}
              y={label.y + 15}
              textAnchor={anchor}
              fontSize={16}
              fill="#64748b"
              className="pointer-events-auto select-none"
            >
              {slice.value} 条 · {formatPct(slice.value, total)}
            </text>
          </g>
        );
      })}
    </>
  );
}

interface IndustryPieNavProps {
  groups: IndustryGroup[];
  selectedMajor?: string | null;
  onSelectedMajorChange?: (major: string) => void;
  stackPies?: boolean;
  pieMode?: "both" | "major" | "sub";
  showPies?: boolean;
  showQuickNav?: boolean;
}

export function IndustryPieNav({
  groups,
  selectedMajor,
  onSelectedMajorChange,
  stackPies = false,
  pieMode = "both",
  showPies = true,
}: IndustryPieNavProps) {
  const [internalSelectedMajor, setInternalSelectedMajor] = useState<string | null>(null);
  const effectiveSelectedMajor = selectedMajor ?? internalSelectedMajor;
  const activeMajor =
    effectiveSelectedMajor && groups.some((g) => g.major === effectiveSelectedMajor)
      ? effectiveSelectedMajor
      : groups[0]?.major ?? null;

  useEffect(() => {
    if (selectedMajor === undefined) {
      setInternalSelectedMajor((prev) =>
        prev && groups.some((g) => g.major === prev) ? prev : groups[0]?.major ?? null,
      );
    }
  }, [groups, selectedMajor]);

  const updateSelectedMajor = (major: string) => {
    if (onSelectedMajorChange) onSelectedMajorChange(major);
    else setInternalSelectedMajor(major);
  };

  const majorItems = useMemo(
    () =>
      groups.map((group, groupIndex) => ({
        groupIndex,
        label: group.major,
        value: group.subs.reduce((sum, sub) => sum + sub.charts.length, 0),
      })),
    [groups],
  );

  const total = majorItems.reduce((sum, item) => sum + item.value, 0);
  const selectedGroupIndex = groups.findIndex((g) => g.major === activeMajor);
  const selectedGroup = selectedGroupIndex >= 0 ? groups[selectedGroupIndex] : null;
  const subItems =
    selectedGroup?.subs.map((sub, subIndex) => ({
      subIndex,
      label: sub.sub,
      value: sub.charts.length,
    })) ?? [];
  const subTotal = subItems.reduce((sum, item) => sum + item.value, 0);
  const baseColor = MAJOR_COLORS[Math.max(0, selectedGroupIndex % MAJOR_COLORS.length)];

  let cursor = 0;
  const majorSlices: SliceItem[] = majorItems.map((item, index) => {
    const start = cursor;
    const end = total > 0 ? cursor + (item.value / total) * 360 : 0;
    cursor = end;
    return {
      ...item,
      color: MAJOR_COLORS[index % MAJOR_COLORS.length],
      start,
      end,
    };
  });

  let subCursor = 0;
  const subSlices: SliceItem[] = subItems.map((item, index) => {
    const start = subCursor;
    const end = subTotal > 0 ? subCursor + (item.value / subTotal) * 360 : 0;
    subCursor = end;
    return {
      ...item,
      color: shadeRange(baseColor, index, subItems.length),
      start,
      end,
    };
  });

  const scrollToSub = (subIndex: number) => {
    if (selectedGroupIndex < 0) return;
    document
      .getElementById(`industry-${selectedGroupIndex}-${subIndex}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (!groups.length || !total) return null;

  return (
    <div className="border-b bg-slate-50/40">
      {showPies && (
        <>
          <div className="flex items-center justify-between border-b bg-card px-5 py-3">
            <h3 className="text-lg font-semibold text-foreground">指标类索引图</h3>
            <span className="text-xs text-muted-foreground whitespace-nowrap">{total} 条指标</span>
          </div>

          <div
            className={
              stackPies
                ? "grid grid-cols-1 gap-y-6 px-5 py-4"
                : "grid grid-cols-1 gap-x-10 gap-y-5 px-5 py-4 lg:grid-cols-2"
            }
          >
            {pieMode !== "sub" && (
              <section className="min-w-0">
                <div className="flex items-baseline justify-between mb-2">
                  <h4 className="text-sm font-semibold text-slate-700">大类指标分布</h4>
                  <span className="text-xs text-muted-foreground">{majorItems.length} 个大类</span>
                </div>
                <svg viewBox="0 0 900 620" className="w-full h-auto max-h-[640px] mx-auto" role="img" aria-label="大类指标分布饼图">
                  {majorSlices.map((slice, i) => (
                    <g
                      key={slice.label}
                      onClick={() => updateSelectedMajor(slice.label)}
                      className="cursor-pointer"
                    >
                      <title>{`${slice.label} ${slice.value} 条 ${formatPct(slice.value, total)}`}</title>
                      <path
                        d={donutPath(450, 310, 205, 112, slice.start, slice.end)}
                        fill={slice.color}
                        stroke={i === selectedGroupIndex ? "#0f172a" : "#fff"}
                        strokeWidth={i === selectedGroupIndex ? 3 : 1.5}
                        fillRule={slice.end - slice.start >= 359.999 ? "evenodd" : undefined}
                        className="transition-opacity hover:opacity-80"
                      />
                    </g>
                  ))}
                  <ExternalSliceLabels
                    slices={majorSlices}
                    total={total}
                    cx={450}
                    cy={310}
                    outerR={205}
                    onSelect={(index) => updateSelectedMajor(majorSlices[index].label)}
                  />
                  <text x="450" y="302" textAnchor="middle" fontSize="22" fontWeight="700" fill="#334155">共 {total} 条</text>
                  <text x="450" y="326" textAnchor="middle" fontSize="16" fill="#64748b">大类指标</text>
                </svg>
              </section>
            )}

            {pieMode !== "major" && (
              <section
                className={
                  stackPies && pieMode === "both"
                    ? "min-w-0 border-t border-slate-200 pt-6"
                    : "min-w-0"
                }
              >
                <div className="flex items-baseline justify-between mb-2">
                  <h4 className="text-sm font-semibold text-slate-700">
                    子类指标分布{selectedGroup ? `：${selectedGroup.major}` : ""}
                  </h4>
                  <span className="text-xs text-muted-foreground">{subItems.length} 个子类</span>
                </div>
                <svg viewBox="0 0 900 620" className="w-full h-auto max-h-[640px] mx-auto" role="img" aria-label={`${selectedGroup?.major ?? ""}子类指标分布饼图`}>
                  <defs>
                    {subSlices.map((slice, i) => (
                      <linearGradient key={`subGrad-${selectedGroupIndex}-${i}`} id={`subGrad-${selectedGroupIndex}-${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor={shade(slice.color, 40)} />
                        <stop offset="100%" stopColor={shade(slice.color, -30)} />
                      </linearGradient>
                    ))}
                  </defs>
                  {subSlices.map((slice, i) => (
                    <g
                      key={slice.label}
                      onClick={() => scrollToSub(slice.subIndex ?? 0)}
                      className="cursor-pointer"
                    >
                      <title>{`${slice.label} ${slice.value} 条 ${formatPct(slice.value, subTotal)}`}</title>
                      <path
                        d={donutPath(450, 310, 205, 112, slice.start, slice.end)}
                        fill={`url(#subGrad-${selectedGroupIndex}-${i})`}
                        stroke="#fff"
                        strokeWidth={2}
                        fillRule={slice.end - slice.start >= 359.999 ? "evenodd" : undefined}
                        className="transition-[filter] hover:brightness-110"
                      />
                    </g>
                  ))}
                  <ExternalSliceLabels
                    slices={subSlices}
                    total={subTotal}
                    cx={450}
                    cy={310}
                    outerR={205}
                    onSelect={(index) => scrollToSub(subSlices[index].subIndex ?? 0)}
                  />
                  {selectedGroup && (
                    <>
                      <text x="450" y="302" textAnchor="middle" fontSize="22" fontWeight="700" fill="#334155">{selectedGroup.major}</text>
                      <text x="450" y="326" textAnchor="middle" fontSize="16" fill="#64748b">{subTotal} 条</text>
                    </>
                  )}
                </svg>
              </section>
            )}
          </div>
        </>
      )}

    </div>
  );
}
