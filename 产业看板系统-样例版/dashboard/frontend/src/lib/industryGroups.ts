import type { ChartMeta } from "./chartTypes";

export interface IndustryChart extends ChartMeta {
  data?: { date: string; value: number }[];
}

export interface IndustrySubGroup {
  sub: string;
  title?: string;
  composite?: boolean;
  charts: IndustryChart[];
}

export interface IndustryGroup {
  major: string;
  subs: IndustrySubGroup[];
}

const TRADE_MAJOR = "进出口";
const TRADE_IMPORT = "进口";
const TRADE_EXPORT = "出口";
const TRADE_NET = "净出口";
const TRADE_QTY = "量";
const TRADE_AMOUNT = "额";
const TRADE_SUB_ORDER = [TRADE_IMPORT, TRADE_EXPORT, TRADE_NET];
const TRADE_FREQ_SUFFIXES = ["月度", "周度", "季度", "年度"];

function orderIdx(list: string[], value: string): number {
  const i = list.indexOf(value);
  return i >= 0 ? i : list.length;
}

function minCatalogOrder(charts: IndustryChart[]): number {
  const orders = charts
    .map((chart) => chart.catalogOrder)
    .filter((order): order is number => order != null);
  return orders.length > 0 ? Math.min(...orders) : Number.MAX_SAFE_INTEGER;
}

function tradeMetric(title: string): string {
  if (
    title.includes(TRADE_NET + TRADE_AMOUNT) ||
    title.includes(TRADE_IMPORT + TRADE_AMOUNT) ||
    title.includes(TRADE_EXPORT + TRADE_AMOUNT) ||
    title.includes(TRADE_IMPORT + "总额") ||
    title.includes(TRADE_EXPORT + "总额")
  ) {
    return TRADE_AMOUNT;
  }
  if (
    title.includes(TRADE_IMPORT) ||
    title.includes(TRADE_EXPORT) ||
    title.includes(TRADE_NET)
  ) {
    return TRADE_QTY;
  }
  return "";
}

function tradeCleanTitle(title: string): string {
  let s = title;
  const phrases = [
    TRADE_NET + TRADE_AMOUNT,
    TRADE_NET,
    TRADE_IMPORT + "总量",
    TRADE_EXPORT + "总量",
    TRADE_IMPORT + "总额",
    TRADE_EXPORT + "总额",
    TRADE_IMPORT + TRADE_QTY,
    TRADE_EXPORT + TRADE_QTY,
    TRADE_IMPORT + TRADE_AMOUNT,
    TRADE_EXPORT + TRADE_AMOUNT,
    TRADE_IMPORT,
    TRADE_EXPORT,
    "总计",
    "合计",
  ];
  for (const phrase of phrases) {
    s = s.split(phrase).join("");
  }
  // 频率词可能出现在标题中间（如"氯化锂月度进口量"），需删除所有位置，
  // 否则进口/出口/净出口的归组 key 不一致，无法放到同一行。
  for (const suffix of TRADE_FREQ_SUFFIXES) {
    s = s.split(suffix).join("");
  }
  // 数据侧偶见"中国海关: 中国金属锂进口量"这类产品名前冗余"中国"，
  // 与净出口"中国海关 金属锂净出口"无法对齐，统一删除"海关后的中国"。
  s = s.replace(/(海关[：:\s]*)中国/g, "$1");
  // 机构前缀清理："中国海关: 锡锭出口" → "锡锭出口"（分组 key 与显示名一致）
  s = s.replace(/^中国海关[：:\s]*/, "");
  s = s.replace(/^海关[：:\s]*/, "");
  // 标题尾部可能用缩写频率，如"净出口-月"、"净出口-季"
  s = s.replace(new RegExp("[-—]\\s*[月季年](度)?$"), "");
  s = s.replace(/[\s：:_\-、]+/g, "");
  return s;
}

function tradeDisplayName(title: string): string {
  let s = title;
  const phrases = [
    TRADE_NET + TRADE_AMOUNT,
    TRADE_NET,
    TRADE_IMPORT + "总量",
    TRADE_EXPORT + "总量",
    TRADE_IMPORT + "总额",
    TRADE_EXPORT + "总额",
    TRADE_IMPORT + TRADE_QTY,
    TRADE_EXPORT + TRADE_QTY,
    TRADE_IMPORT + TRADE_AMOUNT,
    TRADE_EXPORT + TRADE_AMOUNT,
    TRADE_IMPORT,
    TRADE_EXPORT,
    "总计",
    "合计",
  ];
  for (const phrase of phrases) {
    s = s.split(phrase).join("");
  }
  for (const suffix of TRADE_FREQ_SUFFIXES) {
    s = s.split(suffix).join("");
  }
  // 同 tradeCleanTitle：删除"海关后的中国"冗余前缀 + 机构前缀
  s = s.replace(/(海关[：:\s]*)中国/g, "$1");
  s = s.replace(/^中国海关[：:\s]*/, "");
  s = s.replace(/^海关[：:\s]*/, "");
  // 标题尾部可能用缩写频率，如"净出口-月"、"净出口-季"
  s = s.replace(new RegExp("[-—]\\s*[月季年](度)?$"), "");
  s = s.replace(new RegExp("\\s*[：:]\\s*$"), "");
  s = s.replace(new RegExp("[-—]\\s*$"), "");
  s = s.replace(/_+/g, "");
  return s.trim();
}

function tradeKey(title: string): string {
  return tradeCleanTitle(title) + tradeMetric(title);
}

// 频率优先从标题提取：海关数据的 freq 字段可能为 daily（更新频率），
// 而标题统一标注统计口径"月度"，若用 chart.freq 会把标题同为"月度"的
// 进口/出口/净出口拆到不同行。标题无频率词时回退 chart.freq。
function titleFreq(title: string): string | null {
  const full = title.match(/(日度|周度|月度|季度|年度)/);
  if (full) return full[1];
  const abbr = title.match(/[-—]\s*([月季年])(度)?\s*$/);
  if (abbr) return abbr[1] + "度";
  return null;
}

// 进出口统一归组 key：同一产品 + 地区/国别维度 + 频率 + 量/额 的
// 进口、出口、净出口 返回相同 key。供导航分组（buildTradeSubGroups）
// 与行排布（chartGrouping.displayBlockKey）共用，保证两类分组一致。
export function tradeGroupKey(chart: { title?: string; freq?: string }): string | null {
  const key = tradeKey(chart.title || "");
  const freq = titleFreq(chart.title || "") || chart.freq || "";
  return key ? `trade:${freq}:${key}` : null;
}

function buildTradeSubGroups(raw: Record<string, IndustryChart[]>): IndustrySubGroup[] {
  const groups = new Map<string, { displayName: string; charts: IndustryChart[] }>();
  const importExportKeys = new Set<string>();
  const netCharts: IndustryChart[] = [];
  const withTradeTag = (chart: IndustryChart): IndustryChart => ({
    ...chart,
    displayBlockTag: `${tradeDisplayName(chart.title || "")}|${tradeMetric(chart.title || "")}`,
  });

  for (const charts of Object.values(raw)) {
    for (const chart of charts) {
      const key = tradeGroupKey(chart);
      if (!key) continue;
      if (chart.sub === TRADE_IMPORT || chart.sub === TRADE_EXPORT) {
        importExportKeys.add(key);
      }
      if (chart.sub === TRADE_NET) {
        netCharts.push(withTradeTag(chart));
      }
      if (!groups.has(key)) {
        groups.set(key, { displayName: tradeDisplayName(chart.title || ""), charts: [] });
      }
      groups.get(key)!.charts.push(withTradeTag(chart));
    }
  }

  for (const chart of netCharts) {
    const key = tradeGroupKey(chart);
    if (!key || importExportKeys.has(key)) continue;
    const metric = tradeMetric(chart.title || "");
    const altKey =
      `trade:${titleFreq(chart.title || "") || chart.freq || ""}:` +
      tradeCleanTitle(chart.title || "") +
      (metric === TRADE_QTY ? TRADE_AMOUNT : TRADE_QTY);
    if (importExportKeys.has(altKey) && groups.has(altKey)) {
      const source = groups.get(key)!;
      groups.get(altKey)!.charts.push(...source.charts);
      groups.delete(key);
    }
  }

  return [...groups.values()]
    .map((group) => ({
      sub: group.displayName,
      title: `${group.displayName}进出口与净出口图`,
      charts: [...group.charts].sort(
        (a, b) =>
          orderIdx(TRADE_SUB_ORDER, a.sub || "") -
          orderIdx(TRADE_SUB_ORDER, b.sub || ""),
      ),
    }))
    .sort((a, b) => minCatalogOrder(a.charts) - minCatalogOrder(b.charts));
}

const PRICE_MAJOR = "价格";
const COMPOSITE_SUBS = [
  "成交量",
  "成交",
  "持仓",
  "持仓量",
  "成交持仓比",
];
const COMPOSITE_SUB_ORDER = [
  "成交量",
  "成交",
  "持仓",
  "持仓量",
  "成交持仓比",
];
const COMPOSITE_TITLE = "成交持仓";

// 成交持仓复合组标题追加合约标识："成交持仓-主力合约" / "成交持仓-01合约"；
// 无合约标识时保持"成交持仓"
function contractTagOf(displayName: string): string {
  const t = displayName || "";
  const m = t.match(
    /(主力合约|当月合约|(?:十一|十二|十|[一二三四五六七八九])月合约|\d{1,2}合约|连[一二三四五六七八九十\d]+合约)/,
  );
  return m ? `-${m[1]}` : "";
}
const CHINESE_MONTH_NUMBERS: Record<string, string> = {
  "一月": "01",
  "二月": "02",
  "三月": "03",
  "四月": "04",
  "五月": "05",
  "六月": "06",
  "七月": "07",
  "八月": "08",
  "九月": "09",
  "十月": "10",
  "十一月": "11",
  "十二月": "12",
};

// 按长度降序替换（十一月/十二月 必须先于 一月/二月，否则会被 split 成"十01/十02"）
const MONTH_NUMBER_ENTRIES = Object.entries(CHINESE_MONTH_NUMBERS).sort(
  (a, b) => b[0].length - a[0].length,
);

function cleanCompositeTitle(title: string): string {
  let s = title;
  for (const phrase of [
    "成交持仓比",
    "成交量",
    "持仓量",
  ]) {
    s = s.split(phrase).join("");
  }
  for (const prefix of ["SHFE:", "GFEX:", "DCE:", "CZCE:", "INE:"]) {
    s = s.split(prefix).join("");
  }
  for (const [cn, num] of MONTH_NUMBER_ENTRIES) {
    s = s.split(cn).join(num);
  }
  s = s.replace(
    new RegExp("[：:]\\s*(日度|周度|月度|季度|年度)$"),
    "",
  );
  s = s.replace(new RegExp("[-—]\\s*月(度)?$"), "");
  s = s.replace(/[\s：:_\-、]+/g, "");
  return s;
}

function compositeDisplayName(title: string): string {
  let s = title;
  for (const phrase of [
    "成交持仓比",
    "成交量",
    "持仓量",
  ]) {
    s = s.split(phrase).join("");
  }
  for (const prefix of ["SHFE:", "GFEX:", "DCE:", "CZCE:", "INE:"]) {
    s = s.split(prefix).join("");
  }
  for (const [cn, num] of MONTH_NUMBER_ENTRIES) {
    s = s.split(cn).join(num);
  }
  s = s.replace(
    new RegExp("[：:]\\s*(日度|周度|月度|季度|年度)$"),
    "",
  );
  s = s.replace(new RegExp("[-—]\\s*月(度)?$"), "");
  s = s.replace(new RegExp("\\s*[：:]\\s*$"), "");
  s = s.replace(new RegExp("[-—]\\s*$"), "");
  return s.trim();
}

// 合约系列排名（导航分组与行排布一致）：主力 -> 当月 -> 一月/二月/…/十二月（含 01/连X 数字）
const CONTRACT_CN_NUM: Record<string, number> = {
  "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
  "六": 6, "七": 7, "八": 8, "九": 9,
  "十": 10, "十一": 11, "十二": 12,
};

export function contractRankOfTitle(title: string): number {
  const t = title || "";
  if (t.includes("主力合约")) return 0;
  if (t.includes("当月合约")) return 1;
  const cn = t.match(/(十一|十二|十|[一二三四五六七八九])月合约/);
  if (cn) return CONTRACT_CN_NUM[cn[1]] ?? 99;
  const num = t.match(/(\d{1,2})合约/);
  if (num) return parseInt(num[1], 10);
  const lian = t.match(/连(十一|十二|十|[一二三四五六七八九])合约/);
  if (lian) return CONTRACT_CN_NUM[lian[1]] ?? 99;
  return 99;
}

// 去掉合约标识后的产品名（用于判断同一合约系列）
export function contractBaseName(title: string): string {
  return title
    .replace(/(主力|当月|连[一二三四五六七八九十]+|[一二三四五六七八九十]+月|\d{1,2})合约/g, "")
    .replace(/[\s：:_\-、]+/g, "");
}

function buildVolumeOiSubGroups(raw: Record<string, IndustryChart[]>): IndustrySubGroup[] {
  const groups = new Map<string, { displayName: string; charts: IndustryChart[] }>();

  for (const charts of Object.values(raw)) {
    for (const chart of charts) {
      if (!COMPOSITE_SUBS.includes(chart.sub || "")) continue;
      const key = cleanCompositeTitle(chart.title || "");
      if (!key) continue;
      if (!groups.has(key)) {
        groups.set(key, { displayName: compositeDisplayName(chart.title || ""), charts: [] });
      }
      groups.get(key)!.charts.push(chart);
    }
  }

  return [...groups.values()]
    .map((group) => ({
      sub: group.displayName,
      title: `${COMPOSITE_TITLE}${contractTagOf(group.displayName)}`,
      composite: true,
      charts: [...group.charts].sort(
        (a, b) =>
          orderIdx(COMPOSITE_SUB_ORDER, a.sub || "") -
          orderIdx(COMPOSITE_SUB_ORDER, b.sub || ""),
      ),
    }))
    .sort((a, b) => {
      // 同一产品（去掉合约标识后同名）内合约系列优先：主力 -> 当月 -> 一月/五月…
      const baseA = contractBaseName(a.sub);
      const baseB = contractBaseName(b.sub);
      if (baseA === baseB) {
        const contractA = contractRankOfTitle(a.sub);
        const contractB = contractRankOfTitle(b.sub);
        if (contractA !== contractB) return contractA - contractB;
      }
      return minCatalogOrder(a.charts) - minCatalogOrder(b.charts);
    });
}

function allChartsInMajor(raw: Record<string, IndustryChart[]>): IndustryChart[] {
  return Object.values(raw).flat();
}

export function buildIndustryGroups(
  charts: IndustryChart[],
  confidenceThreshold: number,
): IndustryGroup[] {
  const sorted = [...charts]
    .filter((c) => (c.confidence ?? 0) >= confidenceThreshold)
    .sort(
      (a, b) =>
        (a.catalogOrder ?? Number.MAX_SAFE_INTEGER) -
        (b.catalogOrder ?? Number.MAX_SAFE_INTEGER),
    )
    .map((c) =>
      // 磷化工链并入磷酸铁锂板块（数据侧 Excel 拆分、展示侧合并，用户确认）：
      // 归一化 sector 字段使分组标题、行合并边界（sectionKey）一致
      c.sector === "磷化工链" ? { ...c, sector: "磷酸铁锂" } : c,
    );
  // 一级改为板块（major 字段复用为板块名），二级为子类（跨大类收集），
  // 频率/行排布规则不变。大类（价格/供给…）不再单独成层。
  const bySector = new Map<string, IndustryChart[]>();
  for (const c of sorted) {
    const sector = c.sector || "其他";
    if (!bySector.has(sector)) bySector.set(sector, []);
    bySector.get(sector)!.push(c);
  }

  const sectorOrder = detectSectorOrder(charts);
  const sectorRankIn = (s: string) => {
    // 归一化后查表（碳酸锂/氢氧化锂/其他锂盐 → 锂盐），使锂盐拆分板块归位到
    // 锂矿之后；与 groupChartRows 的 sectorRankOf 一致，避免拆分板块被排到
    // 板块列表末尾（SECTOR_ORDER 只有"锂盐"，未归一化时 indexOf 返回 -1）
    const normalized = SECTOR_ALIASES[s] ?? s;
    const idx = sectorOrder.indexOf(normalized);
    return idx >= 0 ? idx : sectorOrder.length;
  };
  return [...bySector.keys()]
    .sort((a, b) => {
      const rankA = sectorRankIn(a);
      const rankB = sectorRankIn(b);
      if (rankA !== rankB) return rankA - rankB;
      // 同板块 rank（锂盐拆分为 碳酸锂/氢氧化锂/其他锂盐）：按板块名排序
      //（碳酸锂板块 < 氢氧化锂板块；不能按标题词，价差类标题会含对方产品词）
      const prodA = SECTOR_PROD_RANK[a] ?? Number.MAX_SAFE_INTEGER;
      const prodB = SECTOR_PROD_RANK[b] ?? Number.MAX_SAFE_INTEGER;
      if (prodA !== prodB) return prodA - prodB;
      return minCatalogOrder(bySector.get(a)!) - minCatalogOrder(bySector.get(b)!);
    })
    .map((sector) => {
      const sectorCharts = bySector.get(sector)!;
      // 板块内按大类分组（内部处理进出口/成交持仓复合组）
      const byMajor: Record<string, Record<string, IndustryChart[]>> = {};
      for (const c of sectorCharts) {
        const major = c.major || "其他";
        const sub = c.sub || "其他";
        if (!byMajor[major]) byMajor[major] = {};
        if (!byMajor[major][sub]) byMajor[major][sub] = [];
        byMajor[major][sub].push(c);
      }
      // 板块内子类收集（跨大类），同名子类合并
      const subMap = new Map<string, IndustrySubGroup>();
      const pushSubs = (list: IndustrySubGroup[]) => {
        for (const s of list) {
          const existing = subMap.get(s.sub);
          if (existing) {
            existing.charts.push(...s.charts);
          } else {
            subMap.set(s.sub, { ...s, charts: [...s.charts] });
          }
        }
      };
      for (const [major, subCharts] of Object.entries(byMajor)) {
        if (major === TRADE_MAJOR) {
          pushSubs(buildTradeSubGroups(subCharts));
        } else if (major === PRICE_MAJOR) {
          const composite = buildVolumeOiSubGroups(subCharts);
          const regular = Object.keys(subCharts)
            .filter((sub) => !COMPOSITE_SUBS.includes(sub))
            .map((sub) => ({ sub, charts: subCharts[sub] }));
          pushSubs([...regular, ...composite]);
        } else {
          pushSubs(
            Object.keys(subCharts).map((sub) => ({ sub, charts: subCharts[sub] })),
          );
        }
      }
      // 子类排序（板块内）：固定顺序（现货价格->…->价差）+ 其他子类按 minOrder
      const subs = sortSubsBySector([...subMap.values()]);
      return { major: sector, subs };
    });
}

// 子类显示名映射（不改分组 key/导航锚点，仅改界面文字）：
// 数据侧子类"指数"（价格类末尾，如各价格指数）显示为"价格指数"更明确
const SUB_DISPLAY_OVERRIDES: Record<string, string> = {
  "指数": "价格指数",
};

export function subDisplayName(sub: string): string {
  return SUB_DISPLAY_OVERRIDES[sub] ?? sub;
}

// 板块顺序（锂电产业链总览）：子类排序时优先按板块顺序，没有的板块跳过
const SECTOR_ORDER = [
  "锂矿",
  "锂盐",
  "磷酸铁锂",
  "三元正极",
  "钴酸锂",
  "锰酸锂",
  "负极材料",
  "隔膜",
  "电解液产业链",
  "辅材",
  "电池电芯",
  "储能",
  "新能源汽车",
];

// 锡板块顺序（总览精确产业链顺序）：锡矿（采选）→ 锡锭（冶炼）→ 锡材（加工）
// → 铅蓄电池/镀锡板（下游应用）→ 锡下游 → 锡期货（衍生品）→ 锡其他（杂项殿后）
const TIN_SECTOR_ORDER = [
  "锡矿", "锡锭", "锡材", "铅蓄电池", "镀锡板", "锡下游", "锡期货", "锡其他",
];

// 硅板块顺序：硅石石英砂/硅基原料（上游原料）→ 工业硅（冶炼）→ 有机硅（旁支）
// → 多晶硅（提纯）→ 硅片 → 电池片 → 组件 → 光伏辅材（旁支）→ 铝合金 → 下游需求
const SILICON_SECTOR_ORDER = [
  "硅石石英砂", "硅基原料", "工业硅", "有机硅", "多晶硅", "硅片",
  "电池片", "组件", "光伏辅材", "铝合金", "下游需求",
];

// 按 charts 的板块集合自动识别数据源（锡/硅/锂电），返回对应产业链顺序表
function detectSectorOrder(charts: IndustryChart[]): string[] {
  const sectors = new Set<string>();
  for (const c of charts) if (c.sector) sectors.add(c.sector);
  if ([...sectors].some((s) => TIN_SECTOR_ORDER.includes(s))) return TIN_SECTOR_ORDER;
  if ([...sectors].some((s) => SILICON_SECTOR_ORDER.includes(s))) return SILICON_SECTOR_ORDER;
  return SECTOR_ORDER;
}

// 数据侧板块名与展示板块不一致时统一映射：
// - "锂盐"被拆为 碳酸锂/氢氧化锂/其他锂盐 → 归回"锂盐"位置
// - "磷化工链"（磷矿/磷酸/磷酸铁等）→ 归入"磷酸铁锂"板块
const SECTOR_ALIASES: Record<string, string> = {
  "碳酸锂": "锂盐",
  "氢氧化锂": "锂盐",
  "其他锂盐": "锂盐",
  "磷化工链": "磷酸铁锂",
};

// 同板块 rank 内（锂盐拆分的板块）：碳酸锂板块 < 氢氧化锂板块 < 其他锂盐
const SECTOR_PROD_RANK: Record<string, number> = {
  "碳酸锂": 0,
  "氢氧化锂": 1,
  "其他锂盐": 2,
};

// 板块排名：不在列表或未标注的板块排最后
export function sectorRankOf(sector: string | undefined): number {
  const normalized = SECTOR_ALIASES[sector || ""] ?? (sector || "");
  const idx = SECTOR_ORDER.indexOf(normalized);
  return idx >= 0 ? idx : SECTOR_ORDER.length;
}

// 锂盐拆分板块内排名（碳酸锂 < 氢氧化锂 < 其他锂盐），与 SECTOR_PROD_RANK 一致；
// 供行排布（groupChartRows）在归一化后同板块 rank 内再按拆分子板块分开，
// 避免碳酸锂/氢氧化锂/其他锂盐混排（氯化锂 catalogOrder 小会被排到锂矿区）。
// 非拆分板块返回 0，不影响同 rank 内其他板块的相对顺序。
export function sectorSplitRankOf(sector: string | undefined): number {
  return SECTOR_PROD_RANK[sector || ""] ?? 0;
}

// 大类显式顺序（总览与板块页统一）：价格 -> 成本利润 -> 库存 -> 供给 -> 需求，其他排最后
const MAJOR_ORDER = ["价格", "成本利润", "库存", "供给", "需求"];

export function majorRankOf(major: string | undefined): number {
  const idx = MAJOR_ORDER.indexOf(major || "");
  return idx >= 0 ? idx : MAJOR_ORDER.length;
}

// 产品级排序（同板块内）：碳酸锂在氢氧化锂前；磷酸铁 -> 磷酸铁锂 -> 磷酸锰铁锂。
// 判定顺序：先匹配更长/更具体的产品名（磷酸锰铁锂/磷酸铁锂 含"磷酸铁"子串需先排除）。
export function productRankOf(title: string | undefined): number {
  const t = title || "";
  // 电解液用途词误判排除："电解液（磷酸铁锂用）"是电解液（用途=磷酸铁锂电池），
  // 不是磷酸铁锂产品；含"电解液"的标题一律不参与 碳酸锂/磷酸铁锂 等产品 rank
  if (t.includes("电解液")) return Number.MAX_SAFE_INTEGER;
  if (t.includes("碳酸锂")) return 0;
  if (t.includes("氢氧化锂")) return 1;
  if (t.includes("磷酸锰铁锂")) return 4;
  if (t.includes("磷酸铁锂")) return 3;
  if (t.includes("磷酸铁")) return 2;
  return Number.MAX_SAFE_INTEGER;
}

// 产品标题词表（按标题关键词匹配，先长后短；用于总览行业数据每行的产品标题）
const PRODUCT_LABEL_RULES: [string, string][] = [
  // 碳酸锂成本/利润族优先于原料词（产业链视角）：
  // "碳酸锂现金生产成本: 外购磷酸铁锂极片黑粉" 是碳酸锂成本（原料=磷酸铁锂黑粉），
  // 不应标"磷酸铁锂"；同族指标统一标题为 碳酸锂成本/碳酸锂利润，
  // 原料路线（三元黑粉/磷酸铁锂黑粉/锂云母精矿/锂辉石精矿…）保留在各卡片小标题
  ["碳酸锂现金生产成本", "碳酸锂成本"],
  ["碳酸锂现金生产利润", "碳酸锂利润"],
  ["碳酸锂生产利润", "碳酸锂利润"],
  ["碳酸锂进口利润", "碳酸锂利润"],
  ["碳酸锂理论交割利润", "碳酸锂利润"],
  // 电芯类型词优先于产品词（"动力电芯产量: 三元"应标"动力电芯"而非"三元电芯"）；
  // 不加"储能电芯"——避免"280Ah磷酸铁锂储能电芯"被误标（应保持"磷酸铁锂电芯"）
  ["动力电芯", "动力电芯"],
  ["消费电芯", "消费电芯"],
  ["锂辉石精矿", "锂辉石精矿"],
  ["锂云母精矿", "锂云母精矿"],
  ["磷锂铝石", "磷锂铝石"],
  ["锂矿", "锂矿"],
  ["六氟磷酸锂", "六氟磷酸锂"],
  ["氟化锂", "氟化锂"],
  // 电解液系列（含"电解液（磷酸铁锂用）"等专用电解液）统一标"电解液"，须在正极词前
  ["电解液", "电解液"],
  ["磷酸锰铁锂", "磷酸锰铁锂"],
  ["磷酸铁锂", "磷酸铁锂"],
  ["磷酸铁", "磷酸铁"],
  // 锂盐词须在"三元系"前：否则"氢氧化锂样本库存: 下游三元材料厂"会误标"三元材料"
  //（"下游三元材料厂"是客户维度而非产品）；"电池级氢氧化锂与电池级碳酸锂价差"
  // 仍按碳酸锂（碳酸锂在前）不变
  ["碳酸锂", "碳酸锂"],
  // "锂辉石"裸词：须在碳酸锂后（"锂辉石矿生产碳酸锂…"类成本指标应标"碳酸锂"），
  // 且须在氢氧化锂前（"锂辉石-氢氧化锂生产成本"属锂辉石系列，不应标"氢氧化锂"）；
  // "锂辉石精矿"已在上方优先匹配
  ["锂辉石", "锂辉石"],
  ["氢氧化锂", "氢氧化锂"],
  ["金属锂", "金属锂"],
  ["氯化锂", "氯化锂"],
  ["硫化锂", "硫化锂"],
  ["氧化锂", "氧化锂"],
  ["硫酸锂", "硫酸锂"],
  ["三元前驱体", "三元前驱体"],
  ["三元材料", "三元材料"],
  ["三元", "三元"],
  ["钴酸锂", "钴酸锂"],
  ["锰酸锂", "锰酸锂"],
  ["人造石墨", "人造石墨"],
  ["天然石墨", "天然石墨"],
  ["鳞片石墨", "鳞片石墨"],
  ["球形石墨", "球形石墨"],
  ["石油焦", "石油焦"],
  ["针状焦", "针状焦"],
  ["石墨化", "石墨化"],
  ["基膜", "基膜"],
  ["隔膜", "隔膜"],
  ["铜箔", "铜箔"],
  ["铝箔", "铝箔"],
  ["PVDF", "PVDF"],
  ["电芯", "电芯"],
  ["Pack", "Pack"],
  ["储能", "储能"],
  ["PCS", "PCS"],
  ["新能源汽车", "新能源汽车"],
  ["新能源车", "新能源汽车"],
  ["整车", "整车"],
  ["汽车", "汽车"],
];

const FREQ_CN: Record<string, string> = {
  daily: "日度",
  weekly: "周度",
  monthly: "月度",
  quarterly: "季度",
  yearly: "年度",
};

// 从图标题提取产品标签（用于行标题）；无匹配返回 null。
// 标题含"电芯/Pack/电池"等形态词时追加到标签
// （方形磷酸铁锂电芯 -> 磷酸铁锂电芯、方形磷酸铁锂电池 -> 磷酸铁锂电池），
// 并追加指标频率（钴酸锂电芯 -> 钴酸锂电芯-日度）。标题无频率词时回退 chart.freq，
// 避免同一行内（如成交持仓复合组"碳酸锂主力合约成交持仓比"无频率词）标签不一致
// 导致"碳酸锂-日度 ｜ 碳酸锂"重复并列。
export function productLabelOf(title: string | undefined, freq?: string): string | null {
  const t = title || "";
  for (const [keyword, label] of PRODUCT_LABEL_RULES) {
    if (t.includes(keyword)) {
      let result = label;
      // 形态词判定排除等级词："电池级/电芯级"（如"电池级碳酸锂"）不是电池/电芯产品；
      // 排除成本/利润族（"碳酸锂现金生产成本: 外购磷酸铁锂电池黑粉"中的"电池"是回收料
      // 原料描述，不应追加成"碳酸锂成本电池"）
      if (t.includes("电芯") && !result.includes("电芯") && !t.includes("电芯级")) result += "电芯";
      if (t.includes("Pack") && !result.includes("Pack")) result += "Pack";
      if (t.includes("电池") && !result.includes("电池") && !result.includes("电芯") && !t.includes("电池级") && !result.includes("成本") && !result.includes("利润")) result += "电池";
      const freqMatch = t.match(/(日度|周度|月度|季度|年度)/);
      const freqLabel = freqMatch ? freqMatch[1] : (freq ? FREQ_CN[freq] : null);
      if (freqLabel) result += "-" + freqLabel;
      return result;
    }
  }
  return null;
}

// 子类板块归属 = 子类内最小板块序号（子类可能跨多个板块，如"现货价格"含锂矿/三元/碳酸锂等）
function subSectorRank(charts: IndustryChart[]): number {
  let min = SECTOR_ORDER.length;
  for (const c of charts) {
    const rank = sectorRankOf(c.sector);
    if (rank < min) min = rank;
  }
  return min;
}

// 子类固定顺序（与数据侧 sort_catalog.SUB_ORDER 保持一致）：
// 价格大类：现货价格 -> 贸易金额 -> 期货价格 -> 现货价差 -> 价差 -> 基差 -> 月差 -> 指数
const PRICE_SUB_ORDER = [
  "现货价格", "贸易金额", "期货价格", "现货价差",
  "价差", "基差", "月差", "指数",
];

function subRankOf(sub: string): number {
  const idx = PRICE_SUB_ORDER.indexOf(sub);
  return idx >= 0 ? idx : PRICE_SUB_ORDER.length;
}

function sortSubsBySector(subs: IndustrySubGroup[]): IndustrySubGroup[] {
  return [...subs].sort((a, b) => {
    const rankA = subSectorRank(a.charts);
    const rankB = subSectorRank(b.charts);
    if (rankA !== rankB) return rankA - rankB;
    // 同板块：子类固定顺序（期货价格在价差前，与数据侧 SUB_ORDER 一致）
    const subA = subRankOf(a.sub);
    const subB = subRankOf(b.sub);
    if (subA !== subB) return subA - subB;
    // 同板块同子类：产品 rank（碳酸锂在氢氧化锂前、磷酸铁在磷酸锰铁锂前）
    const prodA = Math.min(...a.charts.map((c) => productRankOf(c.title)));
    const prodB = Math.min(...b.charts.map((c) => productRankOf(c.title)));
    if (prodA !== prodB) return prodA - prodB;
    // 同板块同产品：同一产品（去掉合约标识后同名）内合约系列优先（主力 -> 当月 -> 一月/五月…），
    // 保持 buildVolumeOiSubGroups 的合约顺序，否则会被 minCatalogOrder 重新打乱
    const baseA = contractBaseName(a.sub);
    const baseB = contractBaseName(b.sub);
    if (baseA === baseB) {
      const contractA = contractRankOfTitle(a.sub);
      const contractB = contractRankOfTitle(b.sub);
      if (contractA !== contractB) return contractA - contractB;
    }
    return minCatalogOrder(a.charts) - minCatalogOrder(b.charts);
  });
}
