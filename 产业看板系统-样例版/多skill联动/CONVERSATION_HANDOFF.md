# 对话交接记录

## 来源

- 原始 Codex 对话发生在 `C:\Users\11\Documents\Selecting skill`
- 对话目标：把 Skill1-Skill4 串成一个统一 workflow
- 本文件用于把这次对话的上下文迁移到 `C:\Users\11\Documents\多skill联动`

Codex 线程本身不能直接改绑到另一个项目目录；这份交接记录承担项目侧迁移。

## 已确认的 Skill 工作内容

### Skill1：excel-catalog-curator

项目：`C:/Users/11/Documents/market-ai-dashboard`

- 扫描 Excel 数据 Sheet
- 按第 1 行指标名、第 2 行单位、第 3 行频率、第 4 行起时间序列识别
- 在第一个 Sheet 生成完整目录
- 生成 `dataset.pkl`

### Skill2：financial-variable-curation

项目：`C:/Users/11/Documents/Selecting skill`

- `directory-mark`：检查、持久化、分类、规则编译、筛选、目录标记
- 净出口计算：对齐日期后补齐缺失净出口
- 产业确定性筛选：锂电/锡/硅分别覆盖最终 `是否选中`

### Skill3：stock-target-curator

- 读取 `config/stock_targets.json` 中人工维护的种子股票池
- 生成硅、锡、锂电池产业链的 `个股标的` 表

### Skill4：dashboard-data-sorter

- 对 `指标目录` sheet 按 `排序规则.md` 重排
- 最终输出后再次执行，确保筛选/AI 后新增行也保持排序

## 统一 workflow 顺序

```text
新 Excel
→ Skill1 目录生成
→ Skill2 directory-mark
→ 净出口计算
→ Skill3 个股标的生成
→ Skill4 看板排序
→ 产业校准 / 频率校验 / 分类检查
→ 产业确定性筛选
→ AI 辅助判断（可选）
→ 最终筛选
→ 最终 Skill4 看板排序
→ 最终 Excel
```

顺序定义在：

```text
configs/workflow.yaml
```

## 已实现文件

```text
workflow/
  __init__.py
  __main__.py
  cli.py
  config.py
  runners.py
configs/workflow.yaml
tests/test_workflow.py
docs/multi_skill_workflow.md
README.md
```

## 验证结果

- `pytest` 全部通过
- 新增 workflow 端到端测试通过
- 用 `C:/Users/11/Documents/Selecting skill/data/business_data_test.xlsx` 全量 mock 冒烟通过
- 最新冒烟结果：工作簿 79 个 Sheet、Skill1 识别 77 个数据 Sheet / 1034 条指标、最终目录选中 172 条、净出口计算 5 对指标
- 最新运行：`workflow_runs/20260805T025651Z_10d97042ae6e`
- 最新最终文件：`output/workflow_smoke.xlsx`

## 硅产业链指标标签新增

- 目的：在不扩展树状层级的前提下，为每条指标生成独立的 `指标标签` 维度。
- 规则文档：`rules/silicon_indicator_tags_rules.md`
- 执行脚本：`scripts/apply_indicator_tags.py`
- workflow：`configs/workflow_silicon.yaml` 已加入 `apply_indicator_tags` 步骤
- 输出列：`指标标签`，JSON 对象，包含 产品/研究主题/指标类型/规格/工艺属性/地域/统计口径/状态/频率
- 最新硅产业链文件：`output/硅产业链数据_processed_tagged.xlsx`
- 验证：2360 条指标全部有标签，标签审计 0 问题，最终检查 0 问题

## 后续扩展方式

1. 在 `configs/workflow.yaml` 的 `steps` 中追加新 skill。
2. 若无现成 runner，在 `workflow/runners.py` 注册新 runner。
3. 现有内置 runner：

```text
excel_catalog_curator
financial_variable_directory_mark
net_export_calculator
tin_selection_rules
reclassify_directory
copy_file
command
stock_target_curator
dashboard_data_sorter
```
