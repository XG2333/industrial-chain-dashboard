# Financial variable curation

A reusable Python package for inspecting multi-sheet Excel workbooks, classifying financial and industrial variables, compiling human-readable rules, applying deterministic selections, and recording provenance in SQLite through SQLAlchemy.

## Install

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e packages/selecting-skill
```

## CLI

```powershell
financial-variable-curation --help
```

The pipeline primarily uses the `directory-mark` command with the rule source in `input/selection_rules.docx`.

## Privacy

The package contains no production workbooks or databases. Its `.env.example` lists optional settings but contains no credentials. Local `.env`, SQLite files, exports, and Excel inputs are ignored by the repository.
