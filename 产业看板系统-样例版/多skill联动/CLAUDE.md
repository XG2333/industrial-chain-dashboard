# CLAUDE.md

> 本项目会话级稳定信息。完整迁移历史在 `migration/`（先读 `migration/HANDOFF.md`）；
> 详细业务规则在 `rules/*.md` 与各 Skill 的 `SKILL.md` / `README.md`。

## 项目定位

`多skill联动` 是 Excel 产业链数据整理流水线：把锂电/锡/硅原始 Excel，经
Skill1 目录生成（外部 market-ai-dashboard）、Skill2 金融变量筛选（外部
Selecting skill）、Skill3 个股标的（本项目内）、Skill4 看板排序（本项目内），
以及净出口/复合指标/分类校准/指标标签/产业筛选/可选 AI 消歧等确定性步骤，
输出排序好的看板目录 Excel 与个股标的表。外部 skill 只调用不复制，路径被
config/脚本硬编码。

## 环境（禁止更改）

- 唯一解释器：`C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe`
  （Python 3.12，外部项目 venv，禁止重建/升级，禁止升级依赖）
- 外部依赖：market-ai-dashboard（Skill1）、Selecting skill（Skill2）、
  本地可视化dashboard（看板，排序规则同步对象）、Result_audit（影子审计）
- 不提交 Git commit（除非用户要求）；不删除 `data_input/`、`output/`、
  `workflow_runs/` 等业务产物

## 测试临时目录（可随时清理，勿长期保留）

- 全量测试命令的 `--basetemp=.pytest_tmp_<名字>` 会在项目根产生
  `.pytest_tmp_*` / `pytest_tmp_*`（无点变体）/ `.tmp_*` 目录：它们是
  pytest 运行残留（test_* 子目录 + 输入/输出 xlsx），非业务数据，**可随时
  整目录删除**；需要现场时重跑对应测试即可重建。
- 已全部加入 `.gitignore`（含无点变体），出现此类目录时先删后跑测试，
  不要留存多个命名副本。
- 不可删除清单不变：`data_input/`、`output/`、`workflow_runs/`、`.env`、
  `scripts/`、`rules/`、`skills/`、`configs/`、`workflow/`、`migration/`。

## 常用命令

```powershell
# 全量测试（需 PYTHONPATH；外部项目齐全时基线 160 passed）
$env:PYTHONPATH = "C:\Users\11\Documents\多skill联动\scripts"
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" -m pytest `
  tests skills\stock-target-curator\tests skills\dashboard-data-sorter\tests -q `
  -p no:cacheprovider --basetemp=.pytest_tmp_<名字>

# 完整产业 pipeline
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  scripts\run_industry_pipeline.py --industry lithium `
  --input data_input\碳酸锂数据库.xlsx --output output\xxx.xlsx [--ai] [--dry-run]
```

## 不可破坏的不变量（改前必读）

1. `scripts/*.py` 是规则执行真源，`rules/*.md` 是文档/审计依据，两者必须同一轮同步修改。
2. 分类采用"候选收集 + 确定性优先级 + AI 消歧"，不退回"命中即停止"。
3. 所有产业统一 `供给` 大类，保存前执行 `供应 → 供给` 归一化。
4. 进出口 `进口/出口/净出口` 选中数量必须相等，`apply_industry_selection.py`
   保存前硬校验，失败即中止。
5. Skill4 是唯一业务排序真源，排序后 invariant 校验失败必须报错，不能静默输出。
6. 目录列结构（含 `指标标签`）被多脚本按位置读取，不要增删列。
7. AI 只处理"其他/未识别/多候选/单位冲突"，结果必须落在候选范围内且有 SQLite 缓存。
8. 未提交改动是用户当前工作，禁止回退/丢弃；改代码必须同步对应 `rules/*.md`
   与 Skill 的 `SKILL.md` / `README.md`。

## Source of truth

- workflow 步骤：`configs/workflow*.yaml`；runner 注册：`workflow/runners.py` 的 `RUNNERS`
- 产业规则实现：`scripts/*.py`；规则文档：`rules/*.md`
- 看板排序：根目录 `排序规则.md` + `skills/dashboard-data-sorter/config/sector_node_rules.json`
- 股票池：`skills/stock-target-curator/config/stock_targets.json`

## 必读

- `migration/HANDOFF.md`：接管指南（Required Reading Order、First-session validation、禁止项）
- `migration/CURRENT_STATUS.md`：当前状态与 WIP（Skill4 真实锂电数据
  `NAME_GROUP_CONTIGUITY_VIOLATION` 失败是当前活跃阻塞；默认 `configs/workflow.yaml`
  的 `apply_tin_selection_rules` 步骤是坏步骤，未修复前不要用默认配置跑全量）
- `rules/README.md`：规则索引，含"规则与代码不一致"清单（第 4 节）
