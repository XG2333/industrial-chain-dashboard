# Skill4：看板数据排序

负责对 `多skill联动` 中其他 Skill 处理后的 Excel 目录 sheet 重新排序。

规则依据：[排序规则.md](../../排序规则.md)。

主要行为：

- 不修改目录内容，sheet 段按规则顺序排列，sheet 名称随数据段移动，段内数据行再排序；
- 大类、子类、频率、同类指标、当期/预测、中国/其他地区均按规则处理；
- 每个 sheet 段内选中行在前、未选中行在后，统计行和伪指标行放整个目录最下方；
- 保留并重建“点击指标跳转到对应 sheet”的超链接；
- 同一子类下中国相关指标排前，外国/全球/海外排后；
- 括号内 `CIF中国/中国现货` 不作为中国依据，括号外指向外国时按外国处理；
- 子类/频率/国家/同类指标都相同时，按板块内部产业链节点顺序收尾排序；
- 可选输出连续两列：`指标名称归一化`、`排序说明`；排序说明为模板生成，不逐行调用大模型；
- 排序 policy 层按 `大类+子类` 选择现货/期货/价差/产量/库存/成本/利润/需求/进出口/平衡等策略，产业节点知识只维护一次；
- 大类、子类固定顺序为硬优先级，policy 只能在同 bucket 内细排；排序后会执行 `SORT_INVARIANT_VIOLATION` 校验；
- 最终 `排序说明` 为面向业务的自然语言，不输出 node_id、policy 内部键等机器字段；
- 同一硬 bucket 内 `指标名称归一化` 必须连续，region/当期/规格只在名称 block 内部排序；
- 写入 `指标标签` 的 `product_family` 与 `display_group`：当前唯一业务同行组
  为 `display_group=港口库存`，由 Skill4 结构化写入，Dashboard 不通过标题关键词
  识别；其他库存继续按普通 singleton 规则展示；
- 排序重写目录前会清除旧合并单元格区域，避免排序后指标名、单位、板块被旧合并区域盖住；
- 最终输出会在原指标名称右侧新增 `指标名称归一化` 列，为空时回退原始指标名；
- 只重排 `指标目录`，不改指标分类字段和其他数据 sheet。
- 最终输出对目录表设置表头筛选索引（AutoFilter，A1 至末行末列）：所有列可下拉
  筛选；`是否选中` / `二次筛选是否保留` 等 是/否 列的筛选下拉直接显示
  `是` / `否` 及各自指标数量。
- 目录行排序时进出口仍按子类顺序；前端展示层按根目录 `排序规则.md` 将同一指标进口/出口/净出口合并为一行。
- 复合组 role 排序仅对 `MATCHED`（配对成功）组生效：未配对（`INCOMPLETE`）的
  进出口/成交持仓行 role 与普通行一致（9999），不会以 role=0 插队到板块最前；
  段排序取段内最小排序键（`min(data_sort_key)`），未配对行不再把所在段拉到最前。
- 排序层级（`data_sort_key` 硬顺序，与根目录 `排序规则.md` 一致）：
  `板块 → 大类(MAJOR_ORDER) → 复合组 → 复合 role → 大类内子类(SUB_ORDER) →
  频率 → 业务块 → 产品族 → 地区 → 当期/预测 → 来源 → 规格 → 名称`。
  大类层是板块内的硬顺序（价格 → 成本利润 → 库存 → 供给 → 需求 → 进出口 → 平衡），
  必须保留：跨大类直接比较各 `SUB_ORDER` 的独立索引没有业务依据
  （如"库存"子类索引 0 会排在"现货价格"索引 1 之前）。
- 同 rank 板块必须有次级键（`SECTOR_SUB_RANK`）：板块一级排序用
  `(SECTOR_RANK, SECTOR_SUB_RANK)`，同 rank 板块缺次级键时段的排序会按大类
  交错（如磷酸铁锂/磷化工链）。新增同 rank 板块必须同步补充次级键。

规则同步：根目录 `排序规则.md` 与 `本地可视化dashboard/docs/排序规则.md` 保持一致；每次修改看板排序或前端归组规则后，必须同步更新本文件、`SKILL.md` 和 `排序规则.md`。

运行脚本：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  skills\dashboard-data-sorter\scripts\sort_catalog.py `
  --input output\硅产业链数据_workflow_ai.xlsx `
  --add-normalized-column
```

测试：

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  -m pytest skills\dashboard-data-sorter\tests -q
```
