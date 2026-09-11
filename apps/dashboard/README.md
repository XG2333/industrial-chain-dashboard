# Dashboard application

The dashboard combines a FastAPI server with a React 19, Vite, Flowbite React, and ECharts frontend.

The server reads processed workbooks from the repository-level `data/processed/` directory and stock targets from `data/stock-targets/`. Paths are configured by `scripts/configure_env.py` and stored only in the ignored local `.env` file.

## Development

```powershell
Set-Location apps/dashboard/frontend
npm ci
npm run dev
```

In another terminal:

```powershell
.\.venv\Scripts\python.exe apps/dashboard/server.py
```

## Production-style local build

```powershell
Set-Location apps/dashboard/frontend
npm ci
npm run build
Set-Location ../../..
./scripts/run_dashboard.ps1
```

No workbook or market-data cache is part of the source repository.
