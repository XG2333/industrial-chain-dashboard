# 个股标的生成 Skill

## 1. Skill 名称

`stock-target-curator` / 个股标的生成

## 2. 适用场景

用于从产业链上下游细分板块出发，生成该产业对应的股票池，并把每只股票映射到所属产业链环节。

当前支持的产业链：

- 硅产业链
- 锡产业链
- 锂电池产业链

## 3. 输入要求

- `--industry`：`silicon`、`tin` 或 `lithium`
- `--config`：股票映射配置文件，默认使用 `config/stock_targets.json`
- `--output`：输出 xlsx 路径

## 4. 输出格式

生成的 Excel 使用一个 `个股标的` Sheet，列固定为：

```text
序号 | 产业链 | 细分板块 | 所属环节 | 股票名称 | 股票代码 | 总市值(亿) | AI筛选原因
```

其中：

- `细分板块`：产业内的上下游板块，例如硅的“工业硅 / 多晶硅 / 硅片 / 电池片 / 组件”。
- `所属环节`：该股票实际对应的产业链环节。
- `总市值(亿)`：AI 返回的总市值（亿元，近似值）；候选池模式取自
  `config/stock_targets.json` 的 `market_cap`。缺失或非法时按 0 处理（排在板块最后）。
- `AI筛选原因`：AI 给出的筛选依据（候选池模式为备注说明）。
- 同一只股票可同时出现在多个细分板块中，因为其业务可能横跨多个环节。

## 5. 生成逻辑

### AI 筛选模式（默认，`--provider deepseek`）

1. 按 `config/stock_targets.json` 中 `industries.<产业>.segments` 逐板块调用
   DeepSeek 筛选代表性上市公司（`scripts/ai_stock_targets.py`）。
2. 提示词中提供板块业务范围与参考候选池（`stocks`，仅作参考，AI 可筛选也可
   补充自己确定代码准确的公司）。
3. AI 返回每只股票的：名称、代码、总市值（亿元，近似）、**AI 筛选原因**
   （结合主营业务关联度、行业地位、产能规模、资源储备等，具体有依据）。
4. 输出前校验：股票代码必须为 6 位数字、名称与原因非空、市值非法值回退 0；
   板块内按总市值降序排列。
5. **股票名称必须使用交易所证券简称**（如"华友钴业""宁德时代"），禁止使用公司
   注册全称（如"浙江华友钴业股份有限公司"）；名称以 AI 返回为准，生成脚本不改写。
6. 每个细分板块受 `requirements` 数量约束（锂电 5~20 只/板块）。
7. 结果按「产业|板块」缓存到 SQLite（默认 `output/stock_targets_ai_cache.db`），
   重复运行命中缓存不再调用 AI；`--force-refresh` 可强制重筛。

### 候选池模式（`--provider mock`，离线验证用）

直接输出 `config/stock_targets.json` 中 `stocks` 参考候选池，原因列取备注，
不调用 AI。用于测试与离线环境。

### 板块说明

- 锂电板块：`锂矿锂盐`（锂矿与锂盐合并为一类，避免交叉个股重复）、三元正极、
  磷酸铁锂正极、负极、隔膜、电解液、铜箔铝箔、电池&电芯、储能&集成、新能源车。
- 输出前按“产业链 → 细分板块 → 总市值（降序）→ 股票代码”排序。
- 同一产业、同一细分板块、同一股票代码只保留一条记录。

## 6. 使用方法

```powershell
& "C:\Users\11\Documents\Selecting skill\.venv\Scripts\python.exe" `
  skills\stock-target-curator\scripts\generate_stock_targets.py `
  --industry silicon `
  --no-strict `
  --output output\个股标的_硅.xlsx
```

## 7. 文件结构

```text
skills/stock-target-curator/
  SKILL.md
  README.md
  config/
    stock_targets.json
  scripts/
    generate_stock_targets.py
  tests/
    test_generate_stock_targets.py
```

## 8. 当前接入

Skill3 已接入 `多skill联动` 的 `configs/workflow.yaml`、`workflow_lithium.yaml`、`workflow_tin.yaml`、`workflow_silicon.yaml`，在净出口计算后执行。`scripts/run_industry_pipeline.py` 也会在完整流程中调用本 Skill。
