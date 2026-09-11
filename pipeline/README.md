# Industrial data pipeline

This directory contains the lithium, tin, and silicon workbook orchestration and deterministic business rules.

## Main entry points

- `scripts/run_industry_pipeline.py`: process one industry workbook.
- repository `scripts/process_all.py`: portable all-industry entry point.
- `workflow/`: YAML workflow engine and runners.
- `configs/`: portable industry configurations. Placeholders are resolved by the repository entry point.
- `rules/`: current business-rule documentation.
- `skills/dashboard-data-sorter/`: canonical catalog ordering.
- `skills/stock-target-curator/`: optional stock-target export using an empty public template.

Generated inputs, outputs, workflow runs, reports, caches, and databases belong under the repository-level `data/` and `runtime/` directories and must not be committed.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/process_all.py --provider mock
```

For detailed data contracts and invariants, see `../docs/ARCHITECTURE.md` and the Markdown files under `rules/`.
