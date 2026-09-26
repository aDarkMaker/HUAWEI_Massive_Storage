# Competition constraints

Source: `assets/Agentic AI 多模态表征与检索赛题.docx` and the organiser's
reference implementation under `third_party/RAG-Anything`.

## Task

Build a retrieval-augmented system over a 100-document PDF knowledge base and
answer a set of questions about it. Two tracks are offered and a team enters
exactly one. This repository targets the multimodal representation and
retrieval track.

The reference baseline is RAG-Anything 1.2.9 on top of a LightRAG 1.4.9.11 core
with the `nano-vectordb` storage backend, `bge-m3` embeddings,
`bge-reranker-v2-m3` reranking and `Qwen3-VL-8B-Instruct` for both extraction
and judging. MinerU produces the parsed representation and its runtime settings
are pinned in `configs/env.baseline`.

## Scoring

```
accuracy_score = 100 * accuracy
search_penalty = 1 * min((search_time - baseline_search) / baseline_search, 1)
build_penalty  = 5 * min((build_time  - baseline_build)  / baseline_build,  1)
final_score    = accuracy_score - search_penalty - build_penalty
```

Consequences that drive the optimisation priorities:

- Accuracy dominates. Each percentage point of accuracy is worth the entire
  search penalty budget, so no latency trade that risks accuracy is acceptable.
- Both penalties saturate. A build up to twice the baseline costs at most 5
  points, and anything slower costs the same 5 points, so build time only
  matters until it is halved.
- Search time has a 1 point ceiling, so even a 10x slowdown costs 1 point.

The reported build time is measured around RAG initialisation plus insertion of
the not-yet-processed documents. PDF parsing is outside that window, and
documents already recorded in `processed_file_set` are skipped, so a
pre-built store is very cheap to rebuild from.

Accuracy gates: 80% for the preliminary round, 85% for the finals.

## Why the baseline underperforms

| Finding | Impact |
| --- | --- |
| MinerU splits math spans per glyph (`$\{ 1 0 \} ^ { 1 2 }$` for `10^{12}`) | Numerals become unretrievable, and 77% of questions need table or figure reasoning |
| The reference store keeps `img_path` as a relative `mineru-parsed/...` path | The path no longer resolves from any working directory, so a query that needs to open the figure cannot find it |
| `MAX_ASYNC`, `WORKERS`, `MAX_CONCURRENT_FILES` all pinned to 1 | vLLM runs with `--max-num-seqs 4`, so three quarters of the serving capacity is idle during the build |
| `ENABLE_LLM_CACHE_FOR_EXTRACT` off in practice | Every retrieval experiment forces a full re-extraction |
| `vdb_*.json` stores each embedding twice | The relation store reaches 655 MB, well past GitHub's 100 MB file limit |
| 12 `table` blocks are emitted completely blank | Each becomes a chunk holding only the model's prose about a table it never saw |

This repository addresses the numerals, the image paths, the concurrency and the
store bloat. The blank table blocks are a small, separable follow-up.

## Verified defect: the reference index cannot resolve a single image

The reference store references 1,112 figures and tables, and none of those image
paths can be opened. Measured against `index/baseline_0713`:

| Check | Result |
| --- | --- |
| Image references in `kv_store_text_chunks.json` | 1,112 |
| Absolute paths | 0 |
| Resolve from the repository root | 0 / 1,112 |
| Resolve from `third_party/RAG-Anything` | 0 / 1,112 |
| Resolve from `rag-anything-experiments` | 0 / 1,112 |
| Resolve after rewriting the `mineru-parsed/` prefix to `data/parsed/` | 1,112 / 1,112 |

Every path has the form
`mineru-parsed/<doc>/auto/images/<hash>.jpg`, a relative path whose base
directory no longer exists.

### Why this silently disables multimodal retrieval

`QUERY_VLM_ENHANCED=true` is set in the reference environment, and the query path
is `RAGAnything.aquery` then `aquery_vlm_enhanced`, then
`_process_image_paths_for_vlm`. That last method validates each matched path with
`validate_image_file`, which is a `Path(...).exists()` call resolved against the
process working directory. With all 1,112 failing validation, `images_found`
stays 0, and the method then does this:

```python
if not images_found:
    self.logger.info("No valid images found, falling back to normal query")
    query_param = QueryParam(mode=mode, **kwargs)
    return await self.lightrag.aquery(query, param=query_param, system_prompt=system_prompt)
```

So the whole multimodal query mechanism is abandoned and the run degrades to a
plain text-only LightRAG query. On a benchmark where 77% of the questions need
table or figure reasoning, that is the most consequential defect found so far.
It is invisible in the output because the fallback is logged at INFO level and
returns a normal-looking answer.

### Root cause

The referenced fixer, `utils/change_img_paths.py`, only rewrites paths that start
with `images/`:

```python
if p.startswith("images/"):
    full_path = str(base_dir / p)
```

No path in this corpus starts with `images/`, so the fixer is a no-op and the
relative paths survive into the store. `scripts/normalize_corpus.py` sidesteps
this by deriving the path from the file name and resolving it against
`data/parsed`, which is what makes the rewritten corpus work.

### Testing the impact without rebuilding

Because the paths are relative, making them resolve is a matter of placing
`data/parsed` where the relative prefix points. For a query server started from
`third_party/RAG-Anything`, the empty `mineru-parsed/` directory needs to become
that link:

```bash
rmdir third_party/RAG-Anything/mineru-parsed
ln -s "$PWD/data/parsed" third_party/RAG-Anything/mineru-parsed
```

For a server started from the repository root, the link goes at the root
instead. The mapping must be verified for the actual working directory before
the numbers mean anything:

```bash
cd third_party/RAG-Anything
ls mineru-parsed/commerce_manufacturing_0501317/auto/images/ | head -3
```

A quick way to see whether it worked is to grep the run log for the two messages
from `_process_image_paths_for_vlm`, `Image validation failed for` and
`No valid images found, falling back to normal query`. They should disappear.

## Retracted finding: `Captions: None`

An earlier revision of this document claimed that 237 figure chunks and 148
table chunks were carrying a hardcoded `Captions: None`. That was wrong, and it
is retracted. Measured against `index/baseline_0713` and the corpus:

| Case | Chunks | Verdict |
| --- | --- | --- |
| Real caption present in the chunk | 738 | Correct; `_apply_chunk_template` reads `image_caption` / `table_caption` properly |
| No caption in MinerU output | 237 | Correct behaviour. The block genuinely has none, and the vision model still supplies a 1,000+ character description that is stored in the chunk |
| Table has no caption but has `table_body` | 137 | Correct behaviour; the `<table>` structure is already in the chunk |
| Source block is entirely blank | 12 | A real, if small, defect |

So there is no caption-reading bug to fix. `Captions: None` is the honest value
for blocks that MinerU never captioned, and those chunks are not empty: they
carry a grounded visual analysis instead.

The 12 genuinely blank blocks are the real residue. MinerU emitted `table`
entries with an empty `img_path`, an empty `table_body` and no caption, and each
one becomes a chunk containing only model prose about a table it could not see.
In the reference store the model's own text concedes this, for example "The
table, though not visually presented, is referenced in the context".

| Document | Page |
| --- | --- |
| `commerce_manufacturing_2024985` | 3 |
| `commerce_manufacturing_2701564` | 12 |
| `commerce_manufacturing_3429581` | 10 |
| `construction_2928102` | 3, 11 |
| `crm_4502338` | 4, 5, 6, 7 |
| `crm_5963931` | 20 |
| `education_4813144` | 14 |
| `healthcare_7083619` | 4 |

## Open questions for the organisers

1. May a pre-built index be submitted as a solution artifact? Only
   `processed_file_set` entries are skipped, so a shipped store is worth most of
   the 5 point build penalty.
2. Is there a hard wall-clock limit? The `min(..., 1)` cap implies the build
   penalty stops growing, but the problem statement still refers to finishing
   "within the specified time".
3. Does the `nano-vectordb` constraint forbid complementary BM25 or sparse
   indexes built outside the library?
4. Which `lightrag-hku` release does the grader run? The vendored lock file
   resolves to 1.5.4 while the problem statement names 1.4.9.11.
