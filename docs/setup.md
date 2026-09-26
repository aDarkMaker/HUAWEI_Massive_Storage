# Setup

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages the interpreter and the virtual
  environment. Nothing is installed into the system Python.
- For a full run: a GPU host serving `Qwen3-VL-8B-Instruct` on port 8100,
  `bge-m3` on 8001 and `bge-reranker-v2-m3` on 8002, matching the endpoints in
  `configs/env.baseline`. The normalizer, the compactor and the unit tests need
  none of this.

## Environment

```bash
make setup      # uv python pin 3.12 && uv sync
```

This creates `.venv/` inside the repository. Runtime dependencies are empty, so
`uv sync` only resolves the project itself and is fully offline-safe. Confirm:

```bash
uv lock --check
uv run python -c "import sys; print(sys.prefix)"
```

`sys.prefix` must point at the repository-local `.venv`. `uv python pin 3.12`
writes `.python-version`, which is committed; `uv.lock` is committed too. The
system Python is never modified.

Development tooling is opt-in:

```bash
uv sync --group lint
uv run --group lint ruff check src scripts tests
```

`ruff` lives in the `lint` dependency group rather than `dev`, so a plain
`uv sync` does not install it.

## Vendored baseline

`third_party/RAG-Anything` is the upstream project plus the organiser's
experiments. It keeps its own `pyproject.toml` and `uv.lock`, and `run.sh`
invokes `uv run` which resolves against that local project. It is read-only: the
scripts here reach it by changing directory and exporting an absolute
`DOTENV_FILE`, so no generated file is written back into it.

No uv workspace is used on purpose. A workspace would make the root lock file
own the vendored dependencies and rewrite the vendored `uv.lock`.

## Reproducing a run

```bash
bash scripts/fetch_data.sh              # confirm the corpus is in place
make normalize                          # data/parsed -> data/parsed_norm
make compact                            # drop redundant vectors from index/*
make build                              # uses configs/env.tuned by default
bash scripts/build_index.sh configs/env.baseline   # reference timing, for comparison
```

`scripts/build_index.sh` writes a materialized `.env` with absolute paths into
the run directory, then calls the vendored `run.sh run_rag_build` and tees the
output to `runs/<timestamp>_build/build.log`.

To evaluate, start the query server in one terminal and run the benchmark in
another:

```bash
RUN=runs/<timestamp>_build
DOTENV_FILE="$PWD/$RUN/.env" bash third_party/RAG-Anything/rag-anything-experiments/run.sh run_rag_server

make score                              # recompute from the newest run directory
```

Or drive the whole thing, benchmark, judger and score, in one step:

```bash
bash scripts/run_eval.sh
```

## Tests

```bash
make test          # uv run python -m unittest discover -s tests -t . -v
```

The suite is standard-library `unittest` only and runs without a GPU, without
the corpus and without network access. It covers the numeric normalizer: split
digits, LaTeX wrappers, symbol mapping, the escaped-space relation form, prose
immutability and idempotence.

## Scoring

`make score` recomputes the graded formula and prints the penalty breakdown:

```bash
PYTHONPATH=src uv run python -m hms.eval.score \
    --run-dir runs/<timestamp>_eval/bench_results \
    --baseline-search-time 2300 \
    --baseline-build-time 3224
```

It needs `rag_answers_judged_summary.json` and `timings.json` in the results
directory, both produced by the benchmark and the judger. The breakdown is
written to `runs/<timestamp>_score/score.json`, together with an explicit pass or
fail on the 80% preliminary and 85% final accuracy gates.
