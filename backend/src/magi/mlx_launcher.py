"""Start the mlx_lm servers that a model profile points at.

    uv run --extra mlx magi-mlx                  # profile from MAGI_MODELS or models/mlx.yaml
    uv run --extra mlx magi-mlx --check          # plan + memory estimate, start nothing

One server per distinct local base_url. Agents that share a base_url share a
server and therefore one copy of the weights. Ctrl-C stops every server.
"""

from __future__ import annotations

import argparse
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from urllib.parse import urlparse

from magi.models import ModelSpec, ProfileError, resolve_roster
from magi.paths import BACKEND_DIR, DEFAULT_PERSONAS_DIR, REPO_ROOT
from magi.personas import load_personas
from magi.resources import (
    fmt,
    gpu_working_set_limit,
    hf_model_size,
    pid_on_port,
    process_memory,
    table,
    total_ram,
)
from magi.settings import Settings

DEFAULT_PROFILE = REPO_ROOT / "models" / "mlx.yaml"
LOG_DIR = BACKEND_DIR / ".mlx-logs"
# Weights plus KV cache and runtime buffers, measured on Qwen3/Llama 4-bit models.
OVERHEAD = 1.15


@dataclass(frozen=True)
class ServerPlan:
    model: str
    host: str
    port: int
    agents: tuple[str, ...]


class PlanError(ValueError):
    pass


def plan_servers(assignments: dict[str, ModelSpec]) -> list[ServerPlan]:
    """Group the local OpenAI-compatible specs by base_url, one server each."""
    by_url: dict[tuple[str, int], tuple[str, list[str]]] = {}
    for who, spec in assignments.items():
        if spec.provider != "openai" or not spec.is_local or not spec.base_url:
            continue
        url = urlparse(spec.base_url)
        key = (url.hostname or "127.0.0.1", url.port or 80)
        model, agents = by_url.setdefault(key, (spec.name, []))
        if model != spec.name:
            raise PlanError(
                f"{spec.base_url} is assigned two models ({model} and {spec.name}); "
                "an mlx_lm server holds one model, so give each model its own port"
            )
        agents.append(who)
    return [
        ServerPlan(model, host, port, tuple(agents))
        for (host, port), (model, agents) in sorted(by_url.items(), key=lambda kv: kv[0][1])
    ]


def describe(plans: list[ServerPlan]) -> tuple[str, int]:
    rows, total = [], 0
    for plan in plans:
        size = hf_model_size(plan.model)
        total += int((size or 0) * OVERHEAD)
        rows.append(
            [
                f"{plan.host}:{plan.port}",
                plan.model,
                ", ".join(plan.agents),
                fmt(size) if size else "**not downloaded**",
            ]
        )
    return table(["Server", "Model", "Used by", "Weights"], rows), total


def wait_ready(plan: ServerPlan, process: subprocess.Popen[bytes], timeout: float) -> bool:
    url = f"http://{plan.host}:{plan.port}/v1/models"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def warm_up(plan: ServerPlan) -> None:
    """mlx_lm loads weights lazily; one tiny request loads them now so the
    first deliberation isn't slow and the memory report is honest."""
    body = (
        f'{{"model": "{plan.model}", "max_tokens": 1, '
        '"messages": [{"role": "user", "content": "hi"}]}'
    ).encode()
    request = urllib.request.Request(
        f"http://{plan.host}:{plan.port}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--models", type=Path, help="model profile (default: MAGI_MODELS or models/mlx.yaml)"
    )
    parser.add_argument(
        "--check", action="store_true", help="show the plan and memory estimate only"
    )
    parser.add_argument(
        "--allow-download", action="store_true", help="let mlx_lm download missing models"
    )
    parser.add_argument("--max-tokens", type=int, default=1024, help="server default max tokens")
    parser.add_argument(
        "--prompt-cache-mb", type=int, default=512, help="cap each server's KV prompt cache"
    )
    args = parser.parse_args(argv)
    # Flush progress lines immediately, even when output goes to a pipe or file.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]

    if not (sys.platform == "darwin" and platform.machine() == "arm64"):
        print(
            "magi-mlx needs an Apple Silicon Mac (MLX only runs there).\n"
            "On Windows or Linux, serve local models with Ollama or LM Studio and use\n"
            "models/ollama.yaml instead: see 'Local models' in the README.",
            file=sys.stderr,
        )
        return 2

    settings = Settings()
    # CLI paths are relative to the working directory; .env paths to the repo.
    profile = args.models.resolve() if args.models else settings.models or DEFAULT_PROFILE
    profile = profile if profile.is_absolute() else REPO_ROOT / profile
    settings = settings.model_copy(update={"models": profile})
    try:
        roster = resolve_roster(
            settings, load_personas(settings.personas_dir or DEFAULT_PERSONAS_DIR)
        )
        plans = plan_servers({**roster.agents, "arbiter": roster.arbiter})
    except (ProfileError, PlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not plans:
        print(f"{profile.name} has no local OpenAI-compatible models to serve.")
        return 0

    text, estimate = describe(plans)
    limit = gpu_working_set_limit()
    shown = profile.relative_to(REPO_ROOT) if profile.is_relative_to(REPO_ROOT) else profile
    print(f"Profile: {shown}\n")
    print(text)
    print(
        f"\nEstimated memory: {fmt(estimate)} of {fmt(total_ram())} RAM "
        f"(GPU working-set limit {fmt(limit)})"
    )
    if limit and estimate > limit:
        print(
            "warning: this is above the GPU limit; expect swapping. Share a server "
            "between agents or use smaller models.",
            file=sys.stderr,
        )
    missing = [p.model for p in plans if hf_model_size(p.model) is None]
    if missing and not args.allow_download:
        print(
            f"\nnot downloaded: {', '.join(missing)}\n"
            "Download them first (e.g. `uv run --extra mlx mlx_lm.generate --model <name> "
            "--prompt hi`) or pass --allow-download.",
            file=sys.stderr,
        )
        return 1
    if args.check:
        return 0

    busy = [p for p in plans if pid_on_port(p.port)]
    if busy:
        ports = ", ".join(str(p.port) for p in busy)
        print(
            f"error: port(s) {ports} already in use; stop the old servers first.", file=sys.stderr
        )
        return 1

    LOG_DIR.mkdir(exist_ok=True)
    env = {**os.environ}
    if not args.allow_download:
        env["HF_HUB_OFFLINE"] = "1"
    processes: list[tuple[ServerPlan, subprocess.Popen[bytes]]] = []
    for plan in plans:
        log = (LOG_DIR / f"{plan.port}.log").open("wb")
        command = [
            sys.executable, "-m", "mlx_lm.server",
            "--model", plan.model,
            "--host", plan.host,
            "--port", str(plan.port),
            "--max-tokens", str(args.max_tokens),
            "--prompt-cache-bytes", str(args.prompt_cache_mb * 1024 * 1024),
        ]  # fmt: skip
        processes.append(
            (plan, subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env))
        )

    def stop(_signum: int | None = None, _frame: FrameType | None = None) -> None:
        for _, process in processes:
            if process.poll() is None:
                process.terminate()
        for _, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    signal.signal(signal.SIGTERM, stop)
    try:
        print(f"\nStarting {len(plans)} server(s); logs in {LOG_DIR.relative_to(REPO_ROOT)}/")
        for plan, process in processes:
            if not wait_ready(plan, process, timeout=180):
                print(
                    f"error: {plan.model} on :{plan.port} did not start; see "
                    f"{LOG_DIR / f'{plan.port}.log'}",
                    file=sys.stderr,
                )
                stop()
                return 1
            warm_up(plan)
        rows = []
        total = 0
        for plan, process in processes:
            memory = process_memory(process.pid) or 0
            total += memory
            rows.append([f":{plan.port}", plan.model, fmt(memory)])
        rows.append(["", "**total**", fmt(total)])
        print("\nReady.\n\n" + table(["Server", "Model", "Memory (loaded)"], rows))
        print("\nRun the API with this profile in another terminal: make local")
        print("Ctrl-C stops the servers.")
        while all(process.poll() is None for _, process in processes):
            time.sleep(1)
        print("a model server exited; stopping the rest", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nstopping model servers")
        return 0
    finally:
        stop()


if __name__ == "__main__":
    raise SystemExit(main())
