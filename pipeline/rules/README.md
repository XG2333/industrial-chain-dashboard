# 产业规则文件索引

本项目将确定性规则集中到两处：

- 硅产业规则：`scripts/silicon_*.py` + 本目录 `silicon_*_rules.md`
- 锂电产业规则：`scripts/lithium_rules.py` + 本目录 `lithium_*_rules.md`

锂电规则的实际执行来源是 `scripts/lithium_rules.py`，Markdown 文件用于规则维护与审计说明。

所有产业统一使用 `供给` 作为供需侧的大类名称，不再使用 `供应` 作为大类。
`供应`、`供应量` 等词语只作为关键词识别，不单独形成大类。

`apply_industry_selection.py` 在保存前会对目录表所有行（包括没有序号的
Skill2 引用行）执行归一化：大类、子类和指标标签中的 `供应` 统一替换为
`供给`，避免旧规则残留。

## 通用规则

| 规则文件 | 规则模块 | 使用位置 | 说明 |
|---|---|---|---|
| [import_export_rules.md](import_export_rules.md) | `scripts/import_export_rules.py` + `scripts/calculate_net_exports.py` | `workflow_lithium.yaml` / `workflow_tin.yaml` / `workflow_silicon.yaml` / `apply_industry_selection.py` | 只保留成对进出口、无配对筛除、成对计算净出口 |
| `scripts/selection_utils.py` | `scripts/selection_utils.py` | 锂电 / 锡 / 硅筛选规则 + `apply_industry_selection.py` | 统一主力/01/05/09合约过滤，并强制成交量与持仓量一一配对 |
| [volume_position_ratio_rules.md](volume_position_ratio_rules.md) | `scripts/volume_position_ratio.py` + `scripts/apply_industry_selection.py` | 锂电 / 锡 / 硅 | 对成对成交量/持仓量计算缺失的成交持仓比 |
| [classification_candidates_rules.md](classification_candidates_rules.md) | `scripts/classification_candidates.py` + `scripts/check_classification_consistency.py` + `scripts/ai_assisted_curation.py` | `apply_lithium_curation.py` / `apply_tin_curation.py` | 候选式大类/子类识别、价格子类确定性优先级、其他多候选 AI 消歧 |
| [secondary_selection_rules.md](secondary_selection_rules.md) | `scripts/secondary_selection.py` | `apply_industry_selection.py` + `volume_position_ratio.py` | 第一次筛选后追加"二次筛选是否保留"列：只保留日度/周度、非指数、按板块保留词 |

### 通用筛选排除规则

- 标题含 `进出口均价 / 进口均价 / 出口均价 / 净出口均价` 的指标一律不保留。
- 标题含 `同比 / 环比 / 占比` 的指标一律不保留；其中 `供给` 大类的 `同比 / 环比` 使用独立状态说明。
- 主力/01/05/09合约过滤仅对 `期货价格 / 成交量 / 持仓` 子类生效：期现价差
  （现货-期货）、交割库容等标题含"期货"字样但非合约行的指标不受合约过滤影响
  （走各自的基差/价差或板块规则）。
- 锂矿品位化学式归一化（`selection_utils._normalize_chemical_formula_text`）：
  "锂辉石（中国现货 Li2O: 3%-4%）" 与 "锂辉石（中国现货 3%-4%）" 视为同一
  指标（化学式仅为品位标注，日度版多写、周度/月度版省略），删除 `Li2O:` /
  `Li₂O:` 字样后同组去重只保留最高频。精确匹配化学式字样，不影响
  NMP/DMC/FEC 等含其他英文字母的指标。

所有产业统一执行进出口配对与净出口计算：

- 标题频率优先于目录频率
- 指标名称同时含“年化”和其他日/周/月/季/年频率词时，按年度处理（年化为实际数据频率）
- 指标名称含“半月度”时按“月度”处理（半月频数据归入月度频率组，避免与月度重复行分开成组）
- 钴酸锂价格标题归一化（`selection_utils._normalize_cobalt_price_text`）：
  “4.45V钴酸锂(国产)” 与 “钴酸锂 4.45V” 视为同一产品（周度版省略“国产”标注，
  均视为国产钴酸锂），电压尾零归一化（4.40V/4.50V 与 4.4V/4.5V 同一产品）；
  同一电压只保留最高频（如日度优先于周度/月度）
- 分国别/分省份 Sheet 的总量行参与
- 进口和出口可跨 Sheet 配对
- 均价类进出口不保留
- 重复进口/出口/净出口只保留一条

```text
Skill1 目录生成
    -> Skill2 金融变量筛选与目录标记
    -> 通用进出口配对 + 净出口计算（import_export_rules.py / calculate_net_exports.py）
    -> 产业专属筛选 + 通用进出口配对去重（apply_industry_selection.py）
```

## 锂电产业规则

| 规则文件 | 规则模块 | 使用位置 | 说明 |
|---|---|---|---|
| [lithium_catalog_rules.md](lithium_catalog_rules.md) | `scripts/lithium_rules.py` | `scripts/lithium_catalog.py` | 板块分类、频率判定 |
| [lithium_classification_rules.md](lithium_classification_rules.md) | `scripts/lithium_rules.py` | `scripts/apply_lithium_curation.py` | 大类、子类、数据性质 |
| [lithium_selection_rules.md](lithium_selection_rules.md) | `scripts/lithium_selection_rules.py` | `scripts/apply_industry_selection.py` | 锂电专属确定性筛选 |
| [lithium_indicator_tags_rules.md](lithium_indicator_tags_rules.md) | `scripts/lithium_rules.py` | `scripts/apply_lithium_curation.py` | 产品、规格、工艺、地域、统计口径等指标标签 |

锂电规则层级（分类部分不再使用优先级链，统一由候选模块处理）：

```text
Skill1 板块分类 (lithium_rules.SECTOR_RULES / classify_sector)
    -> Skill2 金融变量筛选与目录标记 (外部 selection_rules.docx)
    -> 通用净出口计算 (calculate_net_exports.py)
    -> 锂电目录校准 (classification_candidates.candidate_plan / lithium_rules.classify_nature)
    -> 锂电指标标签 (lithium_rules.build_tags)
    -> 输出检查与审计报告 (apply_lithium_curation.py)
```

## 锡产业规则

| 规则文件 | 规则模块 | 使用位置 | 说明 |
|---|---|---|---|
| [tin_catalog_rules.md](tin_catalog_rules.md) | `scripts/tin_rules.py` | `scripts/tin_catalog.py` | 板块分类、频率判定 |
| [tin_classification_rules.md](tin_classification_rules.md) | `scripts/tin_rules.py` | `scripts/apply_tin_curation.py` | 大类、子类、数据性质 |
| [tin_selection_rules.md](tin_selection_rules.md) | `scripts/tin_rules.py` | `scripts/apply_tin_curation.py` | 确定性筛选规则 |
| [tin_indicator_tags_rules.md](tin_indicator_tags_rules.md) | `scripts/tin_rules.py` | `scripts/apply_tin_curation.py` | 产品、规格、工艺、地域、统计口径等指标标签 |

锡产业规则层级（分类部分同样使用候选模块）：

```text
Skill1 板块分类 (tin_rules.SECTOR_RULES / classify_sector)
    -> Skill2 金融变量筛选与目录标记 (外部 selection_rules.docx)
    -> 通用净出口计算 (calculate_net_exports.py)
    -> 锡目录校准 (classification_candidates.candidate_plan / tin_rules.classify_nature)
    -> 锡确定性筛选 (tin_rules.select_rows)
    -> 锡指标标签 (tin_rules.build_tags)
    -> 输出检查与审计报告 (apply_tin_curation.py)
```

## AI 辅助判断

锂电、硅、锡共用同一套 AI 辅助层：

| 规则文件 | 规则模块 | 说明 |
|---|---|---|
| [ai_assisted_curation.py](../scripts/ai_assisted_curation.py) | `scripts/ai_assisted_curation.py` | 确定性规则后处理，仅对未识别/多候选/单位冲突指标调用 DeepSeek |

执行规则：

1. 保留确定性规则结果。
2. 仅对“其他/未识别/未指定/多候选/单位冲突”的指标触发 AI。
3. 默认按 20 条/批调用 DeepSeek，返回严格 JSON；输出截断时会尽量恢复已经完整的结果。
4. 模型结果必须落在 `候选分类组合` / `候选大类` / `候选子类` 的范围内，否则不覆盖。
5. 对模型结果执行单位一致性检查。
6. 结果写入本地 SQLite 缓存，空结果不缓存，避免后续跳过仍需 AI 判断的指标。

### 观测（Langfuse）

**Langfuse 是旁路 observability/evaluation layer，不是业务逻辑执行依赖。**
生产链：Raw Excel → Skill workflow → deterministic rules → DeepSeek（仅歧义）→
Langfuse tracing → final output → verifier/audit → optional Langfuse evaluation
→ dashboard。所有 Langfuse 故障（Cloud 不可达 / 429 / score 写入失败 /
correlation 获取失败 / Dataset 不可用）都 best-effort 降级，**不影响业务
workflow 结果**。

**Production Required（稳定生产接入）：**
- tracing / generation 记录（`ai_disambiguation`、`stock_targets`）
- workflow_run_id correlation（trace id = md5(run_id)，同一 run 归并）
- physical_variable_id correlation（correlation index，run 内精确关联）
- verifier score 写入（门控：唯一关联 + 真实 generation + 可裁定状态）
- auto evaluation（run 后自动 correlation + 门控 score，失败不阻断）
- failure isolation（全链路 best-effort，实测 429 期间 workflow 仍 SUCCESS）

**Optional（未来评估功能，非生产前置）：**
- Golden Dataset 扩容 / 人工审核（`golden_review_pack.xlsx` 已暂停，非当前待办）
- Prompt 实验（v2/v3 均 DO_NOT_PROMOTE，v1 为 production baseline）
- candidate-rule A/B、Prompt v4、更多人工 review、Dataset import

**推荐生产运行方式：**
```powershell
& "<local-documents>\Selecting skill\.venv\Scripts\python.exe" `
  scripts\run_industry_pipeline.py --industry <lithium|tin|silicon> `
  --input data_input\<原始文件>.xlsx --output output\<正式输出>.xlsx `
  --ai --langfuse-evaluation
```
- 环境变量（项目根 `.env`，不打印 secret）：`LANGFUSE_PUBLIC_KEY` /
  `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` / `LANGFUSE_ENABLED`（默认 true，
  控制 tracing）；`LANGFUSE_EVALUATION_ENABLED`（控制 evaluation，可独立关闭）；
  `LANGFUSE_TRACING_ENVIRONMENT`（默认 development）。
- evaluation 也可用 `--langfuse-evaluation` 显式开启；都不开启时 workflow 行为
  与接入前完全一致（tracing 默认开、evaluation 默认关）。

所有 AI 调用（`ai_assisted_curation.py`、`ai_stock_targets.py`）经统一适配层
[workflow/observability.py](../workflow/observability.py) 接入 Langfuse：

- 业务脚本不直接 import langfuse；观测是 best-effort，key 未配置/服务不可达时
  全部退化为 no-op，不改变业务行为、不抛异常。
- 配置在项目根 `.env`（`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
  `LANGFUSE_BASE_URL` / `LANGFUSE_ENABLED`）。
- trace id = md5(`WORKFLOW_RUN_ID`)（32 hex）：同一 run 的跨进程/跨调用观测
  归并到同一 trace；trace 名固定为 `workflow.<industry>`。
- 观测层级：根 span `workflow.<industry>` → stage span（如 `ai_disambiguation`、
  `stock_targets`）→ generation `llm.<prompt_name>`；线程池场景用 OTEL
  `use_span` 显式挂接父级。
- generation 记录 token usage（SDK v4 参数 `usage_details`）；stage span 记录
  `items_total` / `cache_hits` / `actual_llm_calls` / `cache_hit_rate`；
  metadata 含 `workflow_run_id` / `industry` / `stage` / `prompt_name` /
  `prompt_version` / `prompt_hash`（SHA-256）。
- 进程退出前须调用 `observability.flush()`（两个脚本均已接入）。

### 观测-Evaluation（Phase 2a，dry-run）

Verifier case ↔ Langfuse generation 的稳定关联与 dry-run 回填：

- 唯一变量级主身份 `physical_variable_id = sha256(raw_file_hash|sheet|col|name)[:16]`
  （与 Result_audit 审计 findings 同源；3493/3493 实测命中）。
- 关联键：`evaluation_key = sha256(vid|prompt_version|prompt_hash)`；
  `score_id = sha256(evaluation_key|audit_run_id|score_source|score_name)`（幂等）。
- 工具：`scripts/evaluation_backfill.py`（dry-run，只读，不写 score）；
  纯逻辑在 `scripts/evaluation_correlation.py`；报告输出
  `workflow_runs/<run>/audit/evaluation/`（correlation_index.jsonl /
  evaluation_dry_run.{json,csv} / unmatched_cases.csv / ambiguous_cases.csv）。
- 关联规则：run 内 (sheet,name,unit) 精确匹配；人工 pack 用 run 内名称唯一性
  （NAME_UNIQUE_RUN_LOCAL）；禁止跨 run 名称匹配；AMBIGUOUS/UNMATCHED 不评分。
- 正确性规则：HUMAN > VERIFIER；ERROR / REVIEW_REQUIRED / NEEDS_HUMAN_REVIEW /
  PENDING_HUMAN_REVIEW 一律不推导 correctness（影子审计是风险发现器，不是裁判）。
- 设计文档：`docs/langfuse_evaluation_design.md`。

### 观测-Evaluation 写入（Phase 2b，已实施）

- `workflow/observability.py::record_evaluation()`：把 verifier / human scores
  写入 Langfuse（best-effort）。observation 必须经 correlation index 唯一解析
  （workflow_run_id + physical_variable_id + stage，或显式 observation_id）；
  AMBIGUOUS / UNMATCHED → no-op。**不构造 trace_id**（禁止 md5(workflow_run_id)/
  zfill）——trace_id 取自 index 行的真实关联。prompt_version / prompt_hash
  只从 correlation index 读取。
- score_name 前缀强制：`verifier_` / `human_`；来源不明禁止。
- correctness 门控：`*_classification_correct` 必须有明确 expected_output；
  verifier 状态 ∈ {PENDING_HUMAN_REVIEW, REVIEW_REQUIRED, ERROR, AMBIGUOUS,
  NEEDS_HUMAN_REVIEW} 禁止写；human UNRESOLVED 只允许 human_decision。
- 幂等：`score_id = sha256(evaluation_key|idem_source|source|score_name)`，
  idem_source = audit_run_id（verifier 必填）或 metadata['source_record_id']
  （human 且无 audit_run_id 时必填）；时间戳不参与幂等。
- SDK 4.14.1 事实：BOOLEAN score 的 value 必须为 number（1/0），字符串 400；
  CATEGORICAL 的字符串值在 API 的 `stringValue` 字段。
- Dataset：`scripts/evaluation_dataset_export.py` 幂等导入人工确认案例到
  `classification/human_confirmed`（25 条 v1 已导入，item id =
  `golden_<industry>_<commodity>_<vid>`；expected_output 只含人工确认字段；
  NO_AUDIT case 保留标记）。

### 观测-Evaluation 生产闭环（Phase 2c，已实施）

- 开关：`run_industry_pipeline.py --langfuse-evaluation` 或
  `LANGFUSE_EVALUATION_ENABLED=true`；**独立于 tracing**（tracing 开启时
  evaluation 仍可单独关闭）。默认关闭。
- 位置：run 完成 + audit 之后自动执行（`evaluation_backfill.run_auto_evaluation`），
  best-effort，失败不阻断业务 workflow。
- 自动产出：correlation_index.jsonl / evaluation_dry_run.{json,csv} /
  unmatched_cases.csv / ambiguous_cases.csv（workflow_runs/<run>/audit/evaluation/），
  无需人工执行 backfill。
- 自动写分（门控内）：verifier_status / verifier_verdict / verifier_error_type /
  verifier_classification_correct（需 golden 期望 + AI 结果回联 + 状态可裁定）/
  human_decision / human_classification_correct / human_expected_output。
- correctness 禁止：ERROR→false、NEEDS_HUMAN_REVIEW→false、
  PENDING/AMBIGUOUS→correctness、无 generation 的历史 case→score。
- AI 结果回联：generation output（results 按本地 variable_id）→ 行级
  ai_major/ai_sub。
- **Dataset 不自动增长**：export 保持人工/受控触发，生产 case 不自动进入。

### 观测-Evaluation Prompt 实验（Phase 3，已实施）

- 工具：`scripts/prompt_experiment.py`（--register / --verify / --experiment）。
- Langfuse Prompt：`ai_disambiguation`（v1=baseline 来自生产代码、v2=candidate
  最小可解释改动：候选硬约束 + schema 明确性）；metadata 记录
  source=code_baseline / original_prompt_version / original_prompt_hash /
  change_reason / change_summary。**不自动推 production，不删除代码中 Prompt**。
- Dataset：`classification/human_confirmed`（25 条，实验时 25/25 eligible；
  candidates 缺失 → context_limited 标记，不伪造）。
- Evaluator：确定性（expected 大类/子类 vs model major/sub，normalization=
  strip+折叠空白；子类期望缺失不判错；不评估"是否选中"）。
- Experiment：同一 dataset / 同模型 / 同参数（temperature=0, json_object）/
  同 evaluator，仅 Prompt 不同；输出 metrics（accuracy/fixed/regressed/
  latency/usage/estimated cost）+ case_diff.csv（FIXED/REGRESSED/
  UNCHANGED_CORRECT/UNCHANGED_WRONG）。
- 实验产物：`workflow_runs/experiments/prompt_compare_<ts>/`。

### 观测-Evaluation Dataset enrichment（Phase 3b，已实施）

- 工具：`scripts/dataset_enrich.py`（--dry-run / --apply / --verify）。
- 生产 item schema（ai_assisted_curation.build_item）：variable_id / name /
  sheet / unit / frequency / sector / current_major / current_sub /
  current_tags（候选分类组合/候选大类/候选子类 在 指标标签 内）。
- 候选恢复源：原 run 的 `final/final_output.xlsx` 指标标签（该 run 实际运行
  indicator_tags 后的产物）——HISTORICAL_EXACT；禁止用人工 expected 反推候选。
- metadata 标记：context_status（HISTORICAL_EXACT / HISTORICAL_RECONSTRUCTED /
  CURRENT_RULE_RECONSTRUCTED / UNAVAILABLE）、candidate_provenance、
  source_run_id / source_artifact、reconstruction_version、schema_version=2.0、
  preserved_v1 快照（不覆盖历史证据）。
- 结果（25 条）：25/25 production_equivalent；expected_in_candidates 22/25；
  root cause：19 PROMPT_SELECTION_ERROR / 3 WRONG_CANDIDATES / 1
  OUTPUT_PARSE_ERROR / 2 CORRECT。
- v1 + 生产候选上下文：production_equivalent 子集 accuracy **76%**（19/25），
  对比无候选实验 8% —— 低准确率主因是 Dataset 缺候选上下文，非 Prompt。
- eligible 分层：production_equivalent / historical_reconstructed /
  context_limited / ineligible，分属不同 accuracy，不混算。

### 观测-Evaluation Candidate-rule A/B + Prompt v3（Phase 3c，已实施）

- 工具：`scripts/candidate_ab.py`（离线回放，不跑 LLM）+ `prompt_experiment.py`
  （--items-file / --runs N / 聚合）。
- WRONG_CANDIDATES 根因：08-18 时代旧规则版本缺"成本利润优先于价格"优先级；
  **当前** `classification_candidates.py` 已有通用规则（名称含 盈亏/利润/成本 →
  major 收敛成本利润，lines 335-338/362/379），无硬编码，同类概念（进出口盈亏 13
  条 / 进口盈亏 / 进口成本 / 出口成本等）全部泛化命中。
- 离线回放（25 条 production-equivalent）：expected_in_candidates
  **22 → 25**，wrong_candidates_fixed=3，new_regressions=0，
  candidate_changed_cases=13；changed case 标记
  context_status=CURRENT_RULE_RECONSTRUCTED、schema_version=2.1。
- Prompt v3：基于 v1（不继承 v2），紧凑追加"先判断整体经济含义，再以关键词辅助；
  名称含价格/现货不得默认价格类；进出口盈亏/利润/成本等组合指标先判整体性质；
  必须从候选中选择"；输出 schema 完全不变；注册 label candidate3。
- 实验：old/new candidates × v1/v3，每 Prompt 3 次；聚合 mean/min/max accuracy、
  per-case consistency、selection_stability；归因分解 candidate_rule_gain 与
  prompt_gain 分开计算（禁止合并）。v3 不自动 promote（门槛：mean accuracy >
  v1、regressions ≤ fixed、stability 不降、latency/tokens 不显著恶化）。
- Phase 3c 实测（production-equivalent 25 条 ×3 次）：
  | 配置 | mean | min | max | stability |
  |---|---|---|---|---|
  | old candidates + v1 | 68.0% | 64% | 72% | 0.60 |
  | new candidates + v1 | **98.7%** | 96% | 100% | 0.96 |
  | new candidates + v3 | 93.3% | 88% | 96% | 0.92 |
  - **Candidate Rule Gain +30.7pp**（当前 classification_candidates.py 即正确版本，
    08-18 旧规则缺成本利润优先级；离线回放 22→25、0 回归）
  - **Prompt Gain −5.3pp**（v3 弱于 v1）→ **v3 DO_NOT_PROMOTE**；
    candidate rule 推荐保持/上生产。
  - ⚠️ 98.7% 等 accuracy **仅指当前 25 条人工确认 production-context evaluation
    子集**（tin，含生产候选），**不是生产总体分类准确率**——总体准确率需 Golden
    Dataset 扩容覆盖后另行评估。

### 观测-Evaluation Golden Dataset 扩容（Phase 4，已实施，**OPTIONAL**）

> **状态声明（2026-09-02）：Golden Dataset 扩容 / 人工审核 / Prompt 实验属于
> optional evaluation tooling，不是 production workflow prerequisite。**
> `golden_review_pack.xlsx`（60 条候选）是 optional future dataset expansion，
> **不是当前待办**——人工审核已暂停，不要求填写。

- 工具：`scripts/golden_coverage.py`（普查 + coverage matrix + 审核池 + quality metrics）。
- 完整分类空间（最新各产业 run）：9302 变量（lithium 5903 / silicon 2359 / tin 1040）；
  候选数桶 1=5782 / 2=106 / 3+=37 / 0=3377；AI ambiguity 潜在 143；
  verifier flagged 1276（lithium 审计 ERROR 判定为主）。
- 当前 25 条 Golden 覆盖：industry 0.333 / major 0.375 / sub 0.083（全部 tin；
  major：进出口 10 / 成本利润 13 / 供给 2）。
- quality metrics：hard 0.56 / multi-candidate 0.40 / human-corrected 0.52 /
  family_diversity 0.52 / expected_in_candidates 0.88。
- 规则：verifier 只作 P0 标记不作 expected；只有人工确认后 case 才能进
  classification/human_confirmed；扩容继续用同一 Dataset（schema_version/
  semantic_family/difficulty 元数据区分）。

## 产业专属筛选

所有产业在 Skill2 公共筛选之后，统一执行 `scripts/apply_industry_selection.py`，按产业调用对应规则模块覆盖 `是否选中`：

| 产业 | 规则模块 |
|---|---|
| 锂电 | `scripts/lithium_selection_rules.py` |
| 锡 | `scripts/tin_rules.py` |
| 硅 | `scripts/silicon_selection_rules.py` |

`apply_industry_selection.py` 写入"是否选中"后，追加计算"二次筛选是否保留"
列（不修改"是否选中"），规则见
[secondary_selection_rules.md](secondary_selection_rules.md)。

## 净出口计算公共规则

锂电、硅、锡及后续新增产业链统一使用 [net_export_rules.md](net_export_rules.md) 对应的通用脚本：

- `scripts/calculate_net_exports.py`
- `financial_variable_curation/rules/net_export_calculator.py`

AI 审计报告会输出每条实际修改指标的：

- 修改前大类/子类/数据性质
- 修改后大类/子类/数据性质
- 标签字段变更明细
- AI 修改原因
- 候选多于一个的指标人工二次复核清单

人工复核清单不再逐条平铺，而是按候选分类组合聚合：先显示候选组合、
指标数量和 AI 结果分布，再按组展开对应指标明细，方便人工定位同一类
歧义问题。

每次 `--ai` workflow 会保留 `*_ai_report.md`，供人工在 AI 已写入结果后
做二次反馈；AI 修改明细和人工复核清单在同一个报告文件内。

## 硅产业规则

| 规则文件 | 对应脚本 | 说明 |
|---|---|---|
| [silicon_classification_rules.md](silicon_classification_rules.md) | `scripts/reclassify_silicon.py` | 大类/子类判定规则 |
| [silicon_selection_rules.md](silicon_selection_rules.md) | `scripts/silicon_selection_rules.py` | 是否选中的确定性筛选规则 |
| [silicon_catalog_rules.md](silicon_catalog_rules.md) | `scripts/silicon_catalog.py` | Skill1 板块分类规则 |
| [silicon_reclassification_rules.md](silicon_reclassification_rules.md) | `scripts/reclassify_silicon.py` | 分类复核与进出口排序 |
| [silicon_indicator_tags_rules.md](silicon_indicator_tags_rules.md) | `scripts/apply_indicator_tags.py` | 指标标签维度抽取规则 |
| [silicon_output_check_rules.md](silicon_output_check_rules.md) | `scripts/check_silicon_output.py` | 输出检查规则 |

硅产业规则层级：

```text
Skill1 板块分类 (silicon_catalog_rules.md)
    -> Skill2 分类 + 筛选 (外部 selection_rules.docx)
    -> 分类复核 (silicon_classification_rules.md + silicon_reclassification_rules.md + classification_candidates_rules.md)
    -> 通用净出口计算 (calculate_net_exports.py)
    -> 确定性筛选 (silicon_selection_rules.md)
    -> 指标标签 (silicon_indicator_tags_rules.md)
    -> 输出检查 (silicon_output_check_rules.md)
```
## 数量平衡硬校验

进出口总量标题可能写作 `进口量/出口量/进口额/出口额`，也可能直接写作
`进口/出口/净出口`。最终产业筛选必须处理全部目录行，不能只依赖 Skill2
预先选中的结果；只要同一口径存在月度进口和出口，就应保留进口、出口以及
对应净出口，并筛除其余重复或聚合行。

每次 `apply_industry_selection.py` 保存前必须校验：`进出口` 大类下
`进口`、`出口`、`净出口` 三个子类的选中数量必须相等，否则流程直接失败。

## 看板前端规则同步

本目录规则文件是数据处理依据；看板前端展示规则以
`本地可视化dashboard/docs/排序规则.md` 和 `本地可视化dashboard/docs/看板图表开发规范.md`
为准。每次修改前端排序、归组、图表显示规则后，必须同步更新：

- 本项目根目录 `排序规则.md`
- `skills/dashboard-data-sorter/SKILL.md` 与 `README.md`
- `rules/import_export_rules.md`、`rules/volume_position_ratio_rules.md` 中与前端展示相关的段落
