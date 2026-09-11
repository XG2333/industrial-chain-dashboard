# Skill3：个股标的生成

## 定位

Skill3 负责把产业链上下游细分板块映射到具体个股，并输出可供市场看板使用的股票池表格。

## 当前能力

- 支持硅、锡、锂电池产业链。
- **AI 筛选**（`--provider deepseek`）：逐板块调用 DeepSeek 筛选代表性上市公司，
  输出 `股票名称`、`股票代码`、`总市值(亿)`、`AI筛选原因`；结果 SQLite 缓存。
- 候选池模式（`--provider mock`）：输出 `config/stock_targets.json` 参考候选池，
  不调用 AI，用于离线验证。
- 每个细分板块内按总市值从高到低排序。
- 自动去重：同一产业链、同一细分板块、同一股票代码只保留一条。
- 锂电板块 `锂矿锂盐` 已合并（锂矿与锂盐交叉个股只保留一条）。
- 按 `config/stock_targets.json` 中的 `requirements` 约束每个细分板块数量。
- 输出到 xlsx 的 `个股标的` Sheet（`AI筛选原因` 列）。

## 运行

```powershell
& "<local-documents>\Selecting skill\.venv\Scripts\python.exe" `
  skills\stock-target-curator\scripts\generate_stock_targets.py `
  --industry silicon `
  --output output\个股标的_硅.xlsx
```

## 测试

```powershell
& "<local-documents>\Selecting skill\.venv\Scripts\python.exe" `
  -m pytest skills\stock-target-curator\tests -q
```

## 后续

1. 已接入 `多skill联动` 四个 workflow 配置，并在完整流程中通过 `run_industry_pipeline.py` 自动执行。
2. 后续可增加 AI 候选生成，但必须经过环节归属、股票名称（统一使用交易所证券简称，如"华友钴业"而非"浙江华友钴业股份有限公司"）、股票代码校验。
3. 后续可增加实时行情/财务数据的字段补齐。
