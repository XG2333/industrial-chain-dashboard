# AGENTS.md

> 本文件是通用 coding agent 入口。项目全部稳定信息集中在同目录 `CLAUDE.md`，
> 本文件只做指针，不重复内容。

## 开始前必读（顺序）

1. `CLAUDE.md`：项目定位、环境、常用命令、不可破坏的不变量、source of truth
2. `migration/HANDOFF.md`：接管指南（Required Reading Order、禁止项、标准验证方式）
3. `migration/CURRENT_STATUS.md`：当前状态与 WIP（含活跃阻塞问题）

Claude Code 会自动加载 `CLAUDE.md`；Codex 等其他 agent 请显式读取上述文件。

## 硬性禁止（不随开发变化，其余见 CLAUDE.md / migration/HANDOFF.md）

- 禁止回退/丢弃未提交改动（它们是用户当前工作）
- 禁止重建 venv、升级依赖、升级 Python 版本
- 禁止删除 `data_input/`、`output/`、`workflow_runs/` 等业务产物
- 禁止提交 Git commit（除非用户要求）
- 具体业务规则以 `rules/*.md` 与 `scripts/*.py` 为准，不在本文件重复

## 迁移上下文

`migration/` 保留完整历史与证据链（PROJECT_OVERVIEW / ARCHITECTURE /
BUSINESS_RULES / DECISION_HISTORY / CURRENT_STATUS / ENVIRONMENT），
需要细节时再读，不要整份复制进会话。
