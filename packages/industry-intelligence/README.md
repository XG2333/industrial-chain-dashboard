# Industry Intelligence Layer

An optional sidecar package that adds RAG, hybrid retrieval, vector storage,
allow-listed function calling, LangGraph orchestration, and an MCP server without
replacing the existing deterministic Excel pipeline or dashboard endpoints.

## Compatibility contract

- Importing or installing the package performs no work.
- Every capability is disabled by default and requires two explicit flags: the
  master switch plus a feature-specific switch.
- Knowledge ingestion reads only `docs/`, `pipeline/docs/`, and
  `pipeline/rules/` by default. It never indexes `data/` or `.env` files.
- Domain tools are read-only. The workbook tool opens only the first catalog
  sheet with `read_only=True` and `data_only=True`.
- All generated indexes and audit records stay under `runtime/intelligence/`,
  which is excluded from Git.
- The legacy pipeline, existing FastAPI routes, response schemas, and React UI
  do not import this package.

## Install

The normal project setup is unchanged. Install the optional layer explicitly:

```powershell
./scripts/setup.ps1 -EnableIntelligence
```

Or install selected extras:

```powershell
python -m pip install -e "packages/industry-intelligence[rag,graph,mcp,openai]"
```

Copy `.env.example` values into a private environment and opt in deliberately.

## Local RAG

```powershell
$env:INDUSTRY_INTELLIGENCE_ENABLED="true"
$env:INDUSTRY_RAG_ENABLED="true"
industry-intelligence index
industry-intelligence search "净出口如何计算" --industry lithium
```

The default SQLite backend stores embeddings as JSON and performs hybrid dense
and token-overlap ranking for the small repository corpus. To use the dedicated
Chroma vector index, set `INDUSTRY_VECTOR_BACKEND=chroma`.

## Function calling

`DomainToolRegistry` exposes four strict, allow-listed read-only tools:

- `search_industry_knowledge`
- `list_rule_documents`
- `get_indicator_catalog`
- `get_pipeline_run_status`

`openai_agent.run_tool_calling_query` uses the Responses API only when both the
master and tool-calling flags are enabled and `INDUSTRY_OPENAI_MODEL` is set.
It sends `store=False` and does not replace the existing DeepSeek endpoints.

## LangGraph

`graph.build_research_graph` creates a sidecar graph with three nodes:
retrieval, explicit read-only tool execution, and synthesis. A caller can inject
its own synthesizer. The deterministic pipeline remains the source of truth.

## MCP

The MCP server exposes the same read-only registry over stdio:

```powershell
$env:INDUSTRY_INTELLIGENCE_ENABLED="true"
$env:INDUSTRY_RAG_ENABLED="true"
$env:INDUSTRY_MCP_ENABLED="true"
industry-intelligence-mcp
```

Index approved documents before starting the server. Never expose private
workbooks or tool outputs to an external host without confirming authorization.
