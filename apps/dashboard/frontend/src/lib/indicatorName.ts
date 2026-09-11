// 指标名称简化（板块表格部分展示用）：
// 1. 删去结尾频率词（": 日度"/": 周度"等）；标题中间的频率字样是名称内容，保留
// 2. 删去指标词：平均价 / 收盘价 / 成交量 / 持仓量
// 3. 删去开头来源前缀：SMM / GFEX / SHFE / LME / 广期所 / 广期日库存 等
// 4. 清理删除后残留的分隔符（尾部冒号/连字符/空格）
const FREQ_SUFFIX_RE = /\s*[:：]?\s*(半月度|日度|周度|月度|季度|年度)\s*$/;
const REMOVE_WORDS = ["平均价", "收盘价", "成交量", "持仓量"];
const SOURCE_PREFIX_RE = /^\s*(?:SMM|GFEX|SHFE|LME|JFX|ICDX|广期所|广期日库存)\s*[:：]\s*/;

function cleanSeparators(text: string): string {
  return text
    .replace(/\s*[:：]\s*$/, "")
    .replace(/^\s*[:：]\s*/, "")
    .replace(/\s*[-—]\s*$/, "")
    .replace(/^\s*[-—]\s*/, "")
    .replace(/[\s:：,，。]+$/, "")
    .trim();
}

export function simplifyIndicatorName(title: string): string {
  let t = (title || "").replace(FREQ_SUFFIX_RE, "").trim();
  for (const word of REMOVE_WORDS) {
    t = t.split(word).join("");
  }
  t = t.replace(SOURCE_PREFIX_RE, "");
  return cleanSeparators(t);
}
