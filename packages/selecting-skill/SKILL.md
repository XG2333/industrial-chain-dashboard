# Financial Variable Curation Skill

## 1. Skill 名称
financial-variable-curation / Selecting_skill

## 2. 适用场景
跨行业金融及产业 Excel 数据变量筛选，用于变量画像、语义分类、自然语言规则编译、确定性筛选和结果 Excel 导出。

## 3. 输入要求
- Excel 业务数据文件（.xlsx）
- 自然语言筛选规则文本（.txt 或 .md）
- 可选 LLM Provider 配置：`LLM_PROVIDER=mock|openai`

## 4. 输出说明
- `inspect` 输出变量画像与质量摘要
- `classify` 输出分类结果、llm_calls、cache、review items
- `validate-rules` / `compile-rules` 输出规则审计与版本化 rule_set
- `select` 输出 selection_run 与 variable_selection_results
- `export-selection` / `pipeline` 输出最终结果 Excel、审计文件和 pipeline summary

## 5. 工作流阶段
Excel 探查 → 数据库持久化 → AI 变量分类 → 规则解析/校验/编译 → 确定性筛选 → Excel 导出 → 审计摘要

## 6. CLI 使用方法
```powershell
python -m financial_variable_curation inspect --input data/business_data.xlsx --database data/curation.db
python -m financial_variable_curation classify --run-id <run_id> --provider mock --database data/curation.db
python -m financial_variable_curation validate-rules --rules input/selection_rules.txt --provider mock
python -m financial_variable_curation compile-rules --rules input/selection_rules.txt --name business_rules --version 1 --provider mock
python -m financial_variable_curation select --run-id <run_id> --rule-set business_rules --rule-version 1 --allow-validated-rules
python -m financial_variable_curation export-selection --selection-run-id <selection_run_id> --output output/selected.xlsx
python -m financial_variable_curation pipeline --input data/business_data.xlsx --rules input/selection_rules.txt --provider mock --output output/selected.xlsx
```

## 7. API Key 配置
复制 `.env.example` 为 `.env`，设置 `OPENAI_API_KEY`；`REAL_LLM_ENABLED=true` 后才允许 OpenAI Provider。

## 8. Mock 模式
`--provider mock` 完全离线，不读取 API Key，不调用网络。

## 9. 真实 API 模式
`--provider openai` 必须同时满足 `REAL_LLM_ENABLED=true` 且配置 `OPENAI_API_KEY`；默认最多 20 个变量，可传 `--classification-limit` / `--limit`。

## 10. dry-run
`pipeline --dry-run`、`select --dry-run`、`export-selection --dry-run` 只检查配置和输入，不调用真实 API，不写正式结果，不生成正式 Excel。

## 11. 失败恢复
当前 `pipeline_steps` 已记录步骤状态，`--resume-run-id` 参数已预留；完整按步骤恢复仍需在后续版本中完善。

## 12. 规则文件写法
规则支持类别优先级、频率优先级、缺失率过滤、去重、人工复核、最大数量等自然语言短语；Mock 只能识别测试短语，正式业务规则建议使用 OpenAI Provider 并人工复核。

## 13. 当前限制
- 多层表头、合并单元格、复杂多表布局目前只能标记复核或 UNSUPPORTED
- 不会跨 Sheet 对齐日期，不会统一频率
- `run` 命令保留旧链路；完整新编排器当前通过 `pipeline` 命令使用

## 14. 安全和隐私说明
- API Key 只从环境变量读取，不写入代码、日志、数据库或 artifact
- 原始 Excel 永不被修改
- 导出层不会重新调用 LLM 或重新执行筛选规则

## 15. 示例命令
```powershell
python -m financial_variable_curation pipeline --input input/business_data_test.xlsx --rules input/selection_rules_minimal.txt --provider mock --output output/business_data_mock_selected.xlsx
```

## 16. 目录 sheet 标记规则
`directory-mark` 会把筛选结果写回 Excel 第一个 sheet（通常为“目录”），并遵循以下规则：

- 如果“目录”sheet 已有内容，不覆盖原有列顺序和原有行顺序。
- 只追加缺少的筛选列：`大类`、`子类`、`数据性质`、`是否选中`、`状态说明`。
- Skill2 中间产物可能仍包含 `置信度`，但完整 workflow 会在最终输出前删除该列，最终目录不保留置信度。
- 指标名称列会自动添加指向对应数据 sheet 的超链接。
- 已有超链接会被保留；目标文件被占用时自动写为 `__tmp_<随机8位>.xlsx`。
- 如果“目录”sheet 为空，则自动生成标准列结构：`序号`、`指标名称`、`所属Sheet`、`单位`、`频率`、筛选结果列。

## 17. 大类和子类分类体系
目录输出中的“大类”按以下中文分类：

- 价格
- 成本利润
- 库存
- 供给
- 供应
- 需求
- 进出口
- 平衡
- 其他

“子类”按指标名称细分，常用值包括：

- 现货价格
- 期货价格
- 现货价差
- 基差
- 月差
- 成本
- 利润
- 库存
- 仓单
- 库存天数
- 库存指数
- 产能
- 加工费
- 储量
- 产量
- 开工率
- 进口
- 出口
- 出货量
- 招标
- 中标
- 成交量
- 持仓
- 销量
- 平衡
- 数量

其中“产能、储量、产量、开工率、加工费”归入“供给”或“供应”大类。

补充分类规则：

- 持仓及交易者数量归入“价格”大类，子类为“持仓”。
- 期现价差归入“价格”大类，子类为“基差”。
- 出口盈亏、进口盈亏归入“成本利润”大类，子类为“利润”。
- 销量指标归入“需求”大类，子类为“销量”。
- “加工费”归入“供给 / 加工费”。
- “出货量”相关指标归入“需求 / 出货量”。
- “招标中标”拆分为“招标”、“中标”两个子类。
- 进口额、出口额、进口总额、出口总额、金额、总值等贸易金额归入“价格 / 贸易金额”。
- 进口/出口均价、单价及单位价格为 `元/吨`、`美元/吨`、`元/kg`、`元/Wh` 的指标归入“价格 / 现货价格”。
- 进口/出口利润、盈亏优先归入“成本利润 / 利润”。
- 进口量、出口量、净进口量、净出口量等数量指标才归入“进出口 / 进口、出口、净出口”。
- 名称含“平衡”的指标统一归入“平衡”大类，子类固定为“平衡”。
- 锂电数据中的“氯化锂”归入“其他锂盐”板块。

分类依据优先使用指标名称关键词，同时结合单位判断；例如 `元/吨`、`美元/吨` 等价格类单位会优先归入“价格”，含“盈亏/价差/基差/升贴水”的指标归为“价格/现货价差”。

## 18. “是否选中”确定性筛选规则

“是否选中”按以下规则确定，不满足规则的指标统一设为“否”：

公共价格规则：
- 价格/期货价格/成交量/持仓仅保留主力合约、01合约、05合约、09合约。
- 月差仅保留 01-05、05-09、09-01；基差/期现价差仅保留当月或现货升贴水；现货价差保留。
- 同一价格指标只保留最高频（日度 > 周度 > 月度 > 季度 > 年度）。
- 指标名先做符号、空格、标点、频率归一化后再归组，避免 `-平均价`、`- 平均价`、括号差异导致同一指标被拆开。
- 频率分组使用独立 `frequency_comparison_key`，对参与比较的文本做 Unicode NFKC、全半角、空格、连字符/冒号/括号差异、上下标字符归一化；键保留数据来源、板块、大类/子类、规格、单位、地域、统计口径、状态等业务维度，避免 `Li₂O/Li2O` 无法匹配，也避免 `6%-7%` 与 `7%-8%` 被错误合并。

成本利润：
- 同一成本利润指标存在多频率时仅保留最高频；同频重复只保留一条。

库存与供需：
- 仓单仅保留日度总量“小计”；其余库存仅保留周度、月度。
- 供给、需求仅保留日度、周度、月度。
- 供给大类的同比、环比指标不保留。

同比、环比、占比：
- 所有含“同比”、“环比”、“占比”的指标统一筛除。

进出口：
- 进出口均价、进口均价、出口均价、净出口均价统一筛除。
- 进口额、出口额、净出口额、进口金额、出口金额、净出口金额、进口总额、出口总额、总额、总值、金额等金额类指标统一筛除。
- 同一进出口指标只保留进口、出口、净出口三类总量中的月度数据，并且必须成对存在。
- 金额类指标不参与配对，也不参与净出口计算。
- 净出口只基于“进口、出口都存在”的数量型月度口径计算。

成交与持仓：
- 成交量与持仓量必须一一对应，缺少对手方的一侧不保留。
- 如果同一合约已有成交量和持仓量但没有“成交持仓比”，会自动补齐“成交持仓比”并选中。

通用去重：
- 同一指标归一化后只保留一条；锂电额外对“储能电芯库销比”忽略“总计/合计”后去重。

未覆盖的指标默认“否”。当前项目级公共规则实现在 `多skill联动/scripts/selection_utils.py`、`import_export_rules.py`、`volume_position_ratio.py`；产业专属规则见 `lithium_selection_rules.py`、`tin_rules.py`、`silicon_selection_rules.py`。

## 19. 前端展示同步

本 Skill 的分类和筛选规则不因前端展示改变；前端展示层按
`<local-documents>/本地可视化dashboard/docs/排序规则.md` 执行：

- “进出口”大类不拆成三个子类按钮，同一指标进口/出口/净出口合并为一行，行内顺序为 进口 -> 出口 -> 净出口。
- 价格大类中“成交量、成交、持仓、持仓量、成交持仓比”统一显示为“成交持仓”复合组。

修改本 Skill 或上游规则后，必须同步更新本文件及 `多skill联动` 对应规则 md。

## 规则文件格式
支持 `.txt`、`.md` 和 `.docx`。Word 规则通过 `inspect-rules` 提取为规范文本后进入 `validate-rules` / `compile-rules`，不会把 Word 二进制直接发送给 LLM。

```powershell
python -m financial_variable_curation inspect-rules --rules input/selection_rules.docx
```
