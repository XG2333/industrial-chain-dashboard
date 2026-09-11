from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
DATA_PATHS = [
    REPO_ROOT / "data" / "processed" / "锡产业链数据_workflow_ai.xlsx",
    REPO_ROOT / "data" / "processed" / "硅产业链数据_workflow_ai.xlsx",
    REPO_ROOT / "data" / "processed" / "碳酸锂数据库_workflow_ai.xlsx",
]


def _import_server():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import server as server_module
    return server_module


@pytest.mark.skipif(
    not all(path.exists() for path in DATA_PATHS),
    reason="local processed workbooks are not present",
)
def test_chart_metadata_and_index() -> None:
    server_module = _import_server()
    server_module._load_all_workbooks()

    assert server_module._CHART_INDEX
    sample_id = next(iter(server_module._CHART_INDEX))
    sample = server_module._CHART_INDEX[sample_id]
    meta = server_module._chart_metadata(sample)

    assert meta["id"] == sample_id
    assert "data" not in meta


def test_persisted_workbook_cache(monkeypatch) -> None:
    server_module = _import_server()
    with tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT)) as tmp_dir:
        cache_dir = Path(tmp_dir)
        monkeypatch.setattr(server_module, "CACHE_DIR", cache_dir)

        source = cache_dir / "sample.xlsx"
        source.write_bytes(b"sample")
        charts = [{"id": "a", "data": [{"date": "2026-01-01", "value": 1.0}]}]
        sectors = {"sample_sector"}

        server_module._write_workbook_cache(source, "sample", charts, sectors)
        loaded_charts, loaded_sectors = server_module._load_persisted_workbook(source, "sample")

        assert loaded_charts == charts
        assert loaded_sectors == sectors
