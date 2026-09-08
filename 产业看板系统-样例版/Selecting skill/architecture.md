# 架构评审与实施方案

## 1. 当前项目状态

检查 `C:\Users\11\Documents\Selecting skill` 后，该目录为空目录，不是 Git 仓库，也没有既有 Python/SQL 模块。因此当前结论是：

- 当前项目尚未支持规则可插拔，因为项目本身尚未建立。
- 没有既有模块依赖硬编码规则；后续需要从零避免该问题。
- 需要新增完整 Python 包、规则数据模型、AI 解析边界、确定性引擎和 CLI。

## 2. 硬编码规则禁止边界

以下内容不允许出现在引擎或 SQL 中：

- 价格、库存、产量、营收、利润等具体业务优先级。
- 日频、月频、季频等固定取舍优先级。
- 来源、行业、公司的固定排序。
- 仅凭变量名称相似或相关系数高自动删除。

允许存在且必须与执行逻辑分离的默认值：

- 全空列、恒定列、高缺失率属于通用数据质量规则，作为 `DEFAULT_PLACEHOLDER` 存在。
- Mock 分类器可以包含示例语义词表，但它不是规则引擎的一部分，也不决定最终优先级。
- 如果规则集未提供某类规则，执行器按“不排序、不淘汰、不限制”的明确缺省行为运行。

## 3. 目标工作流

```text
输入Excel
→ Excel结构探查
→ 日期列与变量列识别
→ 变量质量分析
→ AI变量语义分类
→ 读取规则文本
→ AI将自然语言规则解析为结构化规则
→ Pydantic校验结构化规则
→ 规则冲突检测
→ 编译为可执行规则
→ SQL/Python确定性规则引擎执行
→ 重复变量处理
→ 生成筛选结果
→ 导出Excel和审计报告
```

AI 边界固定在“变量分类”和“规则解析”两步，其余步骤全部由确定性程序执行。

## 4. 三种运行模式

### Inspect 模式

```bash
python -m financial_variable_curation inspect --input input/example.xlsx
```

可选参数：

- `--header-row`：显式指定 1-based 表头行。
- `--date-column`：显式指定日期列名或 1-based 列位置。
- `--sheet`：只检查指定 Sheet。
- `--artifacts-dir`：产物目录。

只读取 Excel，不调用 LLM，生成：

- `workbook_profile.json`
- `variable_profiles.json`
- `inspection_summary.json`
- `request.json`
- `run.log`

复杂或不确定场景不会猜测解析，而是标记为 `NEEDS_REVIEW` 或 `UNSUPPORTED` 并记录原因。

### Default Rules 模式

```bash
python -m financial_variable_curation run --input input/example.xlsx --use-default-rules --output output/example_selected.xlsx
```

使用项目内置的保守占位规则跑通流程，结果必须标记：

```text
rule_source = DEFAULT_PLACEHOLDER
production_ready = false
```

### User Rules 模式

```bash
python -m financial_variable_curation run --input input/example.xlsx --rules input/selection_rules.txt --output output/example_selected.xlsx
```

规则文本经解析、Pydantic 校验、冲突检测、编译后执行。校验失败时停止，不写入正式规则表。

`--save-rule-set` 会生成唯一版本，例如 `cross_industry_rules_v1`。保存后的规则集默认
`production_ready=false`，避免把当前阶段的示例规则误当成正式业务规则；确认规则可用时再显式传入
`--mark-production`。

## 5. 规则数据模型

`RuleSet` 至少包含：

- `category_priorities`
- `subcategory_priorities`
- `frequency_priorities`
- `source_priorities`
- `hard_filter_rules`
- `sorting_rules`
- `scoring_rules`
- `deduplication_rules`
- `exception_rules`
- `conflict_resolution_rules`
- `review_rules`
- `unresolved_items`

空规则集在数据模型层合法，但不得标记为 `ACTIVE` 或 `production_ready=true`。

CLI 在 User Rules 或 Rule Set 模式下遇到空规则集时拒绝执行，避免把空规则集当作正式筛选结果。

规则状态：

```text
DRAFT
PARSED
VALIDATED
ACTIVE
DEPRECATED
INVALID
```

## 6. 解析、校验、编译、执行边界

- 解析：AI/解析器只输出 `RuleSet` JSON，不输出 SQL，不直接操作数据。
- 校验：Pydantic 结构校验、枚举检查、字段存在性、优先级冲突、重复规则、不可执行规则、例外条件完整性。
- 编译：将优先级展开为有效顺序，生成 `CompiledRuleSet`，并计算规则哈希。
- 执行：确定性引擎只读取 `CompiledRuleSet`，完成过滤、排序、评分、去重、数量限制和复核分流。

## 7. 文件布局

```text
src/financial_variable_curation/
  cli.py
  models/                 # Pydantic 数据模型
  io/                     # Excel、JSON、审计产物读写
  inspection/             # 文件校验、表头/日期检测、变量提取、质量/频率/伪高频分析
  pipeline/               # Inspect 与 Execute 编排
  ai/                     # 分类器和规则解析器接口、Mock/可选 OpenAI
  rules/                  # 默认规则、校验、编译、规则库
  utils/                  # 哈希等工具
tests/
scripts/generate_example_data.py
```

## 8. 分阶段实施计划

1. 包骨架、规则模型、CLI 接口、公共输出契约。
2. Excel 结构探查、变量质量画像、频率识别（当前阶段已完成，不依赖 LLM）。
3. Mock/真实分类器与规则解析、校验、编译、版本化存储。
4. 默认规则和确定性执行引擎。
5. 输出 Excel 与审计报告，完成三种 CLI 模式。
6. 示例数据、测试、文档和端到端冒烟。

## 9. 测试计划

- 模型测试：空规则集合法、生产规则不允许为空、枚举和必填字段校验。
- 解析测试：JSON 规则直接解析；自然语言短语解析为结构化规则。
- 校验测试：优先级冲突、重复规则、非法字段、非法操作符、例外条件不完整。
- 引擎测试：全空列删除、恒定列删除、高缺失分流、无规则不淘汰、不确定重复进入复核。
- CLI 测试：Inspect、Default Rules、User Rules 三种模式均能生成产物。
