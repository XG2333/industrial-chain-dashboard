import { describe, expect, it } from "vitest";
import { sampleWeekly } from "./IndicatorSummaryTable";

describe("sampleWeekly", () => {
  it("samples one point per ISO week (latest first) for double-point weekly data", () => {
    // 问题周度数据：每周 2 点（周四新值 + 周三与上周四重复的值）
    const data = [
      { date: "2026-08-14", value: 2082.8 },
      { date: "2026-08-13", value: 2049.0 },
      { date: "2026-08-07", value: 2049.0 },
      { date: "2026-08-06", value: 2094.0 },
      { date: "2026-07-31", value: 2094.0 },
      { date: "2026-07-30", value: 2105.0 },
    ];
    const out = sampleWeekly(data);
    expect(out.map((p) => p.date)).toEqual(["2026-08-14", "2026-08-07", "2026-07-31"]);
    expect(out.map((p) => p.value)).toEqual([2082.8, 2049.0, 2094.0]);
  });
  it("keeps normal weekly data unchanged", () => {
    const data = [
      { date: "2026-08-14", value: 1 },
      { date: "2026-08-07", value: 2 },
      { date: "2026-07-31", value: 3 },
    ];
    expect(sampleWeekly(data).map((p) => p.date)).toEqual(["2026-08-14", "2026-08-07", "2026-07-31"]);
  });
  it("handles week boundary (sunday belongs to same monday-start week)", () => {
    // 2026-08-09 是周日、08-03 是周一——同一周（周一 08-03 起），采样只保留 08-09
    const data = [
      { date: "2026-08-09", value: 5 },
      { date: "2026-08-07", value: 5 },
      { date: "2026-08-03", value: 4 },
    ];
    const out = sampleWeekly(data);
    expect(out.map((p) => p.date)).toEqual(["2026-08-09"]);
  });
});
