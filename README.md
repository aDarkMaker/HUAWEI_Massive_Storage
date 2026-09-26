# HUAWEI Massive Storage

Multimodal representation and retrieval for the Agentic AI track of the
HUAWEI Massive Storage competition. The system targets high-accuracy
question answering over mixed-layout PDF knowledge bases where answers
frequently depend on charts, tables and formulas rather than prose.

## Layout

```
assets/       small official artifacts (validation queries, problem statement)
configs/      environment templates for the upstream RAG-Anything pipeline
docs/         competition constraints, architecture, data and setup notes
scripts/      thin executable entry points
src/hms/      library code
tests/        standard-library unit tests
third_party/  vendored upstream baseline, read-only
data/         knowledge base (gitignored, see docs/data.md)
index/        built vector and graph stores (gitignored)
runs/         logs, timings and evaluation output (gitignored)
```

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and the competition data placed
under `data/` as described in [docs/data.md](docs/data.md).

```bash
make setup      # pin Python 3.12 and create the project-local .venv
make test       # run the unit tests
make normalize  # normalize math spans and absolutize image paths
make compact    # strip redundant vector payloads from the nano vdb files
make build      # build the index through the vendored baseline
make score      # recompute the competition score
```

See [docs/setup.md](docs/setup.md) for the full reproduction steps.

## Environment

The project environment is managed by uv and lives entirely inside the
repository at `.venv/`. Runtime code depends only on the Python standard
library. Optional development tools are defined in the `lint` dependency
group and are not installed by a plain `uv sync`.

The vendored baseline under `third_party/RAG-Anything` keeps its own
`pyproject.toml` and `uv.lock`, so it resolves independently from the root
project. It is never edited in place.
