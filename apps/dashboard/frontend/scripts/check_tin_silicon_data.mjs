import fs from "node:fs";
import path from "node:path";

// 用 python 检查 xlsx 更可靠，这里只做路径确认
const root = path.resolve("..");
for (const f of ["锡产业链数据_workflow_ai.xlsx", "硅产业链数据_workflow_ai.xlsx"]) {
  const p = path.join(root, "data", f);
  console.log(f, "| exists:", fs.existsSync(p), fs.existsSync(p) ? `| ${fs.statSync(p).size} bytes | ${fs.statSync(p).mtime.toISOString()}` : "");
}
