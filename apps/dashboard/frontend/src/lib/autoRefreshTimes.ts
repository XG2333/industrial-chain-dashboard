// 盘中自动刷新时点(交易日): 开盘后2分钟 → 整点/半点 → 收盘前2分钟。
// 自选股票 / 个股速评 / 截图工具共用同一份时间表。
export const INTRADAY_REFRESH_TIMES = [
  "09:32", "10:00", "10:30", "11:00", "11:30",
  "13:30", "14:00", "14:30", "14:58",
];

// 当前时刻若命中交易日时点, 返回该时点唯一 key(YYYY/M/D HH:MM, 用于去重); 否则返回 null
export function intradayDueKey(now: Date = new Date()): string | null {
  const dow = now.getDay();
  if (dow === 0 || dow === 6) return null; // 周末休市
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  if (!INTRADAY_REFRESH_TIMES.includes(hhmm)) return null;
  return `${now.getFullYear()}/${now.getMonth() + 1}/${now.getDate()} ${hhmm}`;
}
