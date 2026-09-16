# 智能能力集成报告

## 结论

已在不改动既有 SQL、数据处理逻辑、API 契约和 Dashboard 界面的前提下，新增一个默认关闭的 `packages/industry-intelligence` 旁路包。它把 RAG、向量检索、Function Calling、LangGraph 和 MCP 封装为可选能力；现有项目启动时不会导入、安装或运行这些能力。

## 已完成内容

- RAG：仅索引 `docs/`、`pipeline/docs/`、`pipeline/rules/` 下的 Markdown/TXT 规则文档；保留来源路径、行业和文档类型元数据。
- 向量库：默认使用本地 SQLite（混合向量相似度与词项重合度）；可选 Chroma 持久化后端。运行产物只写入 `runtime/intelligence/`。
- Function Calling：建立统一的只读工具注册表，提供知识检索、规则文档清单、指标目录和工作流运行状态四类工具；禁止任意 SQL、写文件、执行 Shell、启动流水线或网络请求。
- LangGraph：提供“检索 → 显式工具执行 → 汇总”的旁路图，不替换原 YAML 工作流。
- MCP：以 stdio 方式暴露同一组只读工具和行业规则资源；不会因导入包或启动 Dashboard 而自动启动。
- 隐私：未加入 API Key、真实观测数据或私有运行产物；新增 `.env.example` 只包含占位配置。

## 具体应用位置与工作流程

新增能力集中在 `packages/industry-intelligence/src/industry_intelligence/`，与既有 `pipeline/`、`apps/dashboard/` 平行部署。它们之间的关系如下：

```text
规则文档 docs/ + pipeline/rules/
              │
              ▼
       rag.py / chunking.py       ← 只读、可重复索引
              │
              ▼
 vector_store.py（SQLite 默认 / Chroma 可选）
              │
       ┌──────┼─────────┐
       ▼      ▼         ▼
    RAG 检索  LangGraph  Function Tools
                         │
                    OpenAI Responses / MCP
```

### RAG 与向量库

- `rag.py` 负责扫描批准的规则和说明文档，调用 `chunking.py` 切分文本，并将来源路径、行业、文档类型写入索引。
- `embeddings.py` 默认使用离线确定性 Hash embedding，确保无外部网络也可运行；配置 OpenAI embedding 时才会产生外部调用。
- `vector_store.py` 提供统一存储接口：小规模开源仓库使用 SQLite，较大语料可切换 Chroma。索引和审计数据位于 `runtime/intelligence/`，不进入 Git。
- 该流程不读取原始观测数据，不改写 Excel，也不参与 SQL 计算；数值结果仍由原有 pipeline 负责。

### Function Calling 工具层

`domain_tools.py` 是唯一的领域工具注册入口，当前四个工具分别应用于：

| 工具 | 作用 | 数据边界 |
| --- | --- | --- |
| `search_industry_knowledge` | 检索规则、口径和指标说明 | 仅已索引文档 |
| `list_rule_documents` | 查看可用规则文档 | 仅批准目录 |
| `get_indicator_catalog` | 读取处理后工作簿的指标目录 | 只读 catalog sheet，不读原始观察表 |
| `get_pipeline_run_status` | 查看流水线运行摘要 | 只读运行元数据 |

工具定义同时生成 OpenAI Responses API schema 和 MCP schema，因此两种调用方式共享同一套权限校验、参数校验和审计记录。没有任意 SQL、写文件、执行 Shell 或启动流水线的工具。

### LangGraph

`graph.py` 将研究型问答编排为三个旁路节点：

1. `retrieve`：从 RAG 索引获取带来源的上下文；
2. `tools`：仅执行调用方明确指定的只读工具；
3. `synthesize`：将检索结果和工具结果汇总成可审阅文本。

它用于规则解释、数据口径核查和运行状态复核，不替换 `pipeline/workflow/cli.py` 的 YAML 步骤执行器。

### MCP

`mcp_server.py` 将 `DomainToolRegistry` 以 stdio MCP 服务暴露给支持 MCP 的客户端，并额外提供 `industry://rules/{industry}` 规则资源。MCP 服务必须由操作者显式启动，不会在 Dashboard 或 Python 包导入时自动启动；因此不会改变现有前端请求路径。

### OpenAI Function Calling

`openai_agent.py` 是可选适配器，仅在总开关、工具调用开关和模型配置同时满足时运行 Responses API 工具循环。项目现有的 DeepSeek 调用和 Dashboard 接口保持原样，未被迁移或包裹。

## 一次完整的旁路调用

```text
启用开关
  → industry-intelligence index
  → 用户问题进入 RAG 检索
  → LangGraph 或 OpenAI/MCP 选择只读工具
  → 返回带来源的规则解释/运行摘要
  → 原有 Excel、SQL、FastAPI、React 输出不变
```

## 兼容性与验证

1. 新包无基础运行依赖；所有功能均要求总开关 `INDUSTRY_INTELLIGENCE_ENABLED=true` 和对应子开关。
2. 现有遗留文件（pipeline、Dashboard 后端与 React 前端）未被修改，也没有对新包的导入。
3. 新增测试全部通过：核心与可选集成共 10 项；覆盖 SQLite RAG、LangChain splitter、Chroma、LangGraph、MCP 和工具调用循环。
4. 离线 CLI 烟测成功：索引仓库规则文档 28 个、生成 121 个 chunk，并可按行业检索命中 `pipeline/rules/` 文档。
5. 发布前检查、Python 编译检查和 Git 空白检查通过。真实 OpenAI/外部模型调用未在本地触发，生产使用时需由部署者显式提供授权配置。

## 使用方式

```powershell
# 保持现有项目行为（默认）
./scripts/setup.ps1

# 需要试用旁路能力时再安装可选依赖
./scripts/setup.ps1 -EnableIntelligence
$env:INDUSTRY_INTELLIGENCE_ENABLED = "true"
$env:INDUSTRY_RAG_ENABLED = "true"
industry-intelligence index
industry-intelligence search "净出口如何计算" --industry lithium
```

详细边界、目录和环境变量见 [INTELLIGENCE_ARCHITECTURE.md](INTELLIGENCE_ARCHITECTURE.md)、[DATA_PRIVACY.md](DATA_PRIVACY.md) 和包内 [README.md](../packages/industry-intelligence/README.md)。
