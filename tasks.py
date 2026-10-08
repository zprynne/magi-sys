# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Cross-platform task runner for MAGI (works in PowerShell, cmd, bash, zsh).

    uv run tasks.py install
    uv run tasks.py dev --mock                      # API + frontend, recorded runs
    uv run tasks.py dev                             # API + frontend, Claude (needs a key)
    uv run tasks.py dev --models models/mlx.yaml --start-mlx    # all-local, Apple Silicon
    uv run tasks.py dev --models models/ollama.yaml             # all-local, Ollama
    uv run tasks.py check                           # lint, types, tests, drift checks

Run `uv run tasks.py --help` for every command. Only uv is needed to start;
`install` also needs Node 22+ (npm) for the frontend.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"


class TaskError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Process helpers
# --------------------------------------------------------------------------- #


def tool(name: str, hint: str) -> str:
    """Full path to an executable (resolves npm -> npm.cmd on Windows)."""
    path = shutil.which(name)
    if path is None:
        raise TaskError(f"`{name}` not found. {hint}")
    return path


def uv() -> str:
    return tool("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")


def npm() -> str:
    return tool("npm", "Install Node.js 22 or newer: https://nodejs.org/")


def run(cmd: Sequence[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    shown = " ".join([Path(cmd[0]).stem, *cmd[1:]])
    print(f"\n> {shown}   (in {cwd.name}/)", flush=True)
    result = subprocess.run(list(cmd), cwd=cwd, env={**os.environ, **(env or {})}, check=False)
    if result.returncode != 0:
        raise TaskError(f"command failed with exit code {result.returncode}")


def spawn(cmd: Sequence[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    """Start a long-running child in its own process group so it can be
    stopped together with everything it launches."""
    full_env = {**os.environ, **env}
    out, err = subprocess.PIPE, subprocess.STDOUT
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        return subprocess.Popen(
            list(cmd), cwd=cwd, env=full_env, stdout=out, stderr=err, creationflags=flags
        )
    return subprocess.Popen(
        list(cmd), cwd=cwd, env=full_env, stdout=out, stderr=err, start_new_session=True
    )


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        # /T stops the whole tree (npm -> node, uv -> python).
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def relay(name: str, process: subprocess.Popen[bytes]) -> threading.Thread:
    """Copy a child's output to ours, prefixed with its name."""

    def pump() -> None:
        assert process.stdout is not None
        for raw in iter(process.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(f"[{name}] {line}", flush=True)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    return thread


def run_together(children: dict[str, tuple[Sequence[str], Path, dict[str, str]]]) -> None:
    """Run several long-lived processes; Ctrl-C (or any of them exiting) stops all."""
    # Ctrl-C must reach us even if our parent started us with SIGINT ignored, and
    # a plain `kill` (SIGTERM) should clean up the children too.
    signal.signal(signal.SIGINT, signal.default_int_handler)

    def on_terminate(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_terminate)
    processes = {name: spawn(cmd, cwd, env) for name, (cmd, cwd, env) in children.items()}
    for name, process in processes.items():
        relay(name, process)
    try:
        while all(p.poll() is None for p in processes.values()):
            time.sleep(0.5)
        exited = next(n for n, p in processes.items() if p.poll() is not None)
        raise TaskError(f"{exited} exited (code {processes[exited].returncode}); stopping the rest")
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
    finally:
        for process in reversed(list(processes.values())):
            stop(process)


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


def api_env(args: argparse.Namespace) -> dict[str, str]:
    env: dict[str, str] = {}
    if getattr(args, "mock", False):
        env["MAGI_MOCK"] = "1"
    if getattr(args, "models", None):
        env["MAGI_MODELS"] = str(Path(args.models).resolve())
    return env


def api_cmd(args: argparse.Namespace, *, reload: bool) -> list[str]:
    cmd = [uv(), "run", "magi-server", "--port", str(args.port)]
    return [*cmd, "--reload"] if reload else cmd


def mlx_cmd(models: str | None) -> list[str]:
    profile = str(Path(models).resolve()) if models else str(ROOT / "models" / "mlx.yaml")
    return [uv(), "run", "--extra", "mlx", "magi-mlx", "--models", profile]


def task_install(_: argparse.Namespace) -> None:
    run([uv(), "sync", "--extra", "mlx"] if APPLE_SILICON else [uv(), "sync"], BACKEND)
    run([npm(), "install"], FRONTEND)


def task_dev(args: argparse.Namespace) -> None:
    children: dict[str, tuple[Sequence[str], Path, dict[str, str]]] = {}
    if args.start_mlx:
        if not APPLE_SILICON:
            raise TaskError("--start-mlx needs an Apple Silicon Mac; use Ollama elsewhere")
        children["mlx"] = (mlx_cmd(args.models), BACKEND, {})
    children["api"] = (api_cmd(args, reload=True), BACKEND, api_env(args))
    children["web"] = (
        [npm(), "run", "dev"],
        FRONTEND,
        {"MAGI_BACKEND_URL": f"http://127.0.0.1:{args.port}"},
    )
    print(
        f"API on http://127.0.0.1:{args.port}. Open the console at the [web] Local: URL "
        "below (Vite uses 5173, or the next free port). Ctrl-C stops everything.",
        flush=True,
    )
    run_together(children)


def task_api(args: argparse.Namespace) -> None:
    run(api_cmd(args, reload=args.reload), BACKEND, api_env(args))


def task_frontend(args: argparse.Namespace) -> None:
    run([npm(), "run", "dev"], FRONTEND, {"MAGI_BACKEND_URL": f"http://127.0.0.1:{args.port}"})


def task_mlx(args: argparse.Namespace) -> None:
    run(mlx_cmd(args.models), BACKEND)


def task_build(_: argparse.Namespace) -> None:
    run([npm(), "run", "build"], FRONTEND)


def task_serve(args: argparse.Namespace) -> None:
    task_build(args)
    print(f"\nMAGI on http://127.0.0.1:{args.port}")
    run(api_cmd(args, reload=False), BACKEND, api_env(args))


def task_schema(_: argparse.Namespace) -> None:
    run([uv(), "run", "magi-schema"], BACKEND)


def task_types(args: argparse.Namespace) -> None:
    task_schema(args)
    run([npm(), "run", "gen:types"], FRONTEND)


def task_traces(_: argparse.Namespace) -> None:
    run([uv(), "run", "python", "scripts/build_example_traces.py"], BACKEND)


def task_resources(args: argparse.Namespace) -> None:
    cmd = [uv(), "run", *(["--extra", "mlx"] if APPLE_SILICON else []), "magi-resources"]
    run([*cmd, *(["--models", str(Path(args.models).resolve())] if args.models else [])], BACKEND)


def task_test(_: argparse.Namespace) -> None:
    run([uv(), "run", "pytest"], BACKEND)
    run([npm(), "test"], FRONTEND)


def task_lint(_: argparse.Namespace) -> None:
    run([uv(), "run", "ruff", "check", ".", str(ROOT / "tasks.py")], BACKEND)
    run([uv(), "run", "ruff", "format", "--check", ".", str(ROOT / "tasks.py")], BACKEND)
    run([npm(), "run", "lint"], FRONTEND)


def task_typecheck(_: argparse.Namespace) -> None:
    run([uv(), "run", "mypy"], BACKEND)
    run([npm(), "run", "typecheck"], FRONTEND)


def task_check(args: argparse.Namespace) -> None:
    task_lint(args)
    task_typecheck(args)
    task_test(args)
    run([uv(), "run", "magi-schema", "--check"], BACKEND)
    run([npm(), "run", "check:types"], FRONTEND)
    print("\nall checks passed")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="uv run tasks.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = root.add_subparsers(dest="command", required=True, metavar="command")

    def add(name: str, func: object, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.set_defaults(func=func)
        return sub

    def server_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--port", type=int, default=8000, help="API port (default 8000)")
        sub.add_argument("--mock", action="store_true", help="replay saved traces, no model")
        sub.add_argument("--models", help="model profile, e.g. models/ollama.yaml")

    add("install", task_install, "install backend (uv) and frontend (npm) dependencies")
    dev = add("dev", task_dev, "run the API and the frontend together (Ctrl-C stops both)")
    server_options(dev)
    dev.add_argument("--start-mlx", action="store_true", help="also start the MLX model servers")
    api = add("api", task_api, "run only the API")
    server_options(api)
    api.add_argument("--reload", action="store_true", help="restart on code changes")
    web = add("frontend", task_frontend, "run only the Vite dev server")
    web.add_argument("--port", type=int, default=8000, help="API port to proxy to")
    mlx = add("mlx", task_mlx, "start the MLX model servers (Apple Silicon)")
    mlx.add_argument("--models", help="model profile (default models/mlx.yaml)")
    add("build", task_build, "build the frontend into frontend/dist")
    serve = add("serve", task_serve, "build the frontend and serve everything from the API")
    server_options(serve)
    add("schema", task_schema, "regenerate schema/magi-events.schema.json")
    add("types", task_types, "regenerate the JSON Schema and the TypeScript event types")
    add("traces", task_traces, "rebuild traces/example-*.jsonl")
    res = add("resources", task_resources, "disk and memory report")
    res.add_argument("--models", help="model profile whose models to report on")
    add("test", task_test, "run backend and frontend tests")
    add("lint", task_lint, "ruff + eslint")
    add("typecheck", task_typecheck, "mypy + tsc")
    add("check", task_check, "lint, typecheck, test and drift checks")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except TaskError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
