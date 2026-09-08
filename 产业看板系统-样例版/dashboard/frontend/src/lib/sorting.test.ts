import { describe, expect, it } from "vitest";
import type { ChartMeta } from "./chartTypes";
import {
  balancedRows,
  displayBlockKey,
  groupChartRows,
  normalizeIndicatorTitle,
  validateChartRows,
} from "./chartGrouping";
import { buildIndustryGroups } from "./industryGroups";

function chart(
  id: string,
  catalogOrder: number,
  overrides: Partial<ChartMeta> = {},
): ChartMeta {
  return {
    id,
    title: id,
    unit: "",
    category: "",
    source: "",
    major: "价格",
    sub: "现货价格",
    freq: "日度",
    catalogOrder,
    ...overrides,
  };
}

function flattenRows(rows: ChartMeta[][]): string[] {
  return rows.flatMap((row) => row.map((item) => item.id));
}

describe("chart grouping catalog order", () => {
  it("keeps catalog_order in flattened output", () => {
    const charts = [
      chart("A", 1),
      chart("B", 2),
      chart("C", 3),
    ];
    const rows = groupChartRows(charts);
    expect(flattenRows(rows)).toEqual(["A", "B", "C"]);
  });

  it("keeps catalog_order when a multi-chart block is present", () => {
    const charts = [
      chart("A", 1),
      chart("B1", 2, { title: "磷矿石（云南30%）" }),
      chart("B2", 3, { title: "磷矿石（四川30%）" }),
      chart("C", 4),
    ];
    const rows = groupChartRows(charts);
    expect(flattenRows(rows)).toEqual(["A", "B1", "B2", "C"]);
    // 新规则：2 张块与相邻 singleton 合并到同一行（1+2+1=4）
    expect(rows.map((row) => row.length)).toEqual([4]);
  });
});

describe("display block ordering", () => {
  it("orders blocks by product rank then min catalog_order", () => {
    const charts = [
      chart("磷矿石1", 1, { title: "磷矿石（云南30%）" }),
      chart("磷矿石2", 2, { title: "磷矿石（四川30%）" }),
      chart("磷矿石3", 3, { title: "磷矿石（贵州30%）" }),
      chart("磷酸1", 4, { title: "磷酸" }),
      chart("磷酸2", 5, { title: "磷酸" }),
      chart("磷酸铁", 6, { title: "磷酸铁" }),
    ];
    const rows = groupChartRows(charts);
    // 磷酸铁 productRank 优先（catalog_order 兜底）；3 张块与相邻 2 张块组合为一行（3+2=5）
    expect(rows.map((row) => row[0].title)).toEqual(["磷酸铁", "磷矿石（云南30%）"]);
  });

  it("does not split same indicator by region", () => {
    const charts = [
      chart("p1", 1, { title: "磷矿石（云南30%）" }),
      chart("p2", 2, { title: "磷矿石（四川30%）" }),
      chart("p3", 3, { title: "磷矿石（湖北28%）" }),
      chart("a1", 4, { title: "磷酸（云南）" }),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([3, 1]);
    expect(rows[0].map((item) => item.id)).toEqual(["p1", "p2", "p3"]);
    expect(rows[1][0].id).toBe("a1");
  });
});

describe("row packing", () => {
  it("never produces a row larger than 5", () => {
    const charts = Array.from({ length: 11 }, (_, index) =>
      chart(`x${index}`, index + 1, { title: "磷酸铁锂" }),
    );
    const rows = groupChartRows(charts);
    expect(rows.every((row) => row.length <= 5)).toBe(true);
    expect(rows.map((row) => row.length)).toEqual([4, 4, 3]);
  });

  it("balances oversized display blocks with minimum difference", () => {
    expect(balancedRows([1, 2, 3, 4, 5, 6], 5).map((row) => row.length)).toEqual([3, 3]);
    expect(balancedRows([1, 2, 3, 4, 5, 6, 7], 5).map((row) => row.length)).toEqual([4, 3]);
    expect(balancedRows([1, 2, 3, 4, 5, 6, 7, 8], 5).map((row) => row.length)).toEqual([4, 4]);
    expect(balancedRows(Array.from({ length: 11 }, (_, i) => i), 5).map((row) => row.length)).toEqual([4, 4, 3]);
  });

  it("packs 7 consecutive singleton blocks as 4 + 3", () => {
    const charts = Array.from({ length: 7 }, (_, index) =>
      chart(`single${index}`, index + 1, { title: `指标${index}` }),
    );
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([4, 3]);
  });

  it("does not merge singletons across frequencies", () => {
    const charts = [
      chart("dailyA", 1, { freq: "日度", title: "日度A" }),
      chart("dailyB", 2, { freq: "日度", title: "日度B" }),
      chart("weeklyC", 3, { freq: "周度", title: "周度C" }),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.map((item) => item.id))).toEqual([
      ["dailyA", "dailyB"],
      ["weeklyC"],
    ]);
  });

  it("keeps a multi-chart display block on its own rows", () => {
    const charts = [
      chart("rock1", 1, { title: "磷矿石" }),
      chart("rock2", 2, { title: "磷矿石" }),
      chart("rock3", 3, { title: "磷矿石" }),
      chart("rock4", 4, { title: "磷矿石" }),
      chart("acid", 5, { title: "磷酸" }),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([4, 1]);
  });
});

describe("industry group ordering", () => {
  it("orders sectors by industry chain order", () => {
    const charts = [
      chart("inventory", 1, { major: "库存", sub: "库存", title: "库存", sector: "碳酸锂" }),
      chart("price", 2, { major: "价格", sub: "现货价格", title: "价格", sector: "氢氧化锂" }),
    ];
    const groups = buildIndustryGroups(charts, 0);
    expect(groups.map((group) => group.major)).toEqual(["碳酸锂", "氢氧化锂"]);
  });

  it("orders subs by fixed sub table within sector", () => {
    const charts = [
      chart("month", 1, { major: "价格", sub: "月差", title: "月差", sector: "碳酸锂" }),
      chart("spot", 2, { major: "价格", sub: "现货价格", title: "现货价格", sector: "碳酸锂" }),
    ];
    const groups = buildIndustryGroups(charts, 0);
    expect(groups[0].subs.map((sub) => sub.sub)).toEqual(["现货价格", "月差"]);
  });

  it("places volume/position composite after fixed sub table within sector", () => {
    const charts = [
      chart("vol", 1, { major: "价格", sub: "成交量", title: "沪铜成交量: 月度", sector: "碳酸锂" }),
      chart("spot", 2, { major: "价格", sub: "现货价格", title: "沪铜现货价格: 月度", sector: "碳酸锂" }),
    ];
    const groups = buildIndustryGroups(charts, 0);
    expect(groups[0].subs.map((sub) => sub.sub)).toEqual(["现货价格", "沪铜"]);
    expect(groups[0].subs[1].composite).toBe(true);
  });

  it("keeps main-contract volume/position/ratio in one row even when only ratio carries a data-side composite tag", () => {
    // 数据侧 composite 标签可能只打在部分指标上（如同合约的成交持仓比），
    // 成交量/持仓量无标签走标题兜底 key——两者 key 必须一致，成交持仓比不能另起一行
    const compositeTag = [
      {
        category: "composite",
        value: JSON.stringify({
          composite_key: "碳酸锂|主力合约|日度|手|实际",
          composite_status: "MATCHED",
        }),
      },
    ];
    const charts = [
      chart("vol", 1, { major: "价格", sub: "成交量", title: "GFEX: 碳酸锂: 主力合约: 成交量: 日度", freq: "日度", sector: "碳酸锂" }),
      chart("oi", 2, { major: "价格", sub: "持仓", title: "GFEX: 碳酸锂: 主力合约: 持仓量: 日度", freq: "日度", sector: "碳酸锂" }),
      chart("ratio", 3, { major: "价格", sub: "成交持仓比", title: "碳酸锂主力合约成交持仓比", freq: "日度", sector: "碳酸锂", tags: compositeTag }),
    ];
    const keys = charts.map((c) => displayBlockKey(c));
    expect(new Set(keys).size).toBe(1);
  });

  it("keeps trade composite rows ordered import -> export -> net", () => {
    const charts = [
      chart("export", 1, { major: "进出口", sub: "出口", title: "中国金属锂出口: 月度", freq: "月度" }),
      chart("net", 2, { major: "进出口", sub: "净出口", title: "中国金属锂净出口: 月度", freq: "月度" }),
      chart("import", 3, { major: "进出口", sub: "进口", title: "中国金属锂进口: 月度", freq: "月度" }),
    ];
    const groups = buildIndustryGroups(charts, 0);
    expect(groups[0].subs.map((sub) => sub.sub)).toEqual(["中国金属锂"]);
    expect(groups[0].subs[0].charts.map((item) => item.sub)).toEqual([
      "进口",
      "出口",
      "净出口",
    ]);
  });
});

describe("row invariants", () => {
  it("reports valid rows without violations", () => {
    const charts = [
      chart("a", 1),
      chart("b", 2),
      chart("c", 3),
      chart("d", 4),
      chart("e", 5),
    ];
    const rows = groupChartRows(charts);
    const validation = validateChartRows(rows);
    expect(validation.maxRowSize).toBeLessThanOrEqual(5);
    expect(validation.displayBlockSplits).toBe(0);
    expect(validation.rowBalanceViolations).toBe(0);
  });

  it("detects a row larger than 5", () => {
    const badRows = [
      Array.from({ length: 6 }, (_, index) => chart(`x${index}`, index + 1)),
    ];
    const validation = validateChartRows(badRows);
    expect(validation.maxRowSize).toBe(6);
  });

  it("normalizes region/spec parenthetical variants into one block key", () => {
    expect(displayBlockKey(chart("a", 1, { title: "磷矿石（云南30%）" }))).toBe(
      displayBlockKey(chart("b", 2, { title: "磷矿石（四川30%）" })),
    );
    expect(normalizeIndicatorTitle("磷矿石（云南30%）")).toBe(
      normalizeIndicatorTitle("磷矿石（四川30%）"),
    );
  });

  it("normalizes generic split dimensions without business rank", () => {
    expect(
      normalizeIndicatorTitle("美国储能预期新增装机量分州级: 得克萨斯州: 年度"),
    ).toBe(normalizeIndicatorTitle("美国储能预期新增装机量分州级: 加州: 年度"));
    expect(
      displayBlockKey(chart("a", 1, { title: "中国新能源乘用车平均带电量: 分车型级别: A级: 月度" })),
    ).toBe(
      displayBlockKey(chart("b", 2, { title: "中国新能源乘用车平均带电量: 分车型级别: B级: 月度" })),
    );
  });
});
