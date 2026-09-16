# Optional intelligence architecture

## Goal

Add retrieval and agent interoperability without changing deterministic data
processing, workbook contents, existing API responses, or the React interface.

## Isolation boundary

```text
Existing path (unchanged)
Excel -> deterministic pipeline -> processed Excel -> FastAPI -> React/ECharts

Optional sidecar (disabled by default)
approved docs -> chunking -> embeddings -> SQLite/Chroma -> retriever
                                                   |            |
                                                   +-> tools <--+
                                                        |
                                      OpenAI function calling / LangGraph / MCP
```

The existing path has no import or runtime dependency on the sidecar. Every
sidecar capability requires `INDUSTRY_INTELLIGENCE_ENABLED=true` plus a matching
feature flag.

## RAG and LangChain

Only approved Markdown/text files under `docs/`, `pipeline/docs/`, and
`pipeline/rules/` are discovered. `RecursiveCharacterTextSplitter` is used when
the LangChain text-splitter extra is installed; a deterministic local splitter
is retained for offline tests. Each chunk keeps its source path, title,
industry, and document type so answers can cite provenance.

Raw observation sheets are not embedded. Precise numeric data remains the
responsibility of deterministic workbook/database tools.

## Database and vector storage

The default sidecar backend is a local SQLite database containing documents,
chunks, vectors, metadata, and tool-call audit rows. It performs hybrid ranking
from dense cosine similarity and token overlap. This is appropriate for the
small repository corpus.

Chroma is available as an explicit vector backend for larger corpora. Both
backends write only below `runtime/intelligence/` unless a private runtime path
is supplied.

## Function tools

One registry defines strict schemas and implementations for both OpenAI tool
calling and MCP:

1. search approved knowledge;
2. list indexed rule documents;
3. read a processed workbook's catalog sheet;
4. read a workflow-run summary.

Tools are allow-listed and read-only. There is no arbitrary SQL, file-write,
shell, pipeline-start, or network-request tool.

## LangGraph

The optional graph has retrieval, explicit tool execution, and synthesis nodes.
It is intended for research and review workflows. It does not replace the YAML
workflow runner or deterministic business rules.

## MCP

The stdio MCP server exposes the same read-only tools and an industry-rule
resource. Starting it is an explicit operator action. No MCP process starts on
package import or normal dashboard startup.

## Compatibility guarantees

- All flags are off by default.
- No existing endpoint or frontend component is changed.
- No existing workbook is written by the sidecar.
- Indexing is idempotent and source documents are read-only.
- Runtime artifacts and embeddings are excluded from source control.
- Existing Python tests, frontend tests, and frontend build remain release gates.
