# Resource usage

A running record of MAGI's disk and memory footprint as the project grows. Regenerate the current numbers with:

```bash
uv run tasks.py resources --models models/mlx.yaml   # disk, models, memory of running MAGI / model servers
```

It runs on macOS, Linux and Windows. Only macOS reports the full GPU-inclusive footprint; elsewhere memory is the resident set (working set on Windows).

Memory figures use macOS `footprint` (physical footprint), which counts the GPU memory MLX allocates. Activity Monitor's "Memory" column and `ps` RSS undercount it badly: Qwen3.5-9B shows about 3.5 GB RSS but 5.4 GB footprint.

**Machine:** Apple M4, 24 GB unified memory. macOS lets the GPU use up to **17.76 GB** of it (`max_recommended_working_set_size`); past that, models start swapping.

## Current snapshot (2026-10-07, after step 1: local models)

### Disk

| What | Size | Notes |
|---|---|---|
| Model weights (3 MLX models) | 11.58 GB | Already downloaded before this step; nothing new fetched |
| Whole Hugging Face cache | 13.16 GB | Also holds whisper and MiniLM, which MAGI doesn't use |
| `backend/.venv` | 482 MB | Was 173 MB; `mlx`, `mlx-lm` and `transformers` added ~310 MB |
| `frontend/node_modules` | 149 MB | Unchanged |
| `frontend/dist`, `traces/`, `.git` | < 1 MB each | |

### Memory with the local council running

| Process | Loaded, idle | After a few runs | Notes |
|---|---|---|---|
| Qwen3.5-9B (MELCHIOR-1 and arbiter) | 5.41 GB | 5.81 GB | Arbiter shares this server, so it costs nothing extra |
| Qwen3-8B (BALTHASAR-2) | 4.65 GB | 5.06 GB | |
| Llama-3.2-3B (CASPAR-3) | 1.91 GB | 2.30 GB | |
| `magi-server` (FastAPI + LangGraph) | | 123 MB | |
| **Total** | **12.0 GB** | **13.3 GB** | Peak sampled *during* a deliberation: **~14.6 GB** |

Growth after runs is the KV prompt cache, which keeps recent prompts so follow-up turns are faster. `magi-mlx` caps it at 512 MB per server by default (`--prompt-cache-mb`).

### Time

| Mode | Full deliberation (2 debate rounds, 13 model calls) |
|---|---|
| Mock replay | ~45 s (recorded timing) |
| Local MLX council | 106-112 s (3 runs) |

## Findings

- **It fits, with about 3 GB of headroom** under the 17.76 GB GPU limit at peak.
- **The rest of the machine is the constraint.** With Chrome, Notion and other apps open, swap use went from 5.1 GB to 9.2 GB (of 10 GB) across the session, and free memory fell from 67% to 34%. Swap was already in use before MAGI started, so not all of that is MAGI, but the models are the largest single consumer.
- **Llama-3.2-3B is cheap but weak at strict JSON.** Before adding JSON repair it failed 2 of 4 turns. After, it failed none over 2 runs (3 replies were repaired). It also sometimes reports a stance that contradicts its own argument.

## Ways to use less memory

| Change | Saves | Cost |
|---|---|---|
| Close browser tabs and other heavy apps while running locally | 2-4 GB of pressure | None |
| Lower the cache: `magi-mlx --prompt-cache-mb 128` | Up to ~1 GB across servers | Slightly slower follow-up turns |
| Point BALTHASAR and CASPAR at the same Qwen3-8B server | ~2.3 GB (Llama server gone) | Less model diversity; Caspar gets a stronger model |
| Run only two servers and use Claude as the arbiter (mixed profile) | Nothing locally, better verdicts | Small API cost |
| Quantize the KV cache (`mlx_lm.server --kv-bits 8`) | Grows less per run | Small quality cost; not yet wired into `magi-mlx` |

## Log

| Date | Step | Disk change | Memory note |
|---|---|---|---|
| 2026-10-07 | Baseline (Claude + mock only) | `.venv` 173 MB, `node_modules` 149 MB | `magi-server` ~120 MB; no local models |
| 2026-10-07 | Step 1: one model per agent, MLX profile | `.venv` +310 MB (mlx, mlx-lm, transformers, langchain-openai, json-repair) | 12.0 GB loaded, 13.3 GB warm, ~14.6 GB peak |
| 2026-10-07 | Windows support: psutil, tasks.py, CI | `.venv` +1 MB (psutil); new README GIF 0.7 MB (replaces 1.0 MB) | No change; the report now also runs on Windows and Linux (RSS there, macOS `footprint` here) |
