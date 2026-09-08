# Langfuse Evaluation 接入设计（Phase 2 设计稿，未实施）

> 状态：**设计定稿，零代码改动**。回归基线 218 passed 不变。
> 范围：仅 Langfuse 已有 tracing（`ai_disambiguation` / `stock_targets` 两个 stage）
> 与 Verifier / golden / 人工结果的关联与 Evaluation 设计。
> 不修改：现有 tracing、Skill 业务规则、SQLite cache、Skill4、Prompt、workflow 输出、golden 内容。

---

## A. 当前 Verifier 数据结构（事实盘点）

### A1. 状态词汇（无字面 FAILED/PENDING）

| 层级 | 状态词 | 载体 |
|---|---|---|
| Golden case | `CONFIRMED` / `PENDING_HUMAN_REVIEW` | golden_cases.jsonl `expected_status` |
| Audit finding | `verdict`: PASS / REVIEW_REQUIRED / ERROR / AMBIGUOUS | audit_report.json `findings[]` |
| Audit finding | `final_disposition`: EXPECTED_TRANSFORMATION / CONFIRMED_ERROR / NEEDS_HUMAN_REVIEW / RULE_SPEC_MISSING / RULE_SPEC_AMBIGUOUS / IDENTITY_AMBIGUOUS / OBSERVABILITY_GAP | 同上 |
| Stage 迁移 | transition_status: ALLOWED / FORBIDDEN / REVIEW_REQUIRED / UNDEFINED | stage_transitions[] |
| 人工确认 | `Human decision`: CONFIRMED / UNRESOLVED（`CORRECTED` 语义体现在 human 大类/子类/选中列） | review pack xlsx |

- `CONFIRMED`（golden）产生条件：`provenance_confidence >= 1.0`，即派生变量且其规则 `APPROVED`（规则自动确认，非人工）。
- `PENDING_HUMAN_REVIEW`：audit-finding 候选 + provenance < 1.0 的派生变量。
- 最接近 FAILED 的是 `verdict="ERROR"` + `final_disposition="CONFIRMED_ERROR"`（注意：verdict=ERROR 有 2672 条，但 disposition=CONFIRMED_ERROR 为 0 条——影子审计不裁定，只标 REVIEW_REQUIRED）。

### A2. Golden case 结构（golden_cases.jsonl，13 字段，92 条/run）

```json
{"case_id": "golden_tin_TIN_003371e0e4caf189",
 "source_dataset": "20260831T062041Z_2f18aeedfeb6",
 "industry": "tin", "commodity": "TIN",
 "original_name": "韩国海关 碳酸锂净出口: 月度",
 "context": {"created_at_stage": "INDUSTRY_CURATION"},
 "expected_category": null, "expected_subcategory": null, "expected_selected": null,
 "expected_status": "CONFIRMED", "matched_keywords": [],
 "expected_rule_ids": ["DV_001"],
 "notes": "Derived variable provenance with APPROVED rule."}
```

- `case_id = golden_<industry>_<commodity>_<suffix>`，suffix 为 16-hex `physical_variable_id`（1 条历史回退为序号 `golden_tin_TIN_10`）。
- **`expected_category / expected_subcategory / expected_selected 全部为 null`** —— golden 集目前没有分类期望值，只有状态与规则 id。`classification_correct` 类评分当前无人可评（除 25 条人工外）。

### A3. 人工确认

- **唯一真实存在的人工确认：`priority_review_pack.xlsx`（25 行 CONFIRMED）**，表头含 `case_id, 原始指标, Human 大类, Human 子类, Human 是否选中, Human decision, Human notes`。
  - ⚠️ 其 `case_id = priority_tin_TIN_0..24` 是按 priority_score 排序的**序号，不稳定**；唯一回联键是 `原始指标`（original_name）。
- 设计中的导入流程（外部 Result_audit `import-review`）把 review xlsx → `golden_confirmations.jsonl`，结构为 `case_id, original_name, industry, commodity, human_category, human_subcategory, human_selected, human_notes, expected_status="CONFIRMED"`。**该流程从未在真实数据上落盘**（仅测试覆盖）。

### A4. Audit finding（15036 条/run，22 字段）

`finding_id`(= `audit_<run>:<validator>:<issue_type>:<physical_variable_id>`)、`audit_run_id`、`stage`、`validator`、`issue_type`、`severity`、`verdict`、**`physical_variable_id`**、`original_name`、`metric_family_key`、`series_key`、`actual`、`expected`、`evidence`、`rule_source`、`rule_hash`、`rule_reference`、`confidence`、`final_disposition`、`required_review_reason`、`recommended_next_action`。

### A5. 变量稳定身份（全链路核心事实，已实测验证）

| ID | 公式 | 验证 |
|---|---|---|
| `physical_variable_id`（审计/黄金主键） | `sha256(f"{raw_file_hash}\|{sheet_name.strip()}\|{int(col)}\|{name.strip()}")[:16]` | **3493/3493** 从 final 目录表重算命中 audit findings |
| curation.db `variable_id`（Skill2） | `sha256(f"{cataloged_hash}\|{sheet_name}\|{column_index}\|{original_name}")[:16]`（cataloged.xlsx 哈希，未归一化） | 500/500 重算命中存库值 |
| ai_assisted_curation `variable_id`（脚本本地） | `sha256(f"{sheet}\|{name}\|{unit}")[:16]` | 与上述两套**均不同**（公式三异：无 file_hash、用 unit 非 col、无归一化） |

- ⚠️ **curation.db variable_id ≠ audit physical_variable_id**（file_hash 不同源：cataloged.xlsx vs raw 输入文件）。审计在 final 输出上用 raw_file_hash 重算。
- `raw_file_hash` 对同一原始输入文件跨 run 稳定（实测 manifest == 现算）。
- 目录表（Excel）中**没有 variable_id 列**；`#` 列是按行递增的序号（不稳定）。目录表有 `Sheet Name`、`Col` 两列，足够按公式重算。

### A6. run 关联链（双轨 id）

- workflow 侧：`run_id = uuid4().hex[:12]`（cli.py），写入 `WORKFLOW_RUN_ID` env + `current_run_id.txt`；run_dir 名 = `<UTC时间戳>_<run_id>`。
- 审计侧：`workflow_run_id` = run_dir **完整目录名**；`audit_run_id = audit_<UTC>`。
- Langfuse trace id = `md5(短 run_id)`（observability 适配层）。
- **关联路径：run_dir 名末段 `_<12hex>` = 短 run_id → md5 → trace id；run_dir → audit/**。

---

## B. Generation ↔ Verifier 关联缺口（现状）

| 缺口 | 说明 |
|---|---|
| **B1. 无变量级 id** | generation metadata 仅有 `workflow_run_id / industry / stage / prompt_name / prompt_version / prompt_hash / model`（+extra: items_count/segment_prompt）。**没有任何 indicator/variable/case 级 id**（agent 2 确认）。 |
| **B2. 一对多粒度** | `ai_disambiguation` 一个 generation 承载最多 20 个变量的批；`stock_targets` 一个 generation = 一个 segment 的股票列表。Verifier 粒度是**变量**（physical_variable_id）与**股票**（6 位代码）。 |
| **B3. id 公式三套并存** | AI 脚本本地 id（sheet\|name\|unit）≠ curation.db variable_id ≠ audit physical_variable_id。AI 侧即使有 id 也对不上审计。 |
| **B4. AI 侧缺公式输入** | items 有 sheet/name/unit，**无 col**（load_rows 未保留列号进 item）且无 raw_file_hash。 |
| **B5. 人工数据无稳定键** | 25 条人工 CONFIRMED 的 case_id 是排序序号；回联只能靠 `原始指标` 名称（用户禁止仅靠名称匹配）。 |
| **B6. golden 无分类期望值** | `expected_category/subcategory/selected` 全 null → "做得是否正确"目前**无 ground truth 可判**（除 25 条人工）。 |
| **B7. trace 输入可恢复 items** | 补偿项：generation input=messages 已存 Langfuse，user payload 含完整 items（name/sheet/unit/freq + 本地 variable_id），**可做 run 内重建关联**。 |

---

## C. 推荐 stable case identity（设计核心）

### C1. 一级主键：`physical_variable_id`（复用审计现成体系）

```
physical_variable_id = sha256(f"{raw_file_hash}|{sheet.strip()}|{int(col)}|{name.strip()}")[:16]
raw_file_hash       = sha256(data_input/<原始文件>.xlsx)     # 跨 run 稳定（实测）
sheet / col / name  = 目录表行的 Sheet Name（节头行）、Col、Indicator Name
```

- 与 audit findings、golden case_id 后缀**字面一致**（已验证）。
- **顺序无关**：由 (file_hash, sheet, col, name) 确定，与行序/排序无关。
- **可复现**：任何持有目录表 + 原始文件的进程都能重算（3493/3493 验证）。
- **跨 run 稳定**：raw 文件字节不变即 id 不变。
- 生成位置建议（未来阶段）：AI 脚本 `build_item` 改用/附带上该 id（需 B4 的 col + file_hash 输入，属 tracing 改动，本阶段不做）。

### C2. 二级键：`case_id`（golden 体系，存在则用）

`golden_<industry>_<commodity>_<physical_variable_id>` —— dataset item id 直接用它。

### C3. 三级键：`evaluation_key`（跨 run 聚合）

```
evaluation_key = sha256(f"{physical_variable_id}|{prompt_version}|{prompt_hash}")[:32]
```
同一变量 + 同一 prompt 版本 → 同一 key，用于跨 run 的正确率聚合；不随 run 变化。

### C4. 幂等键：`score_id`（Langfuse upsert）

```
score_id = sha256(f"{evaluation_key}|{audit_run_id or workflow_run_id}")[:32]
```
同一 run 内重跑/回填幂等；不同 run 保留历史（不互相覆盖）。

### C5. 个股体系（stock_targets stage）

case identity = **6 位股票代码**（normalize_stock 强校验、去重、排序键，天然稳定）。
`evaluation_key = sha256(f"{code}|{industry}|{segment}|{prompt_version}|{prompt_hash}")[:32]`。
（当前无股票级人工/审计数据，本阶段只定接口。）

### C6. 禁止项

- 禁止以 `original_name` / `Indicator Name` 作为 join 键（跨 run 模糊匹配）。
- 唯一允许的例外：**run 内**重建关联时以 (sheet, name[, unit]) 精确匹配本 run 自己的 catalog（同一 run 内目录唯一、无跨 run 漂移风险），且必须记录匹配报告（命中/歧义/未命中），歧义与未命中不评分。

---

## D. Score schema（Langfuse `create_score`）

所有 score 挂到 `observation_id`（对应 generation），**自动与人工彻底分离**（score name 前缀即来源，禁止混用）：

### D1. 自动（source=verifier，无人工）

| score_name | data_type | 取值 | 来源 |
|---|---|---|---|
| `verifier_status` | CATEGORICAL | CONFIRMED / PENDING_HUMAN_REVIEW / CONFIRMED_ERROR / NEEDS_HUMAN_REVIEW / RULE_SPEC_MISSING / RULE_SPEC_AMBIGUOUS / IDENTITY_AMBIGUOUS / OBSERVABILITY_GAP / NOT_EVALUATED | golden expected_status / finding final_disposition |
| `verifier_verdict` | CATEGORICAL | PASS / REVIEW_REQUIRED / ERROR / AMBIGUOUS | finding verdict（按变量聚合） |
| `error_type` | CATEGORICAL | issue_type 列表（FREQUENCY_SOURCE_CONFLICT 等） | finding issue_type |
| `verifier_classification_correct` | BOOLEAN | true/false | 仅当该 case 存在**规则级期望分类**时产生（当前 golden 期望全 null → 实际基本不产生）；AI 结果 vs 确定性规则结果一致与否可另作 `drift_from_rule` |

### D2. 人工（source=human）

| score_name | data_type | 取值 | 来源 |
|---|---|---|---|
| `human_decision` | CATEGORICAL | CONFIRMED / CORRECTED / UNRESOLVED | review pack / golden_confirmations.jsonl |
| `human_classification_correct` | BOOLEAN | true/false | AI 结果 vs human 大类/子类（**人类 ground truth 唯一来源**） |
| `expected_output` | CORRECTION | `{"大类":..., "子类":..., "是否选中":...}` | 人工修正值（也是 dataset 的 expected_output） |

### D3. 每个 score 的 metadata（provenance）

`physical_variable_id`、`case_id`、`evaluation_key`、`workflow_run_id`、`audit_run_id`、`prompt_version`、`prompt_hash`、`model`、`score_source`、`evaluated_at`。

### D4. 用户点名的 5 个字段评估结论

| 字段 | 结论 |
|---|---|
| `classification_correct` | **要，但必须拆两个**：`verifier_classification_correct`（自动）与 `human_classification_correct`（人工），禁止合成一个 score |
| `verifier_status` | 要（CATEGORICAL，自动类） |
| `human_confirmed` | 改成 `human_decision`（CATEGORICAL CONFIRMED/CORRECTED/UNRESOLVED）——布尔"confirmed"无法表达修正 |
| `expected_output` | 要（CORRECTION/TEXT，人工类；同时作为 dataset item 的 expected_output） |
| `error_type` | 要（CATEGORICAL，自动类，取自 issue_type） |

---

## E. Human / Verifier 优先级规则

1. **HUMAN > VERIFIER**：同一 (case, metric) 同时存在人工与自动分时，人工分是 ground truth，自动分保留为独立 score（不覆盖），聚合指标只计人工。
2. **无人工时**：仅当 case 的期望值来自"规则 APPROVED + provenance_confidence=1.0"（golden CONFIRMED）且该变量**确实经过 AI**（出现在某 generation 中）才可计入自动正确率；规则自证且未过 AI 的 case **不计入** LLM 正确率。
3. **PENDING_HUMAN_REVIEW 永不判对错**：只可打 `verifier_status=PENDING_HUMAN_REVIEW`，不进任何正确率分母。
4. **冲突裁定**：`human_classification_correct=false` 与 `verifier_verdict=PASS` 并存 → 人工优先，冲突在 comment/metadata 标注。
5. **歧义/未匹配不评分**：run 内重建 join 出现一对多或未命中 → 不产生 score，写入回填报告（matched / ambiguous / unmatched 计数）。
6. **评分来源隔离**：score name 前缀（verifier_/human_）与 `score_source` 字段双重标识，聚合查询按前缀过滤，杜绝混用。

---

## F. 历史数据可回填范围（诚实评估）

| 数据 | 可回填项 | 限制 |
|---|---|---|
| **25 条人工 CONFIRMED**（priority_review_pack.xlsx） | ① 经 `原始指标` 归一化后 join 本 run 的 golden_cases → 得到 physical_variable_id + 人工期望值 → **dataset item + human 期望**（若找到对应 generation 则打 human 分） | join 键是名称（run 内唯一可接受）；`原始指标` 含引号等噪音需归一化；这些变量**没有** ai_disambiguation generation（rule 类），故 human_classification_correct 实际大多无 generation 可挂 |
| **golden_cases.jsonl**（各 run audit/golden/） | 稳定 case_id + expected_status → dataset 骨架 / verifier_status | expected_category 等全 null，无法评对错；仅状态 |
| **历史 audit findings**（run dirs audit/） | 变量级 verdict/disposition → verifier_status/error_type 的**潜在数据源** | **历史 run 无 Langfuse generation**（Langfuse 08-31 才接入）→ 没有可挂的 observation；除非把 score 挂 trace 级（不建议，粒度错） |
| **08-31 手工 AI runs 的 traces**（llm.ai_disambiguation ×10、llm.stock_targets ×10） | 可做 run 内重建：trace input items ↔ 该 run 目录（curation.db / audit）→ physical_variable_id → 挂 auto 分 | 手工 run 的 workflow_run_id（verify-ai-final 等）多为手动注入，需确认其是否有对应 run dir；无 run dir 的**不评分**（避免跨 run 名称匹配） |
| **curation.db / skill2_artifacts**（各 run） | 作为重建关联的中间层（variable_id ↔ name/sheet） | curation.db variable_id 与审计 id 不同源，只能当"名称→审计 id"的桥 |

**结论**：历史 correctness 评分能力有限（LLM generation 历史太短且无变量级 id）；**最有价值的回填是 dataset 层**（golden + 25 人工 → Langfuse Dataset），以及建立 correlation index（变量→physical_variable_id 的映射表，供后续 run 直接使用）。

---

## G. Dataset 形成机制（未来数据流）

```
FAILED / 漂移 / 待审 case（verdict=ERROR、AI 与规则冲突、PENDING_HUMAN_REVIEW 中高优先级）
   │  （外部 Result_audit 现有 priority-review / import-review 流程，不改）
   ▼
review pack xlsx → import-review → golden_confirmations.jsonl（case_id + human 大类/子类/选中）
   │  （本项目新增脚本 evaluation_dataset_export.py）
   ▼
Langfuse Dataset：
  create_dataset(name="<industry>-ai-classification-v1", input_schema, expected_output_schema)
  create_dataset_item(
      id=case_id,                          # 稳定
      input={"name","sheet","unit","freq","候选大类","候选子类","候选分类组合"},
      expected_output={"大类","子类","是否选中"},
      source_trace_id / source_observation_id,   # 回链产生该 case 的 generation
      status=ACTIVE, metadata={physical_variable_id, evaluation_key, prompt_version, prompt_hash, workflow_run_id},
  )
   │
   ▼（后续阶段）
run_batched_evaluation / Prompt 实验：dataset 作为输入，对比 prompt 版本正确率
```

- dataset 命名版本化：`<industry>-ai-classification-v{1,2,...}`，golden 内容更新开新版本，不覆盖。
- 历史回填：既有 golden_cases（含 25 人工）→ v1；此后每次新 run 增量补 item（幂等：id=case_id）。
- 与 golden 集内容互不修改（用户约束）：dataset 是 golden 的**投影**，不在 Result_audit 侧写回。

---

## H. 预计修改文件（未来阶段，本阶段零改动）

| 文件 | 改动 |
|---|---|
| **新增** `scripts/evaluation_backfill.py` | run 内重建关联（trace input × catalog/audit）→ physical_variable_id → 挂自动 scores；输出匹配报告 |
| **新增** `scripts/evaluation_dataset_export.py` | golden + 人工确认 → create_dataset / create_dataset_item |
| `workflow/observability.py` | 仅实现 `record_evaluation()`（接口见下）；**不动** tracing 机制（root/OTEL/use_span/usage_details/failure isolation） |
| `scripts/ai_assisted_curation.py`（Phase 3 加固，可选） | `build_item` 携带 col + raw_file_hash（或直接物理 id），generation metadata 增加变量级 id —— **属 tracing 扩展，本阶段明确不做** |
| `rules/README.md` | 「观测（Langfuse）」节补 Evaluation 小节（代码-文档同步约定） |
| `tests/test_observability.py` + 新增 `tests/test_evaluation_backfill.py` | record_evaluation 接口单测（fake client）+ 重建关联单测 |
| `.env`（可选） | 无新 key 需求（scores/datasets 复用 LANGFUSE_PUBLIC/SECRET_KEY） |

**明确不改**：`workflow/observability.py` 的 tracing 路径、`ai_assisted_curation.py`/`ai_stock_targets.py` 的 LLM 调用与缓存、Result_audit（外部只读）、golden 集、Skill4、workflow 输出。

---

## I. record_evaluation() 接口（定稿，仍 NotImplemented）

```python
def record_evaluation(
    *,
    physical_variable_id: str,          # 必填：一级稳定主键（C1）
    case_id: str | None = None,         # golden case_id（有则传，dataset item id）
    score_name: str,                    # D 表枚举；前缀 verifier_/human_ 与 source 必须一致
    value: float | str,                 # BOOLEAN→"true"/"false"；NUMERIC→float；其余 str
    data_type: str,                     # NUMERIC | CATEGORICAL | BOOLEAN | TEXT | CORRECTION
    source: Literal["verifier", "human"],
    workflow_run_id: str | None = None, # 缺省取 env WORKFLOW_RUN_ID（→ trace_id=md5(run_id)）
    audit_run_id: str | None = None,    # verifier 类必填；human 类可空
    observation_id: str | None = None,  # 对应 generation 观测 id；缺省由 correlation index 解析
    expected_output: dict | None = None,    # {"大类","子类","是否选中"}（human/expected）
    error_type: str | None = None,
    comment: str | None = None,
    metadata: dict | None = None,       # prompt_version / prompt_hash / model / evaluated_at 等
) -> None
```

内部实现要点（未来）：
- `evaluation_key = sha256(f"{physical_variable_id}|{prompt_version}|{prompt_hash}")[:32]`
- `score_id = sha256(f"{evaluation_key}|{audit_run_id or workflow_run_id}")[:32]`（幂等 upsert，C4）
- `trace_id = md5(workflow_run_id)`；`observation_id` 优先显式传入，否则经 correlation index 解析
- 校验：`score_name` 前缀与 `source` 一致，否则 ValueError；`source=verifier` 无 `audit_run_id` 时降级为 NOT_EVALUATED 注释
- 全程 best-effort（与现适配层一致），失败静默

---

## I-min. 最小实施方案（分阶段，实施时执行）

1. **Phase 2a（回填）**：`evaluation_backfill.py` —— 选定"有 trace + 有 run dir + 有 audit/golden"的历史 run → run 内重建 (generation item → physical_variable_id) → 挂 `verifier_status` / `verifier_verdict` / `error_type`；输出 matched/ambiguous/unmatched 报告；dry-run 先行。
2. **Phase 2b（人工）**：`record_evaluation()` 落地 + 把 25 条人工确认（名称归一化 join golden）导入为 `human_decision` / `expected_output` / `human_classification_correct`；E 节优先级规则实现。
3. **Phase 2c（dataset）**：`evaluation_dataset_export.py` —— golden + 人工 → Langfuse Dataset v1；此后每 run 增量。
4. **Phase 2d（加固，可选）**：AI 脚本原生携带 (col, raw_file_hash) → 直接生成 physical_variable_id 进 generation metadata，淘汰重建关联（**需放开"不修改 tracing"约束时再做**）。
5. 每阶段跑全量测试（基线 218 passed）+ 真实链路验证（回查 API，注意 ingestion ~15-30s 延迟）。

---

## 附：本设计依赖的已验证事实（2026-09-01 实测）

- `physical_variable_id` 公式在 final 目录表 3493/3493 命中 audit findings；raw_file_hash 跨 run 稳定。
- curation.db `variable_id` 公式 500/500 命中存库值；与审计 id 不同源（cataloged vs raw hash）。
- AI 脚本本地 variable_id（sheet|name|unit）与上述两套均不一致。
- Langfuse SDK 4.14.1：`create_score` 支持 `score_id`（幂等）、`observation_id`、`data_type`、`metadata`；`create_dataset_item` 支持 `id`、`source_trace_id`、`source_observation_id`、`expected_output`、`status`。
- 公共 API 回查用 camelCase（`parentObservationId` 等）；client 无 `get_trace`，用 GET `/api/public/traces/{id}` + Basic auth。
