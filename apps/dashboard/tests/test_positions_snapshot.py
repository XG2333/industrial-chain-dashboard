from __future__ import annotations

import json
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _import_server():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import server as server_module
    return server_module


@contextmanager
def _snap_file(monkeypatch, server_module) -> Path:
    """把快照文件指向临时目录并给出可读写的 Path。"""
    tmp = tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT))
    monkeypatch.setattr(server_module, "_POS_SNAPSHOT_FILE", Path(tmp.name) / "snap.json")
    try:
        yield server_module._POS_SNAPSHOT_FILE
    finally:
        tmp.cleanup()


def _groups(product: str = "碳酸锂") -> list[dict]:
    return [{"product": product, "rows": [
        {"contract": "2609", "vol": 100.0, "oi": 500.0},
        {"contract": "2611", "vol": 200.0, "oi": 1000.0},
    ]}]


def _freeze(monkeypatch, server_module, y, mo, d, h, mi, fmt_date: str | None = None):
    """把 server 的本地时间冻结到指定时刻; fmt_date 覆盖 strftime("%Y-%m-%d")。"""
    fake = time.struct_time((y, mo, d, h, mi, 0, 0, 1, -1))
    monkeypatch.setattr(server_module.time, "localtime", lambda: fake)
    if fmt_date is not None:
        monkeypatch.setattr(
            server_module.time, "strftime",
            lambda f, t=None, _d=fmt_date: _d if f == "%Y-%m-%d" else time.strftime(f, t))


def test_old_single_format_migrates_to_history(monkeypatch) -> None:
    """旧版单槽 {date, rows} 文件加载后应迁移为 {history: {date: rows}}。"""
    server_module = _import_server()
    with _snap_file(monkeypatch, server_module) as f:
        f.write_text(json.dumps(
            {"date": "2026-09-08", "rows": {"碳酸锂:2611": {"vol": 200.0, "oi": 1000.0}}},
            ensure_ascii=False), encoding="utf-8")
        snap = server_module._load_pos_snapshot()
        assert snap["history"]["2026-09-08"]["碳酸锂:2611"] == {"vol": 200.0, "oi": 1000.0}


def test_same_day_never_resaved_and_history_kept(monkeypatch) -> None:
    """同日多次 15:30 后不重复覆盖; 新交易日落盘时旧快照保留(供较前日基线)。"""
    server_module = _import_server()
    with _snap_file(monkeypatch, server_module) as f:
        f.write_text(json.dumps({"history": {"2026-09-08": {"碳酸锂:2611": {"vol": 200.0, "oi": 1000.0}}}},
                                ensure_ascii=False), encoding="utf-8")
        _freeze(monkeypatch, server_module, 2026, 9, 9, 15, 40, "2026-09-09")
        # 第一次: 09-09 落盘, 09-08 保留
        server_module._maybe_save_pos_snapshot(_groups(), "2026-09-09")
        snap = json.loads(f.read_text(encoding="utf-8"))
        assert set(snap["history"]) == {"2026-09-08", "2026-09-09"}
        # 同日第二次: 不重复落盘(内容不变)
        before = f.read_text(encoding="utf-8")
        server_module._maybe_save_pos_snapshot(_groups(), "2026-09-09")
        assert f.read_text(encoding="utf-8") == before


def test_night_session_or_holiday_never_saved(monkeypatch) -> None:
    """本地日期 != 行情日期(夜盘 21:00 后行情已属下一交易日)时不落盘。"""
    server_module = _import_server()
    with _snap_file(monkeypatch, server_module) as f:
        f.write_text(json.dumps({"history": {"2026-09-09": {}}}, ensure_ascii=False), encoding="utf-8")
        _freeze(monkeypatch, server_module, 2026, 9, 9, 21, 10, "2026-09-09")
        server_module._maybe_save_pos_snapshot(_groups(), "2026-09-10")  # 行情日期已滚动
        snap = json.loads(f.read_text(encoding="utf-8"))
        assert "2026-09-10" not in snap["history"]


def test_before_1530_never_saved(monkeypatch) -> None:
    server_module = _import_server()
    with _snap_file(monkeypatch, server_module) as f:
        _freeze(monkeypatch, server_module, 2026, 9, 9, 11, 30, "2026-09-09")
        server_module._maybe_save_pos_snapshot(_groups(), "2026-09-09")
        assert not f.exists()  # 未落盘(文件不产生)


def test_history_capped_at_six_days(monkeypatch) -> None:
    server_module = _import_server()
    with _snap_file(monkeypatch, server_module) as f:
        f.write_text(json.dumps({"history": {f"2026-09-0{d}": {} for d in range(2, 8)}},
                                ensure_ascii=False), encoding="utf-8")
        _freeze(monkeypatch, server_module, 2026, 9, 10, 15, 40, "2026-09-10")
        server_module._maybe_save_pos_snapshot(_groups(), "2026-09-10")
        hist = json.loads(f.read_text(encoding="utf-8"))["history"]
        assert len(hist) <= 6
        assert "2026-09-10" in hist
        assert "2026-09-02" not in hist  # 最旧的被裁掉
