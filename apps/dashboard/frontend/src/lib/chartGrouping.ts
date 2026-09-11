import type { ChartMeta } from "./chartTypes";
import {
  contractBaseName,
  contractRankOfTitle,
  productLabelOf,
  productRankOf,
  sectorRankOf,
  sectorSplitRankOf,
  tradeGroupKey,
} from "./industryGroups";

const INDICATOR_VARIABLE_WORDS = [
  "现货价格",
  "期货价格",
  "收盘价",
  "价格指数",
  "价格",
  "供需平衡",
  "平衡",
  "成交持仓比",
  "成交量",
  "成交额",
  "持仓量",
  "持仓",
  "库存天数",
  "库存指数",
  "库存量",
  "库存",
  "产量",
  "产能",
  "年化",
  "预测值",
  "预测",
  "开工率",
  "表观消费量",
  "消费量",
  "需求量",
  "供给量",
  "进口量",
  "出口量",
  "净出口额",
  "净出口",
  "进口额",
  "出口额",
  "进出口",
  "进口",
  "出口",
  "总计",
  "合计",
  "总额",
  "总量",
  "总",
  "金额",
  "利润",
  "成本",
  "价差",
  "基差",
  "月差",
  "同比",
  "环比",
  "值",
  "量",
  "额",
  "价",
];

const EXCHANGE_PREFIXES = ["SHFE:", "GFEX:", "DCE:", "CZCE:", "INE:"];
const CHINESE_MONTH_NUMBERS: Record<string, string> = {
  "\u4e00\u6708": "01",
  "\u4e8c\u6708": "02",
  "\u4e09\u6708": "03",
  "\u56db\u6708": "04",
  "\u4e94\u6708": "05",
  "\u516d\u6708": "06",
  "\u4e03\u6708": "07",
  "\u516b\u6708": "08",
  "\u4e5d\u6708": "09",
  "\u5341\u6708": "10",
  "\u5341\u4e00\u6708": "11",
  "\u5341\u4e8c\u6708": "12",
};

const SOURCE_PREFIXES = ["SMM:", "Mysteel:", "\u767e\u5ddd:", "Wind:", "iFind:"];

const INDICATOR_SPEC_WORDS = [
  "\u56fd\u4ea7",
  "\u542b\u7a0e",
  "\u4e0d\u542b\u7a0e",
  "\u51fa\u5382",
  "\u5230\u5382",
  "\u5230\u6e2f",
  "\u5747\u4ef7",
  "\u5e73\u5747\u4ef7",
  "\u5e73\u5747",
  "\u957f\u5355",
  "\u6563\u5355",
  "\u73b0\u8d27",
  "\u671f\u8d27",
  "\u9ad8\u7aef\u6b3e",
  "\u4e2d\u7aef\u6b3e",
  "\u4f4e\u7aef\u6b3e",
  "\u56de\u6536\u578b",
  "\u5bb9\u91cf\u578b",
  "\u52a8\u529b\u578b",
  "\u50a8\u80fd\u578b",
  "\u9ad8\u5bb9\u91cf\u578b",
  "\u9ad8\u500d\u7387\u578b",
  "\u5de5\u4e1a\u7ea7",
  "\u7535\u6c60\u7ea7",
  "\u6750\u6599\u7ea7",
  "\u7535\u82af\u7ea7",
  "\u4f18\u7b49\u54c1",
  "\u4e00\u7ea7\u54c1",
  "\u4e8c\u7ea7\u54c1",
  "\u5408\u683c\u54c1",
  "\u89c4\u683c",
  "\u578b\u53f7",
  "\u7c92\u5ea6",
  "\u7eaf\u5ea6",
  "\u542b\u91cf",
];

export function normalizeIndicatorTitle(title: string): string {
  let value = title;
  for (const word of INDICATOR_VARIABLE_WORDS) {
    value = value.split(word).join("");
  }
  if (value.includes("\u4eba\u9020\u77f3\u58a8") || value.includes("\u77f3\u58a8")) {
    for (const word of ["\u50a8\u80fd", "\u52a8\u529b", "\u6d88\u8d39"]) {
      value = value.split(word).join("");
    }
  }
  if (value.includes("\u7535\u82af\u51fa\u8d27")) {
    for (const word of ["\u4e09\u5143", "\u78f7\u9178\u94c1\u9502", "\u603b\u8ba1", "\u5408\u8ba1"]) {
      value = value.split(word).join("");
    }
  }
  if (value.includes("\u5206\u7535\u6c60\u7c7b\u578b") || value.includes("\u5e93\u5b58\u5206\u7535\u6c60\u7c7b\u578b")) {
    for (const word of ["\u50a8\u80fd\u7535\u6c60", "\u52a8\u529b\u7535\u6c60", "\u6d88\u8d39\u7535\u6c60", "\u4e09\u5143\u7535\u6c60", "\u78f7\u9178\u94c1\u9502\u7535\u6c60", "\u5206\u7535\u6c60\u7c7b\u578b", "\u7535\u6c60\u7c7b\u578b"]) {
      value = value.split(word).join("");
    }
  }
  for (const word of INDICATOR_SPEC_WORDS) {
    value = value.split(word).join("");
  }
  for (const prefix of EXCHANGE_PREFIXES) {
    value = value.split(prefix).join("");
  }
  for (const prefix of SOURCE_PREFIXES) {
    value = value.split(prefix).join("");
  }
  for (const [cn, num] of Object.entries(CHINESE_MONTH_NUMBERS)) {
    value = value.split(cn).join(num);
  }
  // 只删除显式维度词（分国别/分省份/分环节…）及其后的维度值；
  // 原正则 (分[^：:]{1,20}) 会误删"成本分类别: 280Ah磷酸铁锂储能电芯"中的
  // 电芯类型（如"分类别"），导致不同电芯类型的成本图被归为同一 Display Block。
  value = value.replace(
    /(分(?:国别|省份|环节|仓库|电池类型|车型级别|燃料类型|州级|地区|状态|场景)[^：:，,;；]{0,12})([：:][^：:，,;；]*)?/g,
    "",
  );
  value = value.replace(
    /(月度|周度|季度|年度|日度)/g,
    "",
  );
  value = value.replace(/Fe\/P\s*[:：]?\s*[0-9.%~\-\s]+/gi, "");
  value = value.replace(/\d+(\.\d+)?\s*%\s*[-~]\s*\d+(\.\d+)?\s*%/g, "");
  value = value.replace(/\d+(\.\d+)?\s*[-~]\s*\d+(\.\d+)?/g, "");
  // 电解液/三元前驱体/三元材料 保留括号（用途/规格维度）：
  // - "电解液（三元动力用）"与"电解液（磷酸铁锂用）"是不同规格指标，不应归并为同一
  //   Display Block——否则 9 种电解液报价合并为一个大 block 独占行均分 [5,4]，
  //   相邻的六氟磷酸锂 singleton 无法并入第二行。
  // - "三元前驱体（单晶/动力型）"与"（多晶/消费型）"是独立指标（专属行排布需要
  //   单晶/多晶 拆开：三元前驱体 6 指标 3+3、三元材料 8 指标 4+4）。
  if (!value.includes("电解液") && !value.includes("三元前驱体") && !value.includes("三元材料")) {
    value = value.replace(/[（(][^）)]*[）)]/g, "");
  }
  value = value.replace(/[\s：:，,。.（）()\-_/元吨手%]+/g, "");
  return value;
}

function splitIntoRows<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    rows.push(items.slice(index, index + size));
  }
  return rows;
}

function minimalGroupKey(chart: ChartMeta): string {
  const normalized = normalizeIndicatorTitle(chart.title || "") || chart.id;
  return [
    chart.major || "",
    chart.sub || "",
    chart.freq || "",
    normalized,
    // 板块维度：同一标题在不同板块的重复数据（如"储能型电芯"储能版/电池电芯版）
    // 必须分开成不同 block，否则会被 catalogOrder 靠前的板块"拉走"，打乱板块顺序
    chart.sector || "",
  ].join("|");
}

function chartTagValue(chart: ChartMeta, category: string): string {
  return chart.tags?.find((tag) => tag.category === category)?.value || "";
}

function compositeMeta(
  chart: ChartMeta,
): { composite_key?: string; composite_status?: string } | null {
  const tag = chart.tags?.find((t) => t.category === "composite");
  if (!tag || !tag.value) return null;
  try {
    const parsed = JSON.parse(tag.value);
    if (parsed && typeof parsed === "object") {
      return parsed as { composite_key?: string; composite_status?: string };
    }
  } catch {
    return null;
  }
  return null;
}

// 成交持仓专属兜底分组（用户确认规则）：即使数据侧 composite 元数据
// 缺失（如源数据命名差异导致分组失败），同一合约的 成交量/持仓量/成交持仓比
// 仍归为同一 Display Block。进出口的兜底统一由 tradeGroupKey 处理。
function tradeMarketFallbackKey(chart: ChartMeta): string | null {
  if (
    chart.sub === "成交量" ||
    chart.sub === "持仓" ||
    chart.sub === "持仓量" ||
    chart.sub === "成交持仓比"
  ) {
    const norm = normalizeIndicatorTitle(chart.title || "");
    const product = norm
      .replace(/成交量|成交额|持仓量|持仓|成交持仓比/g, "")
      .replace(/总计|合计|总量/g, "");
    if (product) return `ma:${chart.freq || ""}:${product}`;
  }
  return null;
}

export function displayBlockKey(chart: ChartMeta): string {
  // 进出口统一使用前端归组 key（与 industryGroups.tradeGroupKey 同源），
  // 不再依赖数据侧 composite 标签：净出口的 composite_key 与进口/出口
  // 不一致且 status 通常为 INCOMPLETE，导致净出口无法与进口/出口同行。
  if (chart.major === "进出口") {
    const tradeKey = tradeGroupKey(chart);
    if (tradeKey) {
      return tradeKey;
    }
  }
  // 成交持仓四类（成交量/成交/持仓/持仓量/成交持仓比）统一用标题兜底 key：
  // 数据侧 composite 标签可能只打在部分指标上（如同合约的成交持仓比），
  // 导致同一合约的 成交量/持仓量/成交持仓比 key 不一致、成交持仓比另起一行。
  // 兜底 key 由标题去词生成，同合约天然一致。
  const fallback = tradeMarketFallbackKey(chart);
  if (fallback) {
    return fallback;
  }
  // Composite Display Block (排序规则.md §6): rows sharing the same
  // composite_key (e.g. 成交量/持仓/成交持仓比 of the same contract) form
  // one display block so they stay on the same dashboard row.
  const composite = compositeMeta(chart);
  if (composite?.composite_key && composite.composite_status === "MATCHED") {
    return `composite:${composite.composite_key}`;
  }
  const base = minimalGroupKey(chart) || chart.id;
  const blockSuffix = chart.displayBlockTag ? `|${chart.displayBlockTag}` : "";
  const displayGroup = chartTagValue(chart, "display_group");
  const productFamily = chartTagValue(chart, "product_family");
  if (displayGroup && productFamily) {
    return `group:${productFamily}:${displayGroup}`;
  }
  return `${base}${blockSuffix}`;
}

export function balancedRows<T>(items: T[], maxPerRow: number): T[][] {
  const total = items.length;
  if (total === 0) return [];
  const rowCount = Math.ceil(total / maxPerRow);
  const base = Math.floor(total / rowCount);
  const remainder = total % rowCount;
  const rows: T[][] = [];
  let start = 0;
  for (let index = 0; index < rowCount; index++) {
    const size = base + (index < remainder ? 1 : 0);
    rows.push(items.slice(start, start + size));
    start += size;
  }
  return rows;
}

// 复合组行内固定业务顺序：进出口 进口->出口->净出口；
// 成交持仓 成交量->成交->持仓->持仓量->成交持仓比。
// 其他组（sub 不在表中）保持 catalogOrder，不受影响。
const IN_ROW_SUB_RANK: Record<string, number> = {
  "进口": 0,
  "出口": 1,
  "净出口": 2,
  "成交量": 0,
  "成交": 1,
  "持仓": 2,
  "持仓量": 3,
  "成交持仓比": 4,
};

// 实际/预测配对键：去掉"预测值/预测"（含前置连字符）后相同者视为一对，
// 排序时实际值在前、其预测值紧跟其后（如 产量、产量-预测值）。
function pairKeyOf(title: string | undefined): string {
  return (title || "")
    .replace(/[-—]\s*预测值?/g, "")
    .replace(/预测值?/g, "")
    .trim();
}

// 频率顺序（板块内第二维度，先于产品）：日度 -> 周度 -> 月度 -> 季度 -> 年度
const FREQ_RANK: Record<string, number> = {
  daily: 0,
  weekly: 1,
  monthly: 2,
  quarterly: 3,
  yearly: 4,
};

// 情绪因子族行内业务顺序：总计 -> 上游 -> 下游（用户确认）。
// 出货/成交/购货情绪因子同属"情绪"，行排布时先归一为同一 section（见 sectionKey），
// 同行内再按此次序排列；非情绪因子指标返回 -1（不参与排序）。
const MOOD_POSITIONS: [string, number][] = [
  ["总计", 0],
  ["上游", 1],
  ["下游", 2],
];
function moodRankOf(title: string | undefined): number {
  const t = title || "";
  if (!t.includes("情绪因子")) return -1;
  for (const [word, rank] of MOOD_POSITIONS) if (t.includes(word)) return rank;
  return 3;
}

function groupChartRowsCore(charts: ChartMeta[]): ChartMeta[][] {
  // ── 专属行排布（用户确认，针对当前数据，后续可调整；非通用规则）──
  // 三元正极板块 现货价格-日度：三元前驱体 6 个指标 → 3+3；三元材料 8 个指标 → 4+4。
  // 前提：normalizeIndicatorTitle 对"三元前驱体/三元材料"保留括号（单晶/多晶 拆为独立指标）。
  if (
    charts.length > 0 &&
    charts.every((c) => c.sector === "三元正极" && c.sub === "现货价格" && c.freq === "daily")
  ) {
    const grouped = new Map<string, ChartMeta[]>();
    const others: ChartMeta[] = [];
    for (const c of charts) {
      const key = (productLabelOf(c.title) || "").replace(/-(日度|周度|月度|季度|年度)$/, "");
      const family = key === "三元前驱体" ? "三元前驱体" : key === "三元材料" ? "三元材料" : "";
      if (family) {
        if (!grouped.has(family)) grouped.set(family, []);
        grouped.get(family)!.push(c);
      } else {
        others.push(c);
      }
    }
    const rows: ChartMeta[][] = [];
    // 组间顺序按组内最小 catalogOrder（前驱体组在前、材料组在后）
    const familyOrder = [...grouped.entries()].sort(
      (a, b) =>
        Math.min(...a[1].map((c) => c.catalogOrder ?? Number.MAX_SAFE_INTEGER)) -
        Math.min(...b[1].map((c) => c.catalogOrder ?? Number.MAX_SAFE_INTEGER)),
    );
    for (const [, list] of familyOrder) {
      const sorted = [...list].sort((a, b) => (a.catalogOrder ?? 0) - (b.catalogOrder ?? 0));
      rows.push(...balancedRows(sorted, 5));
    }
    if (others.length > 0) {
      rows.push(...balancedRows(others.sort((a, b) => (a.catalogOrder ?? 0) - (b.catalogOrder ?? 0)), 5));
    }
    return rows;
  }
  // 全局排序：先按板块顺序（总览规则，板块页单板块无影响），板块内按 catalogOrder
  // 产品键：去掉频率后缀的基础标签（用于同板块同频率内产品连续，
  // 避免"储能电池-周度 / 储能-周度"交替出现）
  const prodKeyOf = (chart: ChartMeta) => {
    const label = productLabelOf(chart.title);
    return label ? label.replace(/-(日度|周度|月度|季度|年度)$/, "") : "";
  };
  // 产品基础名：去掉 电芯/电池/Pack 形态后缀（"三元电芯"与"三元Pack"同属"三元"），
  // 用于同板块同频率内同一产品连排；基础名相同者再按形态层级
  // 电芯(0) < 电池(1) < Pack(2) 排列，使 Pack 紧跟对应电芯/电池系列。
  const productBaseOf = (label: string) => label.replace(/(电芯|电池|Pack)$/, "");
  const formRankOf = (label: string) => {
    if (label.includes("Pack")) return 2;
    if (label.includes("电池")) return 1;
    if (label.includes("电芯")) return 0;
    return 0;
  };
  const prodFirstOrder = new Map<string, number>();
  const baseFirstOrder = new Map<string, number>();
  for (const chart of charts) {
    const key = prodKeyOf(chart);
    // 取该产品键所有 block 的最小 catalogOrder（多个 block 共享同一产品键时，
    // 不能按"显示顺序首次出现"，否则首次顺序会失真）
    if (key) {
      const order = chart.catalogOrder ?? Number.MAX_SAFE_INTEGER;
      const prev = prodFirstOrder.get(key) ?? Number.MAX_SAFE_INTEGER;
      if (order < prev) prodFirstOrder.set(key, order);
      const base = productBaseOf(key);
      if (base) {
        const prevBase = baseFirstOrder.get(base) ?? Number.MAX_SAFE_INTEGER;
        if (order < prevBase) baseFirstOrder.set(base, order);
      }
    }
  }
  // 三元材料家族系别排序（行排布）：5系 < NCA < 6系 < 8系 < 9系。
  // NCA 三元材料与 5系 相邻（用户确认归入"三元前驱体-日度 ｜ 三元材料-日度"行）。
  const TERNARY_SERIES_RANK: [RegExp, number][] = [
    [/5系/, 0], [/NCA/, 1], [/6系/, 2], [/8系/, 3], [/9系/, 4],
  ];
  const ternarySeriesRank = (title: string | undefined): number => {
    const t = title || "";
    for (const [re, rank] of TERNARY_SERIES_RANK) if (re.test(t)) return rank;
    return 5;
  };
  // 产品键比较：空标签殿后 -> 产品基础名首次顺序 -> 形态层级（电芯/电池/Pack）
  // -> 产品标签首次顺序。与 groupList 排序共用，保证 ordered 与组间顺序一致。
  const compareProductKeys = (a: ChartMeta, b: ChartMeta): number => {
    const keyA = prodKeyOf(a);
    const keyB = prodKeyOf(b);
    if (keyA === "" && keyB !== "") return 1;
    if (keyB === "" && keyA !== "") return -1;
    if (keyA === keyB) {
      // 三元材料家族内（同"三元材料"标签）：系别 5系 < NCA < 6系 < 8系 < 9系
      if (keyA === "三元材料") {
        const seriesA = ternarySeriesRank(a.title);
        const seriesB = ternarySeriesRank(b.title);
        if (seriesA !== seriesB) return seriesA - seriesB;
      }
      return 0;
    }
    const baseA = productBaseOf(keyA);
    const baseB = productBaseOf(keyB);
    if (baseA === "" && baseB !== "") return 1;
    if (baseB === "" && baseA !== "") return -1;
    if (baseA !== baseB) {
      return (baseFirstOrder.get(baseA) ?? Number.MAX_SAFE_INTEGER) -
             (baseFirstOrder.get(baseB) ?? Number.MAX_SAFE_INTEGER);
    }
    const formA = formRankOf(keyA);
    const formB = formRankOf(keyB);
    if (formA !== formB) return formA - formB;
    return (prodFirstOrder.get(keyA) ?? Number.MAX_SAFE_INTEGER) -
           (prodFirstOrder.get(keyB) ?? Number.MAX_SAFE_INTEGER);
  };

  const ordered = [...charts].sort((a, b) => {
    const rankA = sectorRankOf(a.sector);
    const rankB = sectorRankOf(b.sector);
    if (rankA !== rankB) return rankA - rankB;
    // 同板块：锂盐拆分子板块分开（碳酸锂 < 氢氧化锂 < 其他锂盐），
    // 避免三者在归一化后混排（氯化锂 catalogOrder 小会紧贴锂矿区）
    const splitA = sectorSplitRankOf(a.sector);
    const splitB = sectorSplitRankOf(b.sector);
    if (splitA !== splitB) return splitA - splitB;
    // 同板块：频率优先（所有日度在前，再周度/月度…），
    // 否则产品 rank 会把"磷酸锰铁锂-日度"排到磷酸铁锂周度之后
    const freqA = FREQ_RANK[a.freq ?? ""] ?? 99;
    const freqB = FREQ_RANK[b.freq ?? ""] ?? 99;
    if (freqA !== freqB) return freqA - freqB;
    // 同频率：产品 rank（碳酸锂在氢氧化锂前、磷酸铁在磷酸锰铁锂前）
    const prodA = productRankOf(a.title);
    const prodB = productRankOf(b.title);
    if (prodA !== prodB) return prodA - prodB;
    // 同频率同产品：产品标签连续（Pack 紧跟对应电芯/电池系列）
    const keyCmp = compareProductKeys(a, b);
    if (keyCmp !== 0) return keyCmp;
    return (
      (a.catalogOrder ?? Number.MAX_SAFE_INTEGER) -
      (b.catalogOrder ?? Number.MAX_SAFE_INTEGER)
    );
  });
  const groups = new Map<string, ChartMeta[]>();

  for (const chart of ordered) {
    const key = displayBlockKey(chart);
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(chart);
  }

  // 组内排序：catalogOrder 是唯一业务排序真源，但复合组（进出口/成交持仓）
  // 行内按业务顺序展示，避免数据目录顺序（如净出口 catalogOrder 在前）打乱行内顺序。
  // 同一组内的"总计/合计"汇总图排最前（如"产能分国别: 总计"应在各国之前）；
  // 实际值与其预测值配对相邻（如 产量、产量-预测值、进口量、进口量-预测值）。
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const pairOrder = new Map<string, number>();
    for (const chart of group) {
      const key = pairKeyOf(chart.title);
      const order = chart.catalogOrder ?? Number.MAX_SAFE_INTEGER;
      const prev = pairOrder.get(key);
      pairOrder.set(key, prev == null ? order : Math.min(prev, order));
    }
    group.sort((a, b) => {
      const rankA = IN_ROW_SUB_RANK[a.sub || ""] ?? Number.MAX_SAFE_INTEGER;
      const rankB = IN_ROW_SUB_RANK[b.sub || ""] ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      const totalA = /总计|合计/.test(a.title || "") ? 0 : 1;
      const totalB = /总计|合计/.test(b.title || "") ? 0 : 1;
      if (totalA !== totalB) return totalA - totalB;
      const contractA = contractRankOfTitle(a.title);
      const contractB = contractRankOfTitle(b.title);
      if (contractA !== contractB) return contractA - contractB;
      const pairA = pairKeyOf(a.title);
      const pairB = pairKeyOf(b.title);
      const pairAOrder = pairOrder.get(pairA) ?? Number.MAX_SAFE_INTEGER;
      const pairBOrder = pairOrder.get(pairB) ?? Number.MAX_SAFE_INTEGER;
      if (pairAOrder !== pairBOrder) return pairAOrder - pairBOrder;
      const predA = /预测/.test(a.title || "") ? 1 : 0;
      const predB = /预测/.test(b.title || "") ? 1 : 0;
      if (predA !== predB) return predA - predB;
      return (
        (a.catalogOrder ?? Number.MAX_SAFE_INTEGER) -
        (b.catalogOrder ?? Number.MAX_SAFE_INTEGER)
      );
    });
  }

  // 组间顺序：先按板块顺序（与 ordered 一致），同板块内频率优先
  // （所有日度在前 -> 周度 -> …），频率内产品 rank -> 产品标签连续 -> 合约系列 -> min(catalogOrder)。
  // 如成交持仓复合组主力合约 catalogOrder 靠后但业务上应排最前。
  const groupList = [...groups.values()].sort((a, b) => {
    const rankA = sectorRankOf(a[0].sector);
    const rankB = sectorRankOf(b[0].sector);
    if (rankA !== rankB) return rankA - rankB;
    // 同板块：锂盐拆分子板块分开（与 ordered 排序一致，保证组间与组内顺序一致）
    const splitA = sectorSplitRankOf(a[0].sector);
    const splitB = sectorSplitRankOf(b[0].sector);
    if (splitA !== splitB) return splitA - splitB;
    const freqA = FREQ_RANK[a[0].freq ?? ""] ?? 99;
    const freqB = FREQ_RANK[b[0].freq ?? ""] ?? 99;
    if (freqA !== freqB) return freqA - freqB;
    const prodA = productRankOf(a[0].title);
    const prodB = productRankOf(b[0].title);
    if (prodA !== prodB) return prodA - prodB;
    const keyCmp = compareProductKeys(a[0], b[0]);
    if (keyCmp !== 0) return keyCmp;
    const baseA = contractBaseName(a[0].title || "");
    const baseB = contractBaseName(b[0].title || "");
    if (baseA === baseB) {
      const contractA = contractRankOfTitle(a[0].title);
      const contractB = contractRankOfTitle(b[0].title);
      if (contractA !== contractB) return contractA - contractB;
    }
    // 情绪因子族行内顺序：总计 -> 上游 -> 下游（优先于 catalogOrder）
    const moodA = moodRankOf(a[0].title);
    const moodB = moodRankOf(b[0].title);
    if (moodA >= 0 && moodB >= 0 && moodA !== moodB) return moodA - moodB;
    const orderA = Math.min(
      ...a.map((chart) => chart.catalogOrder ?? Number.MAX_SAFE_INTEGER),
    );
    const orderB = Math.min(
      ...b.map((chart) => chart.catalogOrder ?? Number.MAX_SAFE_INTEGER),
    );
    return orderA - orderB;
  });

  // ── Row Packing（排序规则.md §5）──
  // N>=3 的 Display Block 独占行；2 张块与相邻的 2/3 张块或 singleton 组合到一行
  // （一行最多 5 张，块不可拆分；2+2+2 -> 4+2）；跨行组合保持 大类/子类/频率 硬边界。
  const rows: ChartMeta[][] = [];
  // 行排布硬边界：大类/子类/频率 + 板块（去产品/规格维度，方案 A）。
  // 同板块同子类同频率内的 singleton 可跨产品合并为一行（产业链环节指标族横排：
  // 如碳酸锂板块 成本-日度 的 碳酸锂/磷酸铁锂/锂云母精矿 等原料路线成本单图合并 5+1）。
  // 不同板块的图不合并到同一行（板块仍是硬边界）。
  const sectionKey = (chart: ChartMeta) =>
    [
      // 情绪因子族归一：出货/成交/购货情绪因子 数据侧 major 分别落在 供给/需求，
      // 用户确认同属"情绪"应排同一行 —— 标题含"情绪因子"的指标统一归为一节
      (chart.title || "").includes("情绪因子") ? "情绪因子" : chart.major || "",
      chart.sub || "",
      chart.freq || "",
      chart.sector || "",
    ].join("|");
  const pendingElements: ChartMeta[][] = []; // 待组合元素（singleton 或 2 张块）
  let pendingTriple: ChartMeta[] | null = null; // 暂存的 N>=3 块（等待与后续 2 张块组合）

  // 结算待组合元素为行：按序贪心填充，2 张块不可拆分，且整行保持同 section；
  // 纯 singleton 流保持最小差值均分（如 7 个 -> 4+3）
  const flushElements = () => {
    if (pendingElements.every((element) => element.length === 1)) {
      // 纯 singleton：先按 大类/子类/频率 分段，段内最小差值均分
      let segment: ChartMeta[] = [];
      let segmentSection = "";
      const flushSegment = () => {
        if (segment.length > 0) rows.push(...balancedRows(segment, 5));
        segment = [];
      };
      for (const element of pendingElements) {
        const elementSection = sectionKey(element[0]);
        if (segmentSection !== "" && elementSection !== segmentSection) {
          flushSegment();
        }
        segment.push(...element);
        segmentSection = elementSection;
      }
      flushSegment();
      pendingElements.length = 0;
      return;
    }
    let row: ChartMeta[] = [];
    let rowSection = "";
    for (const element of pendingElements) {
      const elementSection = sectionKey(element[0]);
      const fitsSize = row.length + element.length <= 5;
      const fitsSection = rowSection === "" || rowSection === elementSection;
      if (fitsSize && fitsSection) {
        row.push(...element);
        rowSection = elementSection;
      } else {
        if (row.length > 0) rows.push(row);
        row = [...element];
        rowSection = elementSection;
      }
    }
    if (row.length > 0) rows.push(row);
    pendingElements.length = 0;
  };

  for (const group of groupList) {
    if (group.length === 1) {
      if (pendingTriple) {
        rows.push(pendingTriple);
        pendingTriple = null;
      }
      pendingElements.push(group);
    } else if (group.length === 2) {
      if (pendingTriple && pendingTriple.length === 3 &&
          sectionKey(pendingTriple[0]) === sectionKey(group[0])) {
        // 3+2 组合为一行（仅同板块；4/5 张块不与 2 张块组合，避免超 5 张）
        rows.push([...pendingTriple, ...group]);
        pendingTriple = null;
      } else {
        if (pendingTriple) {
          rows.push(pendingTriple);
          pendingTriple = null;
        }
        pendingElements.push(group);
      }
    } else {
      // N>=3：独占行；若前一个待组合元素恰好是单个 2 张块且本块为 3 张，则 2+3 组合为一行
      if (pendingTriple) {
        rows.push(pendingTriple);
        pendingTriple = null;
      }
      const lastElement = pendingElements[pendingElements.length - 1];
      if (lastElement && lastElement.length === 2 && pendingElements.length === 1 && group.length === 3 &&
          sectionKey(lastElement[0]) === sectionKey(group[0])) {
        pendingElements.pop();
        rows.push([...lastElement, ...group]);
      } else {
        flushElements();
        if (group.length > 5) {
          rows.push(...balancedRows(group, 5));
        } else {
          pendingTriple = group;
        }
      }
    }
  }
  if (pendingTriple) rows.push(pendingTriple);
  flushElements();
  return rows;
}

// 连续单图行最终合并（在 §5 Row Packing 之后）：packing 按"大类/子类/频率"硬边界
// 组合，跨频率的相邻单图行仍会各占一行（如 锂辉石精矿-日度 与 锂辉石精矿-周度）。
// 规则（用户确认）：同一子类内相邻的单图行（每行仅一张图）合并为一行
// （≤5 张，行内保持原顺序），行标题由各图标签并列（如"锂辉石精矿-日度 | 锂辉石精矿-周度"）；
// 不同子类（不同 h4 组/大类）不参与合并。
function mergeLonelySingleRows(rows: ChartMeta[][]): ChartMeta[][] {
  const out: ChartMeta[][] = [];
  let pending: ChartMeta[] = [];
  const flush = () => {
    if (pending.length > 0) {
      out.push(...balancedRows(pending, 5));
      pending = [];
    }
  };
  for (const row of rows) {
    if (row.length === 1) {
      pending.push(row[0]);
    } else {
      flush();
      out.push(row);
    }
  }
  flush();
  return out;
}

export function groupChartRows(charts: ChartMeta[]): ChartMeta[][] {
  return mergeLonelySingleRows(groupChartRowsCore(charts));
}

export interface ChartRowValidation {
  maxRowSize: number;
  displayBlockSplits: number;
  rowBalanceViolations: number;
}

export function validateChartRows(rows: ChartMeta[][]): ChartRowValidation {
  let maxRowSize = 0;
  const blockRows = new Map<string, number[]>();
  const blockRowSizes = new Map<string, number[]>();

  rows.forEach((row, rowIndex) => {
    maxRowSize = Math.max(maxRowSize, row.length);
    for (const chart of row) {
      const key = displayBlockKey(chart);
      if (!blockRows.has(key)) blockRows.set(key, []);
      if (!blockRowSizes.has(key)) blockRowSizes.set(key, []);
      if (!blockRows.get(key)!.includes(rowIndex)) {
        blockRows.get(key)!.push(rowIndex);
      }
    }
    const seen = new Set<string>();
    for (const chart of row) {
      const key = displayBlockKey(chart);
      if (!seen.has(key)) {
        const sizes = blockRowSizes.get(key)!;
        sizes.push(row.length);
        seen.add(key);
      }
    }
  });

  let displayBlockSplits = 0;
  for (const indices of blockRows.values()) {
    const sorted = [...indices].sort((a, b) => a - b);
    const isContiguous = sorted.every(
      (rowIndex, index) => index === 0 || rowIndex === sorted[index - 1] + 1,
    );
    if (!isContiguous) displayBlockSplits += 1;
  }

  let rowBalanceViolations = 0;
  for (const sizes of blockRowSizes.values()) {
    if (sizes.length > 1 && Math.max(...sizes) - Math.min(...sizes) > 1) {
      rowBalanceViolations += 1;
    }
  }

  return { maxRowSize, displayBlockSplits, rowBalanceViolations };
}
