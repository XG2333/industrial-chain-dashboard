// 速评数值分段着色：与页面行情配色一致（涨红跌绿）。
// 识别两种结构, 整段着色:
//   A) 方向词/符号在数字前: "跌0.69%" "日增+1,905手" "-0.85%" "回撤16.2%"
//   B) 数字在方向词前(涨跌只数统计): "8涨11跌" → 8涨红、11跌绿
// 支持千位逗号与 %/万/亿/手 单位; 无涨跌语义的数值(现价/分位)保持黑色。
// 注意: 连字符必须放字符类末尾([+−-])。

const NUM = "\\d[\\d,]*(?:\\.\\d+)?(?:%|万|亿|手)?";
const DIR1 = "(?:增|减|涨|跌|升|降|回撤)";
const TIME = "(?:日|周|月|年)?";
// A 前缀: 词与符号至少出现其一(不允许空前缀, 避免把裸数字单独抠出)
//   (词可选+符号必有) | (词必有, 符号可无), 时间字可置于词前
const PRE_A = `(?:${TIME}(?:${DIR1})?[+−-]|${TIME}(?:${DIR1})|${TIME}[+−-])`;
const TOKEN_RE = new RegExp(
  `(${NUM})(${DIR1})|(${PRE_A})(\\s*${NUM})`,
  "g",
);

export interface ChangeSegment {
  text: string;
  cls: string;
}

const TIME_CHARS = new Set(["日", "周", "月", "年"]);

// 剥离段首时间字(日/周/月/年): 时间字本身不着色, 只给后面的方向+数值上色
function splitTimeChar(raw: string): { head: string; body: string } {
  const c = raw[0];
  if (TIME_CHARS.has(c)) return { head: c, body: raw.slice(1) };
  return { head: "", body: raw };
}

export function colorParts(change: string): ChangeSegment[] {
  const out: ChangeSegment[] = [];
  let last = 0;
  for (const m of change.matchAll(TOKEN_RE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ text: change.slice(last, idx), cls: "" });
    if (m[1] != null) {
      // 形态 B: 数字在前, 方向词在后 → 数字与词整体按方向着色(涨红/跌绿)
      const word = m[2];
      const green = /(跌|降|减|回撤)/.test(word);
      const { head, body } = splitTimeChar(m[0]);
      if (head) out.push({ text: head, cls: "" });
      out.push({ text: body, cls: green ? "text-green-600" : "text-red-600" });
    } else {
      // 形态 A: 方向词/符号在数字前
      const raw = m[0];
      const pre = (m[3] || "").replace(/−/g, "-");
      const neg = pre.includes("-") || /(跌|降|减|回撤)/.test(pre);
      const pos = pre.includes("+") || /(涨|升|增)/.test(pre);
      const { head, body } = splitTimeChar(raw);
      if (head) out.push({ text: head, cls: "" });
      out.push({ text: body, cls: neg ? "text-green-600" : pos ? "text-red-600" : "" });
    }
    last = idx + m[0].length;
  }
  if (last < change.length) out.push({ text: change.slice(last), cls: "" });
  return out.length ? out : [{ text: change, cls: "" }];
}
