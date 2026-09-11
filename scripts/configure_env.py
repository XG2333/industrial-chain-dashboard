# -*- coding: utf-8 -*-
"""生成并配置 apps/dashboard/.env：
- 不存在时从 .env.example 复制
- 写入仓库的数据、股票池与缓存目录
- 清空 WORKFLOW_CURRENT_PATH（不依赖 workflow 发布）
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASH = ROOT / "apps" / "dashboard"
ENV = DASH / ".env"


def main() -> int:
    if not DASH.exists():
        print(f"[configure_env] 未找到看板目录: {DASH}", flush=True)
        return 1
    example = DASH / ".env.example"
    if not ENV.exists():
        if example.exists():
            ENV.write_bytes(example.read_bytes())
        else:
            ENV.write_text("", encoding="utf-8")
        print(f"[configure_env] 已从 .env.example 生成 .env", flush=True)

    content = ENV.read_text(encoding="utf-8")
    lines = [
        ln for ln in content.splitlines()
        if not ln.strip().startswith((
            "STOCK_TARGETS_DIR=",
            "DASHBOARD_DATA_DIR=",
            "DASHBOARD_CACHE_DIR=",
        ))
    ]
    stock_dir = (ROOT / "data" / "stock-targets").as_posix()
    data_dir = (ROOT / "data" / "processed").as_posix()
    cache_dir = (ROOT / "runtime" / "cache").as_posix()
    lines.append(f"STOCK_TARGETS_DIR={stock_dir}")
    lines.append(f"DASHBOARD_DATA_DIR={data_dir}")
    lines.append(f"DASHBOARD_CACHE_DIR={cache_dir}")
    content = "\n".join(lines) + "\n"
    content = re.sub(r"(?m)^WORKFLOW_CURRENT_PATH=.*$", "WORKFLOW_CURRENT_PATH=", content)
    ENV.write_text(content, encoding="utf-8")
    print(f"[configure_env] 已配置 {ENV}", flush=True)
    print(f"  STOCK_TARGETS_DIR={stock_dir}", flush=True)
    print(f"  DASHBOARD_DATA_DIR={data_dir}", flush=True)
    print(f"  DASHBOARD_CACHE_DIR={cache_dir}", flush=True)
    print(f"  WORKFLOW_CURRENT_PATH= (清空)", flush=True)
    if "DEEPSEEK_API_KEY=" in content and not re.search(r"(?m)^DEEPSEEK_API_KEY=\S+", content):
        print("  [提示] 看板「AI 分析」需要配置 DEEPSEEK_API_KEY：", flush=True)
        print("    请编辑 apps/dashboard/.env 填入你的 DeepSeek key 后重启看板", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
