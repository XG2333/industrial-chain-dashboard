# -*- coding: utf-8 -*-
"""生成并配置 本地可视化dashboard/.env：
- 不存在时从 .env.example 复制
- 写入 STOCK_TARGETS_DIR（指向本包 多skill联动/output）
- 清空 WORKFLOW_CURRENT_PATH（不依赖 workflow 发布）
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent  # 包根（脚本位于包根）
DASH = ROOT / "本地可视化dashboard"
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
        if not ln.strip().startswith("STOCK_TARGETS_DIR=")
    ]
    stock_dir = (ROOT / "多skill联动" / "output").as_posix()
    lines.append(f"STOCK_TARGETS_DIR={stock_dir}")
    content = "\n".join(lines) + "\n"
    content = re.sub(r"(?m)^WORKFLOW_CURRENT_PATH=.*$", "WORKFLOW_CURRENT_PATH=", content)
    ENV.write_text(content, encoding="utf-8")
    print(f"[configure_env] 已配置 {ENV}", flush=True)
    print(f"  STOCK_TARGETS_DIR={stock_dir}", flush=True)
    print(f"  WORKFLOW_CURRENT_PATH= (清空)", flush=True)
    if "DEEPSEEK_API_KEY=" in content and not re.search(r"(?m)^DEEPSEEK_API_KEY=\S+", content):
        print("  [提示] 看板「AI 分析」需要配置 DEEPSEEK_API_KEY：", flush=True)
        print("    请编辑 本地可视化dashboard/.env 填入你的 DeepSeek key 后重启看板", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
