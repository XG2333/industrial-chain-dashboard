# Skill4：看板数据排序

## 1. Skill 名称

`dashboard-data-sorter` / 看板数据排序

## 2. 目的

对 `多skill联动` 项目中由 Skill1 / Skill2 / Skill3 处理后的数据文件（例如
`output/*_workflow_ai.xlsx`）按 [排序规则.md](../../排序规则.md) 重排
`指标目录` sheet 的行。

规则文件只作为依据，本 Skill 不修改指标分类字段，也不改动原始数据 sheet。

## 3. 输入输出

输入：

- 一个包含 `指标目录` sheet 的 xlsx；
- 目录列为：`# / Sheet Name / Freq / Col / Indicator Name / Unit / 板块 / 大类 / 子类 / 数据性质 / 是否选中 / 状态说明 / 指标标签`。

输出：

- 重新排好序的 xlsx，只重排 `指标目录` 的行；
- 最终输出会在 `Indicator Name` 右侧新增 `指标名称归一化` 列；
- 其他 sheet 原样保留。

## 4. 排序规则

职责边界：Skill4 是唯一业务排序真源；Dashboard 展示层按根目录
`排序规则.md` 使用 `min(catalog_order)` 决定大类、子类、频率和 Display Block
顺序，不再使用前端固定业务排序表覆盖 Excel 顺序。

1. 不修改目录单元格内容；sheet 段按指标规则顺序排列，sheet 名称随所在数据段整体移动，段内数据行再按规则排序。
2. 大类顺序：价格 -> 成本利润 -> 库存 -> 供给 -> 供应 -> 需求 -> 进出口 -> 平衡 -> 其他；未列出大类排在最后。
3. 子类顺序按 [排序规则.md](../../排序规则.md) 第 3 节；价格大类固定为 价格 → 现货价格 → 期货价格 → 现货价差 → 基差 → 月差；未列出子类排在对应大类最后。
4. 价格大类的成交量 / 成交 / 持仓 / 持仓量 / 成交持仓比组成复合组，复合组排在价格大类所有普通子类之后。
5. 复合组内部顺序固定为：成交量 -> 成交 -> 持仓 -> 持仓量 -> 成交持仓比。
6. 子类内频率顺序为：日度 -> 周度 -> 月度 -> 季度 -> 年度；半年频实际不存在，忽略。
7. 同类指标使用 `chartGrouping.ts` 的标题归一化逻辑归组；组内先按 当期/实际，再按 预测，最后按 中国 -> 其他地区 排序。
8. 同一大类/子类/频率下，中国相关指标排最前（含 中国海关、国产、国内、省份/港口）；未识别/未指定排中间；全球、海外、外国国家统一排最后。括号内出现 `CIF中国`、`中国现货` 等不改变来源判定，括号外指向外国国家或外国产品时仍按外国处理。
9. 目录行排序时，进出口仍按 进出口 -> 净出口 -> 进口 -> 出口 顺序；前端展示层按 [排序规则.md](../../排序规则.md) 第 7.1 节，将同一指标进口/出口/净出口合并为一行。
10. 全部目录行都参与排序：每个 sheet 段内选中行在前，未选中行在后；统计行和伪指标行放到整个目录最下方。
11. 排序后保留并重建目录跳转超链接：sheet 表头跳到对应 sheet 的 A1，指标名按 `Col` 跳到对应数据 sheet 列首行。
12. 在同一大类/子类/频率/中国外国/同类指标分组下，按板块内部产业链节点顺序作为最终收尾排序；节点规则见 `config/sector_node_rules.json`，支持严格上下游、平行路线、同级并列和指标类型 policy；节点冲突或无法匹配时稳定回落原 `catalog_order`。
14. 最终输出可选新增连续两列：`指标名称归一化` 和 `排序说明`；排序说明由节点解析结果和排序 policy 模板化生成，不逐行调用大模型。
15. 排序 policy 层：根据 `大类 + 子类` 选择指标类型策略，产业节点知识仍只维护在 `config/sector_node_rules.json`：
    - 现货价格：产业阶段 → 平行分支 → 产品 → 规格
    - 期货价格：期货品种 → 合约角色/结构 → 合约期限
    - 价差/基差/月差：标的对象 → 价格关系类型 → 合约/市场结构
    - 产量/产能：产业阶段 → 生产节点 → 产品
    - 开工率：产业阶段 → 生产/加工环节 → 产品
    - 库存：产业阶段 → 产品节点 → 库存位置/性质
    - 成本：加工环节 → 成本对象 → 产品
    - 利润：利润产生环节 → 加工环节 → 产品
    - 需求：需求链阶段 → 消费节点 → 产品
    - 进出口：产品节点 → 进口 → 出口 → 净出口
    - 平衡：产业阶段 → 平衡对象 → 产品节点
    - 其余子类走默认排序，最终始终以 `original_catalog_order` 兜底。
16. 硬优先级：大类、子类固定顺序必须先于 policy 生效；policy 只能在大类、子类、频率等总体排序维度相同后，在同一 bucket 内细排，不得跨大类或跨子类改变顺序。
17. 排序后执行 `SORT_INVARIANT_VIOLATION` 校验：同一 sheet、同一选中组内若出现大类或子类逆序，直接报错并列出 Sheet、指标、大类、子类、当前行与前一行，不再静默输出 Excel。
18. 最终 `排序说明` 按相邻“产业指标组”生成业务自然语言，只描述产业链环节、上下游/平行/同级/规格关系及排序依据，不输出 node_id、policy 内部键等机器字段；无可靠关系时写“当前未识别到明确上下游关系，本组保持既定展示顺序”。
19. 同一硬 bucket（Sheet + 是否选中 + 大类 + 子类 + 频率）内，`指标名称归一化` 必须形成连续 block；region/当期/规格等只能在 block 内部排序，不得拆散名称 block。新增 `NAME_GROUP_CONTIGUITY_VIOLATION` 校验。
20. 写入 `指标标签` 的 `product_family` 与 `display_group`：当前唯一业务同行组为 `display_group=港口库存`，由 Skill4 结构化写入；Dashboard 不通过标题关键词识别库存业务知识。可售/贸易商/外采/厂内/在途/矿山样本/锂盐厂样本等库存不设置 display_group，继续按普通 singleton 规则展示。
14. 排序重写目录前会清除旧合并单元格区域，避免原表头合并区域盖住排序后移动进来的指标名、单位、板块等单元格。
15. 最终目录输出时，在 `Indicator Name` 右侧新增 `指标名称归一化` 列，值为 `normalize_indicator_title(...)`；归一化结果为空时回退原始指标名。该列只影响最终输出，中间 workflow 排序不新增，避免后续筛选/AI 脚本列位移。
15. 本 Skill 的排序依据是根目录 `排序规则.md`，该文件与 `本地可视化dashboard/docs/排序规则.md` 同步；每次修改前端排序、归组或行排布规则后，必须同步更新本文件、`README.md` 和 `排序规则.md`。

## 5. 使用方式

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  skills\dashboard-data-sorter\scripts\sort_catalog.py `
  --input output\碳酸锂数据库_workflow_ai.xlsx `
  --output output\碳酸锂数据库_workflow_ai_sorted.xlsx `
  --add-normalized-column
```

不传 `--output` 时默认写到 `<输入文件名>_sorted.xlsx`。

## 6. 测试

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  -m pytest skills\dashboard-data-sorter\tests -q
```

## 7. 文件结构

```text
skills/dashboard-data-sorter/
  SKILL.md
  README.md
  scripts/
    sort_catalog.py
  tests/
    test_sort_catalog.py
```

## 8. 后续接入

已接入 `configs/workflow.yaml` 以及锂电、锡、硅三个产业 workflow，作为每个
workflow 的最后一步，在 Skill3 生成个股标的后自动执行。也可作为独立脚本运行。
`scripts/run_industry_pipeline.py` 会在最终输出生成后再执行一次 Skill4，
确保筛选/AI 阶段新增的行也保持排序。
