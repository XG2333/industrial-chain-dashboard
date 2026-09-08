# financial-variable-curation

通用、规则可插拔的金融变量筛选工作流。当前阶段不内置任何正式业务规则，只提供：

- `inspect`：只做确定性 Excel 探查、变量画像、数据质量统计和频率识别，不调用 LLM。
- `run --use-default-rules`：用保守占位规则跑通端到端流程，结果明确标记为非生产结果。
- `run --rules <file>`：读取自然语言规则文本，解析、校验、编译后执行。
- `run --rule-set <name>`：直接使用已保存且版本化的规则集。
- `--save-rule-set` 保存版本化规则集，默认 `production_ready=false`；只有显式加 `--mark-production` 才会标记为生产可用。

## 快速开始

```bash
python -m venv --system-site-packages .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"

python -m financial_variable_curation inspect --input input/example.xlsx
python -m financial_variable_curation inspect --input input/example.xlsx --header-row 1 --date-column date
python -m financial_variable_curation inspect --input input/example.xlsx --sheet MarketData
python -m financial_variable_curation run --input input/example.xlsx --use-default-rules --output output/example_selected.xlsx
python -m financial_variable_curation run --input input/example.xlsx --rules input/selection_rules.txt --output output/user_selected.xlsx
```

## SQLite persistence

The project uses SQLAlchemy 2.x and an internal versioned migration runner. Migrations are recorded in `schema_migrations`; they are not applied by `metadata.create_all()` at startup.

```bash
python -m financial_variable_curation db-upgrade --database data/financial_variable_curation.db
python -m financial_variable_curation db-current --database data/financial_variable_curation.db
python -m financial_variable_curation db-downgrade --database data/financial_variable_curation.db --revision base
```

`inspect --database` persists inspection artifacts after writing JSON. A separate `persist-inspection` command can load an existing artifact directory without rerunning Excel inspection:

```bash
python -m financial_variable_curation inspect --input input/example.xlsx --database data/financial_variable_curation.db
python -m financial_variable_curation persist-inspection --artifacts artifacts/<run_id> --database data/financial_variable_curation.db
python -m financial_variable_curation show-run --run-id <run_id> --database data/financial_variable_curation.db
```

Database settings come from `DATABASE_URL` and `DATABASE_ECHO`; see `.env.example`.

## LLM classification

The `classify` command reads persisted variables from SQLite, builds the existing classification request, and calls the configured LLM client. Mock mode is fully offline; OpenAI mode requires `REAL_LLM_ENABLED=true` and an `OPENAI_API_KEY`.

```bash
python -m financial_variable_curation classify --run-id <run_id> --provider mock --limit 20
python -m financial_variable_curation classify --run-id <run_id> --provider openai --limit 20 --database data/financial_variable_curation.db
python -m financial_variable_curation classify --run-id <run_id> --provider openai --limit 3 --dry-run
```

OpenAI provider settings, retry limits, cache schema versions, and the `REAL_LLM_ENABLED` safety switch are defined in `.env.example`. API keys are only read from the environment and are never written to artifacts or the database.

## Rule workflow

Natural-language rule files can be validated and compiled without executing any variable selection:

```bash
python -m financial_variable_curation validate-rules --rules input/selection_rules.txt --provider mock
python -m financial_variable_curation validate-rules --rules input/selection_rules.txt --provider openai
python -m financial_variable_curation compile-rules --rules input/selection_rules.txt --name cross_industry_rules --version 1 --provider mock
python -m financial_variable_curation compile-rules --rules input/selection_rules.txt --name cross_industry_rules --version 1 --provider openai --activate
```

The workflow parses the file, normalizes the structured rules, validates whitelisted fields/operators/actions, detects conflicts, compiles an execution plan, and writes audit artifacts under `artifacts/<parse_run_id>/rules/`. It never modifies Excel or executes the final selection engine.

## Deterministic selection

After variables have been inspected, classified, and persisted, and a compiled rule set exists, the deterministic selection engine can generate formal selection statuses without exporting Excel:

```bash
python -m financial_variable_curation select --run-id <classification_run_id> --rule-set cross_industry_rules --rule-version 1 --database data/financial_variable_curation.db
python -m financial_variable_curation select --run-id <classification_run_id> --rule-set-id <rule_set_id> --dry-run
python -m financial_variable_curation show-selection --selection-run-id <selection_run_id> --database data/financial_variable_curation.db
```

`select` requires a `VALIDATED` rule set only when `--allow-validated-rules` is passed; `ACTIVE` rule sets are preferred. `--dry-run` executes rules and writes audit artifacts without persisting a formal selection run. The engine never calls an LLM and never modifies the original Excel file.

## Export and full pipeline

Export a completed selection run to Excel:

```bash
python -m financial_variable_curation export --selection-run-id <selection_run_id> --output output/selected.xlsx
```

Run the complete offline pipeline with a natural-language rule file:

```bash
python -m financial_variable_curation pipeline --input input/example.xlsx --rules input/selection_rules.txt --provider mock --output output/selected.xlsx
```

The pipeline executes inspection, persistence, classification, rule parsing/compilation, deterministic selection, Excel export, and writes `pipeline_summary.json`. It never calls an LLM in mock mode and never overwrites the original source workbook.

## 设计边界

- AI 只负责语义分类和自然语言规则到 JSON Schema 的转换。
- AI 不输出 SQL、不修改 Excel、不直接删除变量。
- 规则校验不通过时不得进入正式规则表，也不得执行。
- 确定性规则引擎只读取结构化规则；未提供的优先级不猜测，采用“不排序/不淘汰”的缺省行为。
- 默认占位规则仅用于验证流程，输出中固定记录 `rule_source=DEFAULT_PLACEHOLDER` 与 `production_ready=false`。
- Inspect 输出 `request.json`、`workbook_profile.json`、`variable_profiles.json`、`inspection_summary.json` 和 `run.log`。

## 本地从零运行

```powershell
Set-Location "C:\Users\11\Documents\Selecting_skill"

py -3.12 -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Copy-Item ".\.env.example" ".\.env"

.\.venv\Scripts\python.exe -m financial_variable_curation --help
```

然后按顺序运行：

```powershell
.\.venv\Scripts\python.exe -m financial_variable_curation inspect --input input\business_data_test.xlsx --database data\financial_variable_curation.db
.\.venv\Scripts\python.exe -m financial_variable_curation classify --run-id <inspection_run_id> --provider mock --database data\financial_variable_curation.db
.\.venv\Scripts\python.exe -m financial_variable_curation validate-rules --rules input\selection_rules_minimal.txt --provider mock
.\.venv\Scripts\python.exe -m financial_variable_curation compile-rules --rules input\selection_rules_minimal.txt --name business_test_rules --version 1 --provider mock
.\.venv\Scripts\python.exe -m financial_variable_curation select --run-id <classification_run_id> --rule-set business_test_rules --rule-version 1 --allow-validated-rules
.\.venv\Scripts\python.exe -m financial_variable_curation export-selection --selection-run-id <selection_run_id> --output output\business_data_selected.xlsx
.\.venv\Scripts\python.exe -m financial_variable_curation pipeline --input input\business_data_test.xlsx --rules input\selection_rules_minimal.txt --provider mock --output output\business_data_mock_selected.xlsx
```
