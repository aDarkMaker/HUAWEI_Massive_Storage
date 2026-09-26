# Data

The knowledge base is large and is never tracked by git. `.gitignore` excludes
`/data/`, `/index/` and `/runs/` at the repository root, anchored so that
`src/hms/index/` and any other nested `index` package keep being tracked.

## Sizes, and why nothing is committed

| Path | Size | Tracked |
| --- | --- | --- |
| `data/parsed/` | 1.1 GB | no |
| `data/raw/pdfs/` | 248 MB | no |
| `index/baseline_0713/` | 1.1 GB | no |
| `third_party/RAG-Anything/` | 6 MB | yes (largest file 1.56 MB) |
| `assets/` | 728 KB | yes |

Two files in the reference store exceed GitHub's 100 MB per-file hard limit on
their own, before compaction:

- `index/baseline_0713/vdb_relationships.json` 655 MB
- `index/baseline_0713/vdb_entities.json` 365 MB

`scripts/compact_index.py` brings those to roughly 455 MB and 254 MB, which is
still far above the limit, so the index can never be pushed. It is rebuilt
locally or shipped as a release asset.

## Layout

```
data/
  raw/pdfs/                     source PDFs, 100 documents
  parsed/                       MinerU output, one directory per document
    <doc>/auto/<doc>_content_list.json
    <doc>/auto/images/<hash>.jpg
  parsed_norm/                  produced by scripts/normalize_corpus.py
index/
  baseline_0713/                the reference store shipped with the task
  current/                      scratch store used by scripts/build_index.sh
runs/
  <timestamp>_<step>/           per-step logs and machine-readable reports
```

## MinerU output

The pipeline starts from `*_content_list.json`, which is a flat list of typed
blocks. The types that matter here are `text`, `equation`, `image` and `table`.
Each block carries a `text` field; `image` and `table` blocks additionally carry
an `img_path`.

The reference run wrote `img_path` values relative to a directory that no longer
exists, so the baseline's `change_img_paths.py` has to be run from a specific
working directory to repair them. That fixer only rewrites references starting
with `images/`, while every reference in this corpus starts with
`mineru-parsed/`, so it does nothing here; see `docs/competition.md` for the
consequences. `scripts/normalize_corpus.py` instead derives the path from the
file name and rewrites `img_path` to an absolute path inside `data/parsed`,
which makes all downstream consumers working-directory independent. It also
fails the run if any written path is not absolute, because a relative path is
what silently disables the multimodal query path. Images are not copied: only
the JSON is rewritten.

## Obtaining the data

The dataset is distributed by the organisers and is not reproducible from this
repository. Place it as shown above, then verify:

```bash
bash scripts/fetch_data.sh
```

`data/parsed` is treated as an input rather than a build product. Re-running
MinerU is possible through the vendored baseline (`run.sh parse_docs`) but its
runtime is heavy and its output is stable, so parsing sits outside the measured
build window and outside this pipeline.

## Normalized corpus

`make normalize` reads `data/parsed` and writes `data/parsed_norm`. The two trees
differ in three ways:

- math spans inside `text` and `equation` blocks are rewritten;
- `img_path` is rewritten to an absolute path;
- multimodal blocks with no payload at all are dropped (12 of them, listed in
  `docs/competition.md`), unless `--keep-blank-blocks` is passed.

Table bodies, captions and every other field are copied verbatim, which keeps
review simple:

```bash
diff <(python -m json.tool data/parsed/<doc>/auto/<doc>_content_list.json) \
     <(python -m json.tool data/parsed_norm/<doc>/auto/<doc>_content_list.json) | head
```

Per-rule hit counts and the number of missing images are written to
`runs/<timestamp>_normalize/normalize_stats.json`.
