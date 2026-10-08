"""The resource report must run on every OS (CI covers macOS, Linux, Windows)."""

from __future__ import annotations

from pathlib import Path

from magi.resources import dir_size, fmt, magi_processes, pid_on_port, report, total_ram


def test_report_runs_on_this_platform() -> None:
    text = report(["example/not-downloaded"])
    assert "### Machine" in text
    assert "not downloaded" in text
    assert total_ram() > 0


def test_process_helpers_do_not_crash() -> None:
    assert isinstance(magi_processes(), list)
    assert pid_on_port(1) is None  # nothing listens on port 1


def test_dir_size_and_formatting(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 2048)
    assert dir_size(tmp_path) == 2048
    assert dir_size(tmp_path / "missing") == 0
    assert fmt(2048) == "2 KB"
    assert fmt(3 * 1024**3) == "3.00 GB"
    assert fmt(None) == "n/a"
