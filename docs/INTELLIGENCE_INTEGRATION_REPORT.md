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
