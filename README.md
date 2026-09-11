# 产业链研究数据处理与可视化看板

一个面向产业研究的端到端工程：从多 Sheet Excel 数据库生成指标目录，执行确定性分类、标签、净出口/复合指标计算、主筛选与二次筛选，再由 FastAPI 和 React/ECharts 组成的看板按需展示。

> 本仓库只包含程序、规则、测试和空白配置。真实产业数据、股票池、数据库、缓存、日志及 API Key 均不在仓库中。

## 系统能力

- 支持锂、锡、硅三类产业链工作簿。
- 根据 Sheet、列、频率、单位与指标名称生成统一指标目录。
- 将指标分类为价格、成本利润、库存、供给、需求、进出口、平衡等类别。
- 确定性匹配进口/出口并生成净出口，校验三类选中数量平衡。
- 生成成交量、持仓量与成交持仓比等复合指标。
- 使用规则完成主筛选和面向看板的日/周频二次筛选。
- 可选调用大模型处理模糊分类；无密钥时可使用 `mock` 模式。
- FastAPI 按工作簿修改时间缓存，React 前端按视口懒加载图表数据。

## 仓库结构

```text
.
├─ apps/dashboard/              # FastAPI 后端与 React/ECharts 前端
├─ packages/selecting-skill/    # 变量分类、规则编译、SQLite 审计与导出
├─ pipeline/                    # 三产业数据流水线、业务规则、Skill3/Skill4
├─ scripts/                     # 仓库级安装、配置、处理与启动入口
├─ data/                        # 私有输入和生成结果；内容不进入 Git
├─ runtime/                     # 运行记录、数据库和缓存；内容不进入 Git
└─ docs/                        # 架构、隐私和发布说明
```

更详细的模块职责见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 环境要求

- Python 3.12+
- Node.js 18+
- Windows PowerShell 5.1+ 或 PowerShell 7+

## 快速开始

```powershell
./scripts/setup.ps1
```

脚本会创建 `.venv`、安装 Python 依赖、安装并构建前端，然后从空白模板生成本地 `.env`。

将你有权使用的原始工作簿放入 `data/raw/`：

```text
碳酸锂数据库.xlsx
锡产业链数据.xlsx
硅产业链数据.xlsx
```

执行离线确定性处理：

```powershell
.\.venv\Scripts\python.exe scripts/process_all.py --provider mock --parallel 3
```

启动看板：

```powershell
./scripts/run_dashboard.ps1
```

浏览器访问 `http://127.0.0.1:8000`。

## 可选 AI 功能

编辑本地 `apps/dashboard/.env`，按需设置 `DEEPSEEK_API_KEY`。不要把 `.env` 提交到版本库。

```powershell
.\.venv\Scripts\python.exe scripts/process_all.py --provider deepseek --ai
```

AI 只用于候选不唯一或单位冲突等模糊项目；确定性规则、候选集合与最终校验仍是结果边界。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest packages/selecting-skill/tests pipeline/tests apps/dashboard/tests
Set-Location apps/dashboard/frontend
npm test
```

## 数据与隐私

请先阅读 [docs/DATA_PRIVACY.md](docs/DATA_PRIVACY.md)。提交前运行：

```powershell
./scripts/prepublish_check.ps1
```

## 项目边界

- 仓库没有附带任何数据源授权；使用者必须自行确认数据许可。
- 股票标的配置仅含三个公开演示条目，不构成投资建议；正式使用时请自行维护。

## 开源许可证

本项目采用 [Apache License 2.0](LICENSE) 发布。许可证只覆盖本仓库中的程序、规则和文档，不授予任何外部数据源、商标或第三方内容的使用权。
