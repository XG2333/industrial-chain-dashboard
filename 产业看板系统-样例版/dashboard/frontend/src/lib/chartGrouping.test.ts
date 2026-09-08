import { describe, expect, it } from "vitest";

import type { ChartMeta } from "./chartTypes";
import { groupChartRows } from "./chartGrouping";


function chart(
  id: string,
  title: string,
  options: Partial<ChartMeta> = {},
): ChartMeta {
  return {
    id,
    title,
    unit: "",
    category: "",
    source: "",
    major: "库存",
    sub: "库存",
    freq: "周度",
    catalogOrder: 0,
    ...options,
  };
}


function portInventory(id: string, order: number, name: string): ChartMeta {
  return chart(id, name, {
    catalogOrder: order,
    tags: [
      { category: "product_family", value: "锂矿" },
      { category: "display_group", value: "港口库存" },
    ],
  });
}

// 构造一个 2 张图的 Display Block（同 display_group + product_family）
function pairBlock(id1: string, id2: string, order: number, name: string, displayGroup: string): ChartMeta[] {
  return [
    chart(id1, `${name}1`, {
      catalogOrder: order,
      tags: [
        { category: "product_family", value: "锂矿" },
        { category: "display_group", value: displayGroup },
      ],
    }),
    chart(id2, `${name}2`, {
      catalogOrder: order + 1,
      tags: [
        { category: "product_family", value: "锂矿" },
        { category: "display_group", value: displayGroup },
      ],
    }),
  ];
}


describe("groupChartRows display_group", () => {
  it("packs 6 port inventory charts as 3+3", () => {
    const charts = [
      portInventory("p1", 1, "港口库存总计"),
      portInventory("p2", 2, "其他港口"),
      portInventory("p3", 3, "南通港"),
      portInventory("p4", 4, "钦州港"),
      portInventory("p5", 5, "镇江港"),
      portInventory("p6", 6, "青岛港"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([3, 3]);
  });

  it("keeps 3 ungrouped consecutive singletons in one row", () => {
    const charts = [
      chart("a", "外采库存", { catalogOrder: 1 }),
      chart("b", "厂内库存", { catalogOrder: 2 }),
      chart("c", "在途库存", { catalogOrder: 3 }),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([3]);
  });

  it("does not mix different display groups", () => {
    const charts = [
      chart("a", "可售库存", { catalogOrder: 1 }),
      chart("b", "贸易商库存", { catalogOrder: 2 }),
      portInventory("p1", 3, "南通港"),
      portInventory("p2", 4, "钦州港"),
      portInventory("p3", 5, "镇江港"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([2, 3]);
  });

  it("preserves catalog order inside a display group", () => {
    const charts = [
      portInventory("p1", 1, "南通港"),
      portInventory("p2", 2, "钦州港"),
      portInventory("p3", 3, "镇江港"),
    ];
    const rows = groupChartRows(charts);
    const flat = rows.flat().map((item) => item.id);
    expect(flat).toEqual(["p1", "p2", "p3"]);
  });

  it("packs 11 port inventory charts as 4+4+3", () => {
    const charts = Array.from({ length: 11 }, (_, index) =>
      portInventory(`p${index + 1}`, index + 1, `港口${index + 1}`),
    );
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([4, 4, 3]);
  });

  it("combines two 2-chart blocks into one row (2+2=4)", () => {
    const charts = [
      ...pairBlock("a1", "a2", 1, "港口A", "港口库存"),
      ...pairBlock("b1", "b2", 3, "贸易商", "贸易商库存"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([4]);
  });

  it("combines 3-chart block with adjacent 2-chart block into one row (3+2=5)", () => {
    const charts = [
      portInventory("p1", 1, "南通港"),
      portInventory("p2", 2, "钦州港"),
      portInventory("p3", 3, "镇江港"),
      ...pairBlock("b1", "b2", 4, "贸易商", "贸易商库存"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([5]);
  });

  it("combines 2-chart block before 3-chart block into one row (2+3=5)", () => {
    const charts = [
      ...pairBlock("b1", "b2", 1, "贸易商", "贸易商库存"),
      portInventory("p1", 3, "南通港"),
      portInventory("p2", 4, "钦州港"),
      portInventory("p3", 5, "镇江港"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([5]);
  });

  it("packs three 2-chart blocks as 4+2", () => {
    const charts = [
      ...pairBlock("a1", "a2", 1, "库存A", "甲"),
      ...pairBlock("b1", "b2", 3, "库存B", "乙"),
      ...pairBlock("c1", "c2", 5, "库存C", "丙"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([4, 2]);
  });

  it("combines 2-chart block with singleton on each side (2+1+2=5)", () => {
    const charts = [
      ...pairBlock("a1", "a2", 1, "库存A", "甲"),
      chart("s", "外采库存", { catalogOrder: 3 }),
      ...pairBlock("b1", "b2", 4, "库存B", "乙"),
    ];
    const rows = groupChartRows(charts);
    expect(rows.map((row) => row.length)).toEqual([5]);
  });
});
