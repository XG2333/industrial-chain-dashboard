import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { createServer } from "vite";

const CACHE_PATH = path.resolve(process.cwd(), "../data/cache/lithium_charts.json.gz");
const server = await createServer({
  root: process.cwd(),
  logLevel: "error",
  server: { middlewareMode: true },
  appType: "custom",
  optimizeDeps: { noDiscovery: true },
});
const chartGrouping = await server.ssrLoadModule("/src/lib/chartGrouping.ts");
const industryGroups = await server.ssrLoadModule("/src/lib/industryGroups.ts");

const payload = JSON.parse(zlib.gunzipSync(fs.readFileSync(CACHE_PATH)).toString("utf8"));
const charts = (Array.isArray(payload) ? payload : payload.charts).map((item) => ({
  ...item,
  catalogOrder: item.catalog_order,
}));
const selected = charts.filter((c) => c.final_selected);
console.log(`总览 charts (final_selected): ${selected.length}`);

const SECTOR_ORDER = ["锂矿","锂盐","磷酸铁锂","三元正极","钴酸锂","锰酸锂","负极材料","隔膜","电解液产业链","辅材","电池电芯","储能","新能源汽车"];
const ALIASES = { "碳酸锂": "锂盐", "氢氧化锂": "锂盐", "其他锂盐": "锂盐", "磷化工链": "磷酸铁锂" };
const CN = { "一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"十一":11,"十二":12 };
const contractRankOf = (t) => {
  t = t || "";
  if (t.includes("主力合约")) return 0;
  if (t.includes("当月合约")) return 1;
  const cn = t.match(/(十一|十二|十|[一二三四五六七八九])月合约/);
  if (cn) return CN[cn[1]] ?? 99;
  const num = t.match(/(\d{1,2})合约/);
  if (num) return parseInt(num[1], 10);
  const lian = t.match(/连(十一|十二|十|[一二三四五六七八九])合约/);
  if (lian) return CN[lian[1]] ?? 99;
  return 99;
};
const contractBaseOf = (t) =>
  (t || "").replace(/(主力|当月|连[一二三四五六七八九十]+|[一二三四五六七八九十]+月|\d{1,2})合约/g, "").replace(/[\s：:_\-、]+/g, "");
const sectorRankOf = (s) => {
  const n = ALIASES[s || ""] ?? (s || "");
  const i = SECTOR_ORDER.indexOf(n);
  return i >= 0 ? i : SECTOR_ORDER.length;
};
// 与 chartGrouping.productRankOf 保持一致：碳酸锂在氢氧化锂前；磷酸铁 -> 磷酸铁锂 -> 磷酸锰铁锂
const productRankOf = (title) => {
  const t = title || "";
  if (t.includes("碳酸锂")) return 0;
  if (t.includes("氢氧化锂")) return 1;
  if (t.includes("磷酸锰铁锂")) return 4;
  if (t.includes("磷酸铁锂")) return 3;
  if (t.includes("磷酸铁")) return 2;
  return 99;
};
// 大类显式顺序：价格 -> 成本利润 -> 库存 -> 供给 -> 需求
const MAJOR_ORDER = ["价格", "成本利润", "库存", "供给", "需求"];
const majorRankOf = (m) => {
  const i = MAJOR_ORDER.indexOf(m);
  return i >= 0 ? i : MAJOR_ORDER.length;
};

let errors = 0;
const err = (msg) => { errors += 1; console.log("  !! " + msg); };

const groups = industryGroups.buildIndustryGroups(selected, 0);
console.log(`大类: ${groups.map((g) => g.major).join(" -> ")}`);

// 1. 子类顺序：按 subSectorRank 递增；同板块内按子类固定顺序（现货价格->…->期货价格->价差），
//    再合约 rank / minOrder（与 sortSubsBySector 一致）
const PRICE_SUB_ORDER = ["现货价格", "贸易金额", "期货价格", "现货价差", "价差", "基差", "月差", "指数"];
const subRankOf = (s) => {
  const i = PRICE_SUB_ORDER.indexOf(s);
  return i >= 0 ? i : PRICE_SUB_ORDER.length;
};
for (const group of groups) {
  let prevRank = -1;
  let prevSubRank = -1;
  let prevKey = null;
  for (const sub of group.subs) {
    const subRank = Math.min(...sub.charts.map((c) => sectorRankOf(c.sector)));
    const sRank = subRankOf(sub.sub);
    const minOrder = Math.min(...sub.charts.map((c) => c.catalogOrder ?? 9e9));
    const base = contractBaseOf(sub.sub);
    const cRank = contractRankOf(sub.sub);
    if (subRank < prevRank) err(`${group.major}/${sub.sub}: subSectorRank ${subRank} < prev ${prevRank}`);
    if (subRank === prevRank) {
      if (sRank < prevSubRank) {
        err(`${group.major}/${sub.sub}: 子类顺序 ${sub.sub}(${sRank}) < prev (${prevSubRank})`);
      } else if (sRank === prevSubRank) {
        if (prevKey?.base === base && cRank < 99) {
          if (cRank < prevKey.cRank) err(`${group.major}/${sub.sub}: 合约 rank ${cRank} < prev ${prevKey.cRank}`);
        } else if (minOrder < prevKey.order) {
          err(`${group.major}/${sub.sub}: minOrder ${minOrder} < prev ${prevKey.order} (同板块同子类)`);
        }
      }
    }
    prevRank = subRank;
    prevSubRank = sRank;
    prevKey = { base, cRank: cRank < 99 ? cRank : 9e9, order: minOrder };
  }
}

// 2. 行排布 + block 顺序 + 合约
const allRows = [];
for (const group of groups) {
  for (const sub of group.subs) {
    const rows = chartGrouping.groupChartRows(sub.charts);
    allRows.push(...rows);
    // block 顺序
    const FREQ_RANK = { daily: 0, weekly: 1, monthly: 2, quarterly: 3, yearly: 4 };
    const prodKeyOf = (title) =>
      (industryGroups.productLabelOf(title) || "").replace(/-(日度|周度|月度|季度|年度)$/, "");
    const blockInfo = new Map();
    const blockFirstOrder = new Map();
    for (const row of rows) {
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        const order = item.catalogOrder ?? 9e9;
        const prev = blockInfo.get(key);
        if (!prev || order < prev.order) {
          blockInfo.set(key, { sectorRank: sectorRankOf(item.sector), freqRank: FREQ_RANK[item.freq] ?? 99, productRank: productRankOf(item.title), prodKey: prodKeyOf(item.title), order, contractRank: contractRankOf(item.title), base: contractBaseOf(item.title) });
        }
        const pk = prodKeyOf(item.title);
        if (pk) {
          const prev = blockFirstOrder.get(pk) ?? 9e9;
          if (order < prev) blockFirstOrder.set(pk, order);
        }
      }
    }
    const seen = new Set();
    let last = null;
    const less = (a, b) => {
      if (a.sectorRank !== b.sectorRank) return a.sectorRank < b.sectorRank;
      if (a.freqRank !== b.freqRank) return a.freqRank < b.freqRank;
      if (a.productRank !== b.productRank) return a.productRank < b.productRank;
      const pkA = blockFirstOrder.get(a.prodKey) ?? 9e9;
      const pkB = blockFirstOrder.get(b.prodKey) ?? 9e9;
      if (pkA !== pkB) return pkA < pkB;
      if (a.order === b.order) return false;
      if (a.base === b.base && a.base !== "") {
        if (a.contractRank !== b.contractRank) return a.contractRank < b.contractRank;
      }
      return a.order < b.order;
    };
    for (const row of rows) {
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        if (seen.has(key)) continue;
        seen.add(key);
        const info = blockInfo.get(key);
        if (last && less(info, last)) err(`${group.major}/${sub.sub} block顺序: ${item.title} (order=${info.order}, sector=${item.sector})`);
        last = info;
      }
    }
    // 行大小/拆分/平衡
    for (const row of rows) {
      if (row.length > 5) err(`${group.major}/${sub.sub} 行超5: ${row.length}`);
      const keys = new Set(row.map((c) => chartGrouping.displayBlockKey(c)));
      if (keys.size > 1) {
        const cnt = new Map();
        for (const c of row) cnt.set(chartGrouping.displayBlockKey(c), (cnt.get(chartGrouping.displayBlockKey(c)) || 0) + 1);
        for (const [k, v] of cnt) {
          if (v >= 3 && keys.size > 1) {
            const legal = keys.size === 2 && v === 3 && row.length === 5;
            if (!legal) err(`${group.major}/${sub.sub} 3+块混行: ${row.map((c) => c.title).join(" | ")}`);
          }
        }
      }
    }
  }
}

// 3. 合约系列抽查：主力必须在该系列最前
for (const group of groups) {
  for (const sub of group.subs) {
    const rows = chartGrouping.groupChartRows(sub.charts);
    const flat = rows.flat();
    const seriesMap = new Map();
    for (const c of flat) {
      const base = contractBaseOf(c.title);
      const rank = contractRankOf(c.title);
      if (rank < 99) {
        if (!seriesMap.has(base)) seriesMap.set(base, []);
        seriesMap.get(base).push({ title: c.title, rank });
      }
    }
    for (const [base, list] of seriesMap) {
      if (list.length < 2) continue;
      const ranks = list.map((x) => x.rank);
      if (ranks[0] !== Math.min(...ranks)) err(`${group.major}/${sub.sub} 合约系列主力不在最前: ${JSON.stringify(list.map((x) => x.title))}`);
      const sorted = [...ranks].sort((a, b) => a - b);
      if (ranks.join(",") !== sorted.join(",")) err(`${group.major}/${sub.sub} 合约系列乱序: ${ranks.join(",")}`);
    }
  }
}

// 4. 总计/合计优先抽查（仅单 block 行内有效，跨 block 混合行不适用）
for (const group of groups) {
  for (const sub of group.subs) {
    const rows = chartGrouping.groupChartRows(sub.charts);
    for (const row of rows) {
      const keys = new Set(row.map((c) => chartGrouping.displayBlockKey(c)));
      if (keys.size !== 1) continue;
      const totals = row.filter((c) => /总计|合计/.test(c.title || ""));
      if (totals.length > 0 && totals.length < row.length) {
        const firstTotal = row.indexOf(totals[0]);
        const firstNonTotal = row.findIndex((c) => !/总计|合计/.test(c.title || ""));
        if (firstTotal > firstNonTotal) err(`${group.major}/${sub.sub} 总计未排最前: ${row.map((c) => c.title).join(" | ")}`);
      }
    }
  }
}

// 5. 板块顺序（一级）：锂矿 -> 锂盐(碳酸锂/氢氧化锂/其他锂盐，产品 rank 碳酸锂<氢氧化锂)
//    -> 磷酸铁锂 -> 磷化工链 -> 三元正极 -> …
let prevSectorRank = -1;
let prevSectorProd = -1;
for (const group of groups) {
  const sRank = Math.min(...group.subs.flatMap((s) => s.charts.map((c) => sectorRankOf(c.sector))));
  const pRank = Math.min(...group.subs.flatMap((s) => s.charts.map((c) => productRankOf(c.title))));
  if (sRank < prevSectorRank) err(`板块顺序违规: ${group.major} rank=${sRank} < prev ${prevSectorRank}`);
  if (sRank === prevSectorRank && pRank < prevSectorProd) err(`板块顺序违规(同板块): ${group.major} 产品rank=${pRank} < prev ${prevSectorProd}`);
  prevSectorRank = sRank;
  prevSectorProd = pRank;
}

// 6. 第一个板块必须是锂矿
const firstGroup = groups[0];
if (firstGroup) {
  const firstSector = Math.min(...firstGroup.subs.flatMap((s) => s.charts.map((c) => sectorRankOf(c.sector))));
  if (firstSector !== 0) err(`第一个板块不是锂矿: ${firstGroup.major}`);
  console.log(`第一板块: ${firstGroup.major}`);
}

console.log(`\n总行数: ${allRows.length}`);
console.log(errors === 0 ? "=== 总览排序检查: ALL PASS ===" : `=== 总览排序检查: ${errors} 个问题 ===`);
await server.close();
process.exit(errors === 0 ? 0 : 1);
