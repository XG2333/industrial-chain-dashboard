import { describe, expect, it } from "vitest";
import { colorParts } from "./analysisColor";

const clsOf = (s: string) => colorParts(s).map((x) => `${x.cls === "text-red-600" ? "R" : x.cls === "text-green-600" ? "G" : "N"}:${x.text}`);

describe("colorParts 涨跌着色", () => {
  it("千位逗号符号段整体着色", () => {
    const segs = colorParts("日增+1,905手");
    const r = segs.filter((x) => x.cls === "text-red-600").map((x) => x.text).join("");
    const n = segs.filter((x) => x.cls === "").map((x) => x.text).join("");
    expect(r).toContain("增+1,905手"); // 时间字"日"不着色
    expect(n).toContain("日");
    expect(r).toContain("1,905");
  });
  it("时间字(日/周/月/年)不着色, 仅数值着色", () => {
    const segs = colorParts("近5日-9.11%，近60日回撤16.2%");
    const g = segs.filter((x) => x.cls === "text-green-600").map((x) => x.text).join("");
    const n = segs.filter((x) => x.cls === "").map((x) => x.text).join("");
    expect(g).toContain("-9.11%");
    expect(g).toContain("回撤16.2%");
    expect(n).toContain("日");
    expect(n).toContain("5");
  });
  it("中文跌/涨/回撤词驱动着色", () => {
    const text = "现价142000，跌0.69%，位于日内区间39%分位；近5日跌9.11%，近60日回撤16.2%";
    const segs = colorParts(text);
    const g = segs.filter((x) => x.cls === "text-green-600").map((x) => x.text);
    expect(g.join("|")).toContain("跌0.69%");
    expect(g.join("|")).toContain("跌9.11%");
    expect(g.join("|")).toContain("回撤16.2%");
    const n = segs.filter((x) => x.cls === "").map((x) => x.text).join("");
    expect(n).toContain("142000");
    expect(n).toContain("39%");
  });
  it("符号形式正负", () => {
    expect(clsOf("-0.85%").some((x) => x.startsWith("G"))).toBe(true);
    expect(clsOf("+420手").some((x) => x.startsWith("R"))).toBe(true);
    expect(clsOf("10627手，周+1590 月+449").some((x) => x.startsWith("G"))).toBe(false);
  });
  it("N涨M跌 计数模式: 数字随方向着色", () => {
    const segs = colorParts("19只 8涨11跌 平均-0.33% 藏格矿业+0.85%领涨");
    const r = segs.filter((x) => x.cls === "text-red-600").map((x) => x.text).join("|");
    const g = segs.filter((x) => x.cls === "text-green-600").map((x) => x.text).join("|");
    const n = segs.filter((x) => x.cls === "").map((x) => x.text).join("");
    expect(r).toContain("8涨");
    expect(r).toContain("+0.85%");
    expect(g).toContain("11跌");
    expect(g).toContain("-0.33%");
    expect(n).toContain("19只");
    expect(n).toContain("平均");
    expect(n).toContain("藏格矿业");
    expect(n).toContain("领涨");
  });
  it("空输入", () => {
    expect(colorParts("")).toEqual([{ text: "", cls: "" }]);
  });
});
