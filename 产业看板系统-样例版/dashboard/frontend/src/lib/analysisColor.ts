// 速评数值分段着色：与页面行情配色一致（涨红跌绿）。
// change 文本如 "38608手，日+3.3%，周+10.0%，月-5.9%" 会被切成多段：
// - 无符号的主数值/文字（如 "38608手"、逗号、"日"）→ cls 为空，继承正文颜色（与文字同色）
// - 带符号的涨跌段（如 "日+3.3%"、"+10.0%"、"-5.9%"）→ 涨红、跌绿（兼容 Unicode 减号 − 与 万/亿/手 单位）
// 注意: 连字符必须放字符类末尾([+−-]), 否则 [+-−] 会被解析成 "+到−" 的范围,
// 误匹配所有 ASCII 数字, 导致无符号主数值也被判红
const TOKEN_RE = /([日周月年]?[+−-]\s*\d+(?:\.\d+)?(?:%|万|亿|手)?)/g;

export interface ChangeSegment {
  text: string;
  cls: string;
}

export function colorParts(change: string): ChangeSegment[] {
  const out: ChangeSegment[] = [];
  let last = 0;
  for (const m of change.matchAll(TOKEN_RE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ text: change.slice(last, idx), cls: "" });
    const raw = m[1];
    const t = raw.replace(/−/g, "-");
    out.push({
      text: raw,
      cls: /-\s*\d/.test(t) ? "text-green-600" : "text-red-600",
    });
    last = idx + m[0].length;
  }
  if (last < change.length) out.push({ text: change.slice(last), cls: "" });
  return out.length ? out : [{ text: change, cls: "" }];
}
