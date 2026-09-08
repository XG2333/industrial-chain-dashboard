# 多skill联动

这是 `excel-catalog-curator` 与 `financial-variable-curation` 的统一编排项目。

项目保存 workflow 编排代码、配置和文档。Skill1、Skill2 通过
`configs/workflow.yaml` 指向外部 skill 项目，Skill3、Skill4 位于本项目内：

- Skill1：`C:/Users/11/Documents/market-ai-dashboard`
- Skill2：`C:/Users/11/Documents/Selecting skill`
- Skill3：`skills/stock-target-curator`
- Skill4：`skills/dashboard-data-sorter`

## 快速使用

从本项目目录执行：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" -m workflow `
  --input <新的Excel文件.xlsx>
```

常用参数：

```text
--provider mock|deepseek|openai
--rules input/selection_rules.docx
--output output/<名称>_final.xlsx
--dry-run
```

默认 `provider=mock`，完全离线。真实 DeepSeek 分类需要 `.env` 中
`REAL_LLM_ENABLED=true` 并配置对应 API Key。

## 目录

```text
configs/workflow.yaml
workflow/                 # 可扩展 workflow 运行器
skills/dashboard-data-sorter
skills/stock-target-curator
tests/test_workflow.py
docs/multi_skill_workflow.md
docs/CONVERSATION_HANDOFF.md
```

## 验证

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" -m pytest tests\test_workflow.py -q
```

如沙箱不允许写系统 Temp，可加：

```text
-p no:cacheprovider --basetemp=.pytest_tmp
```

## 统一入口

使用 `scripts/run_industry_pipeline.py` 可以一次完成：

1. Skill1 + Skill2 workflow（最后两步为 Skill3 个股标的生成、Skill4 看板数据排序）
2. 产业确定性校准
3. 可选 AI 辅助判断
4. 最终输出后再次执行 Skill4 看板数据排序
   - 最终目录会在 `Indicator Name` 右侧新增 `指标名称归一化` 列

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" scripts\run_industry_pipeline.py `
  --industry lithium `
  --input data_input\碳酸锂数据库.xlsx `
  --output output\碳酸锂数据库_workflow.xlsx `
  --ai
```

`--industry` 可选 `lithium`、`tin`、`silicon`；`--ai` 启用 AI 辅助判断；`--dry-run` 仅打印执行计划，不实际运行。

## 规则同步约定

本项目要求：每次修改 Python 脚本、JSON 配置或 workflow 配置后，必须同步更新对应 Skill 的 `SKILL.md`、`README.md` 或规则 md，包括：

- Skill1：`market-ai-dashboard/skills/excel-catalog-curator/SKILL.md`
- Skill2：`Selecting skill/SKILL.md`
- Skill3：`skills/stock-target-curator/SKILL.md` 与 `README.md`
- Skill4：`skills/dashboard-data-sorter/SKILL.md`、`README.md`、`排序规则.md`

md 是规则说明和审计依据，Python 脚本是实际执行入口；两者必须在同一轮修改中保持一致。

看板前端规则变更时，`本地可视化dashboard/docs/排序规则.md` 必须同步到本项目根目录
`排序规则.md`，并同步更新 Skill4 的 `SKILL.md`、`README.md`；涉及目录生成规则时同步
更新 `market-ai-dashboard/skills/excel-catalog-curator/SKILL.md`。
