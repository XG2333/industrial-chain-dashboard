# 多 Skill Excel 工作流

本目录是独立编排项目 `多skill联动`。Skill1、Skill2 通过
`configs/workflow.yaml` 指向现有 skill 项目，Skill3、Skill4 位于本项目内：

- `C:/Users/11/Documents/market-ai-dashboard`
- `C:/Users/11/Documents/Selecting skill`
- `C:/Users/11/Documents/多skill联动/skills/stock-target-curator`
- `C:/Users/11/Documents/多skill联动/skills/dashboard-data-sorter`

## 当前链路

这个工作流把已有 skill 串成一条流水线：

1. `excel-catalog-curator`（market-ai-dashboard）
   - 扫描 Excel 所有数据 Sheet
   - 识别指标名、单位、频率
   - 生成第一个 Sheet 的完整目录
   - 生成 `dataset.pkl` 数据包
2. `financial-variable-curation`（Selecting_skill）
   - `directory-mark` 完成检查、持久化、分类、规则编译、筛选
   - 把 `大类 / 子类 / 数据性质 / 是否选中 / 状态说明` 写回目录 Sheet，最终输出不保留置信度列
3. 净出口计算
   - 通用脚本 `scripts/calculate_net_exports.py`
   - 对已有进出口指标按日期对齐
   - 补齐缺失的净出口并追加到目录
4. 产业确定性筛选
   - 锂电、锡、硅分别使用 `lithium_selection_rules.py`、`tin_rules.py`、`silicon_selection_rules.py`
   - 公共规则由 `selection_utils.py`、`import_export_rules.py`、`volume_position_ratio.py` 执行
5. Skill3 个股标的生成
   - `skills/stock-target-curator/scripts/generate_stock_targets.py`
   - 股票池来自 `config/stock_targets.json`，当前为人工维护种子池，不调用 AI
6. Skill4 看板数据排序
   - `skills/dashboard-data-sorter/scripts/sort_catalog.py`
   - 在最终输出生成后再执行一次，确保筛选/AI 阶段新增的行也保持排序

## 运行方式

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" -m workflow `
  --input <新的Excel文件.xlsx>
```

常用参数：

```text
--provider mock|deepseek|openai
--rules input/selection_rules.docx
--output output/<名称>_final.xlsx
--run-root workflow_runs
--dry-run
```

默认 `provider=mock`，完全离线。要使用真实 DeepSeek 分类时显式传：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" -m workflow `
  --input <新的Excel文件.xlsx> `
  --provider deepseek
```

真实 provider 仍受 `.env` 中 `REAL_LLM_ENABLED` 和 API Key 配置约束。

## 输出

每次运行生成一个独立目录：

```text
workflow_runs/<时间戳>_<run_id>/
  01_excel_catalog_curator/cataloged.xlsx
  01_excel_catalog_curator/dataset.pkl
  02_financial_variable_curation/directory_marked.xlsx
  workflow_summary.json
  workflow.log
```

最终文件默认复制到：

```text
output/<输入文件名>_workflow.xlsx
```

## 扩展新 Skill

新 skill 只需两步：

1. 在 `configs/workflow.yaml` 的 `steps` 中按顺序追加一步。
2. 若没有现成 runner，在 `workflow/runners.py` 中加一个函数并在 `RUNNERS` 注册。

内置 runner：

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

`command` runner 可用 `{input}`、`{output}`、`{run_dir}`、`{project_root}` 占位符调用任意 CLI。

## Skill3：个股标的生成

当前新增独立 Skill3 位于：

```text
skills/stock-target-curator/
```

Skill3 负责根据产业链上下游细分板块生成个股标的，并输出：

- 产业链
- 细分板块
- 所属环节
- 股票名称
- 股票代码

生成脚本：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  skills\stock-target-curator\scripts\generate_stock_targets.py `
  --industry silicon `
  --output output\个股标的_硅.xlsx
```

## Skill4：看板数据排序

当前新增独立 Skill4 位于：

```text
skills/dashboard-data-sorter/
```

Skill4 负责对 Skill1 / Skill2 / Skill3 处理后的 `指标目录` sheet 重新排序：

- 不修改目录内容，sheet 段按规则顺序排列，sheet 名称随数据段移动，段内数据行再排序；
- 每个 sheet 段内选中行在前、未选中行在后；
- 统计行和伪指标行放整个目录最下方；
- 保留并重建“点击指标跳转到对应 sheet”的超链接；
- 最终输出会在 `Indicator Name` 右侧新增 `指标名称归一化` 列；
- 同一子类下中国相关指标排前，外国/全球/海外排后；
- 括号内 `CIF中国/中国现货` 不作为中国依据，括号外指向外国时按外国处理；
- 子类/频率/国家/同类指标都相同时，按板块内部产业链节点顺序收尾排序；
- 可选输出连续两列：`指标名称归一化`、`排序说明`；排序说明为模板生成；
- 排序 policy 层按 `大类+子类` 选择现货/期货/价差/产量/库存/成本/利润/需求/进出口/平衡等策略；
- 大类、子类固定顺序为硬优先级，policy 只能在同 bucket 内细排；
- 最终 `排序说明` 为面向业务的自然语言，不输出内部机器字段；
- 同一硬 bucket 内 `指标名称归一化` 必须连续，region/当期/规格只在名称 block 内部排序；
- 规则依据为项目根目录 `排序规则.md`。

Skill4 已接入 `configs/workflow.yaml` 和三个产业 workflow 配置，作为每个
workflow 的最后一步，在 Skill3 生成个股标的后自动执行。
`scripts/run_industry_pipeline.py` 在最终输出生成后还会再执行一次 Skill4，
确保筛选/AI 阶段新增的行也保持排序。

排序脚本：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  skills\dashboard-data-sorter\scripts\sort_catalog.py `
  --input output\锡产业链数据_workflow_ai.xlsx `
  --add-normalized-column
```

## 规则同步约定

每次修改规则对应的 Python 脚本、JSON 配置或 workflow 配置后，必须同步更新以下 md：

- Skill1：`market-ai-dashboard/skills/excel-catalog-curator/SKILL.md`
- Skill2：`Selecting skill/SKILL.md`
- Skill3：`skills/stock-target-curator/SKILL.md` 与 `README.md`
- Skill4：`skills/dashboard-data-sorter/SKILL.md`、`README.md`、`排序规则.md`

同步内容包括规则行为、输入输出变化、去重/筛选/分类口径、执行入口和配置位置。md 是文档依据，最终执行仍以 Python 脚本为准，但二者必须在同一轮修改中保持一致。

看板侧规则变更同样必须同步：`本地可视化dashboard/docs/排序规则.md` 与项目根目录
`排序规则.md` 保持一致，同时更新 `skills/dashboard-data-sorter/SKILL.md`、
`README.md` 以及 `market-ai-dashboard/skills/excel-catalog-curator/SKILL.md`。
