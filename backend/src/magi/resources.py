"""Disk and memory measurements for MAGI and its local models.

    uv run magi-resources            # markdown report to stdout

Memory is measured with macOS ``footprint`` (phys_footprint), which includes
GPU allocations made by MLX. Plain RSS misses most of them: a 9B 4-bit model
shows ~3.5 GB RSS but ~5.4 GB footprint.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from magi.paths import BACKEND_DIR, REPO_ROOT

GB = 1024**3
MB = 1024**2
HF_HUB = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))


def dir_size(path: Path) -> int:
    """Bytes used by a directory tree (symlinks not followed, so HF snapshot links
    don't double-count their blobs)."""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file = Path(root) / name
            if not file.is_symlink():
                total += file.stat().st_size
    return total


def hf_model_dir(repo_id: str) -> Path:
    return HF_HUB / f"models--{repo_id.replace('/', '--')}"


def hf_model_size(repo_id: str) -> int | None:
    """Size of a downloaded Hugging Face model, or None if it is not in the cache."""
    path = hf_model_dir(repo_id)
    return dir_size(path / "blobs") if path.is_dir() else None


def total_ram() -> int:
    if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return 0


def gpu_working_set_limit() -> int | None:
    """macOS caps how much unified memory the GPU may use (~75% of RAM)."""
    try:
        import mlx.core as mx

        return int(mx.device_info()["max_recommended_working_set_size"])
    except Exception:
        return None


_FOOTPRINT = re.compile(r"phys_footprint:\s+([\d.]+)\s+([KMG])B")


def process_memory(pid: int) -> int | None:
    """Physical footprint of a process in bytes (macOS), falling back to RSS."""
    if shutil.which("footprint"):
        out = subprocess.run(
            ["footprint", str(pid)], capture_output=True, text=True, check=False
        ).stdout
        match = _FOOTPRINT.search(out)
        if match:
            scale = {"K": 1024, "M": MB, "G": GB}[match.group(2)]
            return int(float(match.group(1)) * scale)
    out = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return int(out) * 1024 if out.isdigit() else None


def pid_on_port(port: int) -> int | None:
    out = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, check=False
    ).stdout.split()
    return int(out[0]) if out else None


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    label: str
    memory: int | None


# Launchers whose command line mentions the real process but isn't it.
_WRAPPERS = {"uv", "sh", "bash", "zsh", "make"}
_PATTERNS = {
    "mlx_lm.server": re.compile(r"mlx_lm[. ]server.*--model\s+(\S+)"),
    "magi-server": re.compile(r"magi-server|magi\.server"),
    "vite": re.compile(r"node .*vite"),
}


def magi_processes() -> list[ProcessInfo]:
    """Running MAGI-related processes: model servers, the API, the dev server."""
    out = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False
    ).stdout
    found: list[ProcessInfo] = []
    for line in out.splitlines():
        pid_text, _, command = line.strip().partition(" ")
        # Skip this report and the `uv run` wrappers around the real processes.
        program = Path(command.split(" ", 1)[0]).name
        if not pid_text.isdigit() or "magi-resources" in command or program in _WRAPPERS:
            continue
        for kind, pattern in _PATTERNS.items():
            match = pattern.search(command)
            if match:
                label = f"{kind} {match.group(1)}" if match.groups() else kind
                found.append(ProcessInfo(int(pid_text), label, process_memory(int(pid_text))))
                break
    return found


def fmt(size: int | None) -> str:
    if size is None:
        return "n/a"
    if size >= GB:
        return f"{size / GB:.2f} GB"
    return f"{size / MB:.0f} MB" if size >= MB else f"{size / 1024:.0f} KB"


def table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> str:
    headers = list(headers)
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def report(models: list[str]) -> str:
    sections = [f"_Measured {datetime.now():%Y-%m-%d %H:%M}_"]

    ram, gpu = total_ram(), gpu_working_set_limit()
    sections.append(
        "### Machine\n\n"
        + table(["", ""], [["RAM", fmt(ram)], ["GPU working-set limit", fmt(gpu)]])
    )

    disk_rows = [
        [label, fmt(dir_size(path))]
        for label, path in [
            ("backend/.venv", BACKEND_DIR / ".venv"),
            ("frontend/node_modules", REPO_ROOT / "frontend" / "node_modules"),
            ("frontend/dist", REPO_ROOT / "frontend" / "dist"),
            ("traces/", REPO_ROOT / "traces"),
            (".git", REPO_ROOT / ".git"),
        ]
    ]
    traces = len(list((REPO_ROOT / "traces").glob("*.jsonl")))
    disk_rows.append(["trace files", str(traces)])
    sections.append("### Project on disk\n\n" + table(["Path", "Size"], disk_rows))

    model_rows = [
        [name, fmt(hf_model_size(name)) if hf_model_size(name) else "not downloaded"]
        for name in models
    ]
    model_rows.append(["whole Hugging Face cache", fmt(dir_size(HF_HUB))])
    sections.append("### Models on disk\n\n" + table(["Model", "Size"], model_rows))

    procs = magi_processes()
    if procs:
        rows = [[str(p.pid), p.label, fmt(p.memory)] for p in procs]
        rows.append(["", "**total**", fmt(sum(p.memory or 0 for p in procs))])
        sections.append("### Running processes\n\n" + table(["PID", "Process", "Memory"], rows))
    else:
        sections.append("### Running processes\n\nNo MAGI or mlx_lm processes running.")
    return "\n\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> None:
    from magi.models import load_profile
    from magi.settings import get_settings

    parser = argparse.ArgumentParser(description="Report MAGI disk and memory usage.")
    parser.add_argument("--models", type=Path, help="model profile (default: MAGI_MODELS)")
    args = parser.parse_args(argv)

    # CLI paths are relative to the working directory; .env paths to the repo.
    path = args.models.resolve() if args.models else get_settings().models
    names: list[str] = []
    if path:
        profile = load_profile(path if path.is_absolute() else REPO_ROOT / path)
        entries = [*profile.agents.values(), *([profile.arbiter] if profile.arbiter else [])]
        names = sorted(
            {str(e.get("name", profile.defaults.get("name", ""))) for e in entries} - {""}
        )
    print(report(names))


if __name__ == "__main__":
    main()
