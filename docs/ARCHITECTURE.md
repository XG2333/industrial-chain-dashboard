# Architecture

## End-to-end flow

```text
Private Excel sources
  -> catalog generation
  -> variable classification and tags
  -> net-export and composite metrics
  -> deterministic selection
  -> optional constrained AI review
  -> secondary display selection
  -> canonical catalog sorting
  -> processed workbooks
  -> FastAPI metadata and series APIs
  -> React/ECharts dashboard
```

## Components

### `pipeline/`

The orchestration and industrial business-rule layer. `scripts/run_industry_pipeline.py` is the per-industry entry point. YAML files under `configs/` describe the lithium, tin, and silicon stages. The repository-level `scripts/process_all.py` prepares portable configuration and runs all industries.

The first worksheet is treated as the catalog contract. Data worksheets remain intact. The sorter only changes catalog order and rebuilds catalog hyperlinks.

### `packages/selecting-skill/`

The reusable classification and selection engine. It inspects Excel schemas, compiles natural-language rules into structured rules, applies deterministic selection, and records runs in SQLite through SQLAlchemy. SQLite is used for provenance, quality, classification, rule versions, LLM calls, selection results, and exports; it is not the primary numerical calculation engine.

### `apps/dashboard/`

`server.py` loads generated workbooks from `data/processed/`, caches parsed metadata and time series under `runtime/cache/`, and exposes the API and built frontend. The frontend first requests metadata and lazily requests chart series near the viewport.

The workbook `catalog_order` remains the canonical business ordering signal. Frontend grouping combines related charts such as import/export/net export and volume/open-interest/ratio while retaining that order between blocks.

## Data contracts

The catalog includes source sheet, column, indicator name, frequency, unit, sector, major class, subclass, data nature, primary selection, tags, and secondary selection. New transformations should preserve existing worksheet formulas and data sheets.

Important invariants include:

- supply terminology is normalized to `供给`;
- selected import, export, and net-export counts must balance;
- composite groups must remain contiguous after sorting;
- the original workbook must never be saved after opening only with `data_only=True`.

## Runtime boundaries

- `data/raw/`: private inputs.
- `data/processed/`: generated workbooks consumed by the dashboard.
- `data/stock-targets/`: local target universes.
- `runtime/workflow-runs/`: run snapshots, reports, SQLite databases, and audit artifacts.
- `runtime/cache/`: disposable dashboard caches.

None of these runtime contents belongs in source control.
