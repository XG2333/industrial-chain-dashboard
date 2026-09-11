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

if (!fs.existsSync(CACHE_PATH)) {
  console.error(`missing cache: ${CACHE_PATH}`);
  process.exit(1);
}

const payload = JSON.parse(
  zlib.gunzipSync(fs.readFileSync(CACHE_PATH)).toString("utf8"),
);
const charts = Array.isArray(payload) ? payload : payload.charts;
if (!Array.isArray(charts) || charts.length === 0) {
  console.error("lithium cache does not contain charts");
  process.exit(1);
}

const apiCharts = charts.map((item) => ({
  ...item,
  catalogOrder: item.catalog_order,
}));

const expectedOrder = [...apiCharts].sort(
  (a, b) =>
    (a.catalog_order ?? Number.MAX_SAFE_INTEGER) -
    (b.catalog_order ?? Number.MAX_SAFE_INTEGER),
).map((item) => item.id);

const groups = industryGroups.buildIndustryGroups(apiCharts, 0);
const allRows = [];
const ordinaryIds = [];
const blockCases = [];
let ordinaryDrift = 0;
let compositeOrderChanges = 0;
let largeSameNameGroup = null;
let largeSingletonRun = null;
let multiBlockMixedRows = 0;
let blockOrderViolations = 0;
const orderViolationDetails = [];

for (const group of groups) {
  for (const sub of group.subs) {
    const rows = chartGrouping.groupChartRows(sub.charts);
    allRows.push(...rows);

    const inputIds = sub.charts.map((item) => item.id);
    const outputIds = rows.flat().map((item) => item.id);
    if (sub.composite) {
      if (inputIds.join("|") !== outputIds.join("|")) compositeOrderChanges += 1;
    } else if (inputIds.join("|") !== outputIds.join("|")) {
      ordinaryDrift += 1;
      ordinaryIds.push(...outputIds);
    } else {
      ordinaryIds.push(...outputIds);
    }

    for (const row of rows) {
      const keys = new Set(row.map((item) => chartGrouping.displayBlockKey(item)));
      if (row.length > 5) {
        console.error(`row too large: ${row.length}`);
      }
      const keyCounts = new Map();
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        keyCounts.set(key, (keyCounts.get(key) || 0) + 1);
      }
      // 新规则（排序规则.md §5）：N>=3 的 Display Block 独占行；
      // 仅允许"一个 3 张块 + 一个 2 张块"组合为一行（3+2=5）；
      // 2 张块可与相邻 2 张块或 singleton 混行。其他 3+ 块混行视为违规。
      const bigBlockKeys = [...keyCounts.entries()].filter(
        ([, count]) => count >= 3,
      );
      if (bigBlockKeys.length > 0 && keys.size > 1) {
        const bigCount = bigBlockKeys[0][1];
        const otherCount = row.length - bigCount;
        const legalCombo =
          bigBlockKeys.length === 1 && keys.size === 2 && bigCount === 3 && otherCount === 2;
        if (!legalCombo) {
          multiBlockMixedRows += 1;
        }
      }
    }

    const caseTitles = [
      "磷矿石",
      "磷酸",
      "磷酸一铵",
      "磷酸铁",
      "磷酸铁锂",
      "鳞片石墨",
      "球形石墨",
      "天然石墨",
      "石油焦",
      "针状焦",
      "石墨化",
      "人造石墨",
      "库存",
      "需求",
    ];
    for (const row of rows) {
      const hit = row.find((item) =>
        caseTitles.some((title) => (item.title || "").includes(title)),
      );
      if (hit && blockCases.length < 12) {
        blockCases.push({
          major: group.major,
          sub: sub.sub,
          composite: Boolean(sub.composite),
          row: row.map((item) => ({
            catalog_order: item.catalog_order,
            title: item.title,
            normalized_name: chartGrouping.normalizeIndicatorTitle(item.title || ""),
            major: item.major,
            sub: item.sub,
            freq: item.freq,
          })),
        });
      }
    }

    // block 顺序检查：子类内部先按板块顺序、板块内按 catalogOrder 递增（总览板块规则）。
    // 例外：同一归一化系列（同一产品+指标）内合约系列优先（主力 -> 一月 -> 五月…），
    // 与 chartGrouping.contractRankOf 保持一致。
    const SECTOR_ORDER = ["锂矿","锂盐","磷酸铁锂","三元正极","钴酸锂","锰酸锂","负极材料","隔膜","电解液产业链","辅材","电池电芯","储能","新能源汽车"];
    const SECTOR_ALIASES = { "碳酸锂": "锂盐", "氢氧化锂": "锂盐", "其他锂盐": "锂盐", "磷化工链": "磷酸铁锂" };
    const sectorRankOf = (item) => {
      const normalized = SECTOR_ALIASES[item.sector || ""] ?? (item.sector || "");
      const idx = SECTOR_ORDER.indexOf(normalized);
      return idx >= 0 ? idx : SECTOR_ORDER.length;
    };
    const contractRankOf = (title) => {
      const t = title || "";
      if (t.includes("主力合约")) return 0;
      if (t.includes("当月合约")) return 1;
      const cn = t.match(/(十一|十二|十|[一二三四五六七八九])月合约/);
      const CN = { "一":1, "二":2, "三":3, "四":4, "五":5, "六":6, "七":7, "八":8, "九":9, "十":10, "十一":11, "十二":12 };
      if (cn) return CN[cn[1]] ?? 99;
      const num = t.match(/(\d{1,2})合约/);
      if (num) return parseInt(num[1], 10);
      const lian = t.match(/连(十一|十二|十|[一二三四五六七八九])合约/);
      if (lian) return CN[lian[1]] ?? 99;
      return 99;
    };
    // 与 chartGrouping.contractBaseName 保持一致：去掉合约标识后的产品名判定同系列
    const contractBaseOf = (title) =>
      (title || "").replace(/(主力|当月|连[一二三四五六七八九十]+|[一二三四五六七八九十]+月|\d{1,2})合约/g, "").replace(/[\s：:_\-、]+/g, "");
    // 与 chartGrouping.productRankOf 保持一致：碳酸锂在氢氧化锂前；磷酸铁 -> 磷酸铁锂 -> 磷酸锰铁锂；
    // 含"电解液"的标题不参与产品 rank（"电解液（磷酸铁锂用）"是电解液，用途词不判产品）
    const productRankOf = (title) => {
      const t = title || "";
      if (t.includes("电解液")) return 99;
      if (t.includes("碳酸锂")) return 0;
      if (t.includes("氢氧化锂")) return 1;
      if (t.includes("磷酸锰铁锂")) return 4;
      if (t.includes("磷酸铁锂")) return 3;
      if (t.includes("磷酸铁")) return 2;
      return 99;
    };
    // 与 chartGrouping.FREQ_RANK 保持一致：日度 -> 周度 -> 月度 -> 季度 -> 年度
    const FREQ_RANK = { daily: 0, weekly: 1, monthly: 2, quarterly: 3, yearly: 4 };
    // 产品键：去掉频率后缀的基础标签（与 chartGrouping.prodKeyOf 一致）
    const prodKeyOf = (title) =>
      (industryGroups.productLabelOf(title) || "").replace(/-(日度|周度|月度|季度|年度)$/, "");
    // 产品基础名与形态层级（与 chartGrouping.productBaseOf / formRankOf 一致）：
    // "三元电芯"与"三元Pack"同属基础名"三元"，形态 电芯(0) < 电池(1) < Pack(2)
    const productBaseOf = (label) => label.replace(/(电芯|电池|Pack)$/, "");
    const formRankOf = (label) => {
      if (label.includes("Pack")) return 2;
      if (label.includes("电池")) return 1;
      if (label.includes("电芯")) return 0;
      return 0;
    };
    const blockInfo = new Map(); // key -> {sectorRank, freqRank, productRank, prodKey, baseKey, formRank, order, contractRank, base}
    const blockFirstOrder = new Map();
    const baseFirstOrder = new Map();
    for (const row of rows) {
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        const order = item.catalogOrder ?? Number.MAX_SAFE_INTEGER;
        const prev = blockInfo.get(key);
        if (!prev || order < prev.order) {
          blockInfo.set(key, {
            sectorRank: sectorRankOf(item),
            freqRank: FREQ_RANK[item.freq] ?? 99,
            productRank: productRankOf(item.title),
            prodKey: prodKeyOf(item.title),
            title: item.title,
            order,
            contractRank: contractRankOf(item.title),
            base: contractBaseOf(item.title),
          });
        }
        const pk = prodKeyOf(item.title);
        if (pk) {
          const prev = blockFirstOrder.get(pk) ?? Number.MAX_SAFE_INTEGER;
          if (order < prev) blockFirstOrder.set(pk, order);
          const bk = productBaseOf(pk);
          if (bk) {
            const prevBase = baseFirstOrder.get(bk) ?? Number.MAX_SAFE_INTEGER;
            if (order < prevBase) baseFirstOrder.set(bk, order);
          }
        }
      }
    }
    const seenBlockOrders = new Set();
    let lastBlockInfo = null;
    // 与 groupChartRows.groupList 排序一致：
    // (板块, 频率, 产品 rank, 产品基础名首次顺序, 形态层级 电芯<电池<Pack, 产品标签首次顺序, 同系列合约 rank, min order)
    const blockLess = (a, b) => {
      if (a.sectorRank !== b.sectorRank) return a.sectorRank < b.sectorRank;
      if (a.freqRank !== b.freqRank) return a.freqRank < b.freqRank;
      if (a.productRank !== b.productRank) return a.productRank < b.productRank;
      const bkA = productBaseOf(a.prodKey);
      const bkB = productBaseOf(b.prodKey);
      // 空基础名殿后（与 compareProductKeys 的 baseA === "" return 1 一致）
      if (bkA === "" && bkB !== "") return false;
      if (bkA !== "" && bkB === "") return false;
      if (bkA !== bkB) {
        const baseA = baseFirstOrder.get(bkA) ?? Number.MAX_SAFE_INTEGER;
        const baseB = baseFirstOrder.get(bkB) ?? Number.MAX_SAFE_INTEGER;
        if (baseA !== baseB) return baseA < baseB;
      }
      const formA = formRankOf(a.prodKey);
      const formB = formRankOf(b.prodKey);
      if (formA !== formB) return formA < formB;
      const pkA = blockFirstOrder.get(a.prodKey) ?? Number.MAX_SAFE_INTEGER;
      const pkB = blockFirstOrder.get(b.prodKey) ?? Number.MAX_SAFE_INTEGER;
      if (pkA !== pkB) return pkA < pkB;
      // 三元材料家族内（同"三元材料"标签）：系别 5系 < NCA < 6系 < 8系 < 9系
      if (a.prodKey === "三元材料" && b.prodKey === "三元材料") {
        const seriesRank = (t) => {
          const pairs = [[/5系/, 0], [/NCA/, 1], [/6系/, 2], [/8系/, 3], [/9系/, 4]];
          for (const [re, r] of pairs) if (re.test(t || "")) return r;
          return 5;
        };
        const sa = seriesRank(a.title);
        const sb = seriesRank(b.title);
        if (sa !== sb) return sa < sb;
      }
      if (a.order === b.order) return false;
      // 同一产品系列（去合约标识后同名）内：合约 rank 优先，其次 min order
      if (a.base === b.base && a.base !== "") {
        if (a.contractRank !== b.contractRank) return a.contractRank < b.contractRank;
      }
      return a.order < b.order;
    };
    for (const row of rows) {
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        if (seenBlockOrders.has(key)) continue;
        seenBlockOrders.add(key);
        const info = blockInfo.get(key);
        if (!info) continue;
        if (lastBlockInfo && blockLess(info, lastBlockInfo)) {
          blockOrderViolations += 1;
          if (orderViolationDetails.length < 20) {
            orderViolationDetails.push({
              major: group.major,
              sub: sub.sub,
              order: info.order,
              lastBlockSortKey: `${lastBlockInfo.sectorRank}/${lastBlockInfo.order}/${lastBlockInfo.base}/${lastBlockInfo.contractRank}`,
              title: item.title,
            });
          }
        }
        lastBlockInfo = info;
      }
    }

    const grouped = new Map();
    for (const row of rows) {
      for (const item of row) {
        const key = chartGrouping.displayBlockKey(item);
        if (!grouped.has(key)) grouped.set(key, 0);
        grouped.set(key, grouped.get(key) + 1);
      }
    }
    for (const [key, count] of grouped.entries()) {
      if (count > 5 && !largeSameNameGroup) {
        largeSameNameGroup = {
          major: group.major,
          sub: sub.sub,
          key,
          count,
          rows: rows
            .map((row, index) => ({ index, length: row.length }))
            .filter(({ index }) =>
              rows[index].some((item) => chartGrouping.displayBlockKey(item) === key),
            ),
        };
      }
    }

    const singletonRunRows = rows.filter((row) => row.length > 1);
    if (singletonRunRows.length >= 2 && !largeSingletonRun) {
      const sizes = singletonRunRows.map((row) => row.length);
      if (Math.max(...sizes) <= 5 && sizes.length >= 2) {
        largeSingletonRun = {
          major: group.major,
          sub: sub.sub,
          sizes,
        };
      }
    }
  }
}

const ordinarySet = new Set(ordinaryIds);
const expectedOrdinaryOrder = expectedOrder.filter((id) => ordinarySet.has(id));
let ordinaryOrderDrift = 0;
for (let index = 0; index < ordinaryIds.length; index++) {
  if (ordinaryIds[index] !== expectedOrdinaryOrder[index]) ordinaryOrderDrift += 1;
}

const validation = chartGrouping.validateChartRows(allRows);
const blockRowIndexes = new Map();
allRows.forEach((row, rowIndex) => {
  for (const item of row) {
    const key = chartGrouping.displayBlockKey(item);
    if (!blockRowIndexes.has(key)) blockRowIndexes.set(key, []);
    if (!blockRowIndexes.get(key).includes(rowIndex)) {
      blockRowIndexes.get(key).push(rowIndex);
    }
  }
});
const splitKeys = [...blockRowIndexes.entries()]
  .filter(([, indexes]) => {
    const sorted = [...indexes].sort((a, b) => a - b);
    return sorted.some((rowIndex, index) => index > 0 && rowIndex !== sorted[index - 1] + 1);
  })
  .map(([key, indexes]) => ({ key, indexes }));

console.log("=== REAL DATA VERIFICATION ===");
console.log(`charts=${charts.length}`);
console.log(`majors=${groups.length}`);
console.log(`rows=${allRows.length}`);
console.log(`ordinary_drift=${ordinaryDrift}`);
console.log(`block_order_violations=${blockOrderViolations}`);
if (orderViolationDetails.length > 0) {
  console.log(`order_violation_details=${JSON.stringify(orderViolationDetails.slice(0, 10))}`);
}
console.log(`multi_block_mixed_rows=${multiBlockMixedRows}`);
console.log(`composite_order_changes=${compositeOrderChanges}`);
console.log(`aggregated_flatten_drift=${ordinaryOrderDrift} (display block aggregation only; not a business-order violation)`);
if (ordinaryIds.length > 0) {
  console.log(`aggregated_drift_ids=${ordinaryIds.slice(0, 5).join(",")}`);
}
console.log(`max_row_size=${validation.maxRowSize}`);
console.log(`display_block_splits=${validation.displayBlockSplits}`);
if (splitKeys.length > 0) {
  console.log(`split_keys=${JSON.stringify(splitKeys.slice(0, 10))}`);
}
console.log(`row_balance_violations=${validation.rowBalanceViolations}`);
console.log(`large_same_name_group=${JSON.stringify(largeSameNameGroup)}`);
console.log(`large_singleton_run=${JSON.stringify({
  ...largeSingletonRun,
  sizes: largeSingletonRun?.sizes?.slice(0, 20),
})}`);
console.log("");
console.log("=== REAL CASES ===");
for (const item of blockCases) {
  console.log(`\n[${item.major} / ${item.sub}${item.composite ? " / composite" : ""}]`);
  for (const row of item.row) {
    console.log(
      `${row.catalog_order}\t${row.title}\t${row.normalized_name}\t${row.major}\t${row.sub}\t${row.freq}`,
    );
  }
}

await server.close();

if (
  blockOrderViolations !== 0 ||
  multiBlockMixedRows !== 0 ||
  validation.maxRowSize > 5 ||
  validation.displayBlockSplits !== 0 ||
  validation.rowBalanceViolations !== 0
) {
  process.exit(2);
}
