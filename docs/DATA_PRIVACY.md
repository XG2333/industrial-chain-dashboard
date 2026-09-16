# Data and privacy policy

## Never commit

- `.env` files or API keys;
- raw or processed industry workbooks;
- licensed market data or internal indicator values;
- real watchlists or analyst-selected stock pools;
- SQLite databases, caches, logs, audit exports, and workflow snapshots;
- RAG chunks, embeddings, Chroma indexes, retrieved context, and tool-call audit records;
- usernames, passwords, cookies, tokens, private keys, or local user paths.

## Repository safeguards

- `.gitignore` blocks common secrets, data formats, caches, databases, and build artifacts.
- `.env.example` files contain variable names only.
- stock-target configuration contains only a minimal, public demonstration entry per industry.
- production and sample data directories are not copied from the private project.
- `scripts/prepublish_check.ps1` performs a second release-time scan.

The optional intelligence layer indexes only `docs/`, `pipeline/docs/`, and `pipeline/rules/` by default. It deliberately excludes `data/`, runtime workbooks, `.env` files, and credentials. Before using remote embeddings, Function Calling, or an external MCP host, confirm that every transmitted document, catalog row, and tool result is authorized for that provider.

## If a secret was ever committed

Deleting the file in a later commit is insufficient. Revoke or rotate the credential first, then remove it from Git history before publishing.

## Data licensing

Code publication does not grant redistribution rights for the underlying industry or market data. Only use data that you own or are licensed to process and display.
