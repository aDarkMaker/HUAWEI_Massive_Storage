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
| 237 figure chunks and 148 table chunks carry a literal `Captions: None` | The reasoner sees a placeholder instead of the caption text |
| `MAX_ASYNC`, `WORKERS`, `MAX_CONCURRENT_FILES` all pinned to 1 | vLLM runs with `--max-num-seqs 4`, so three quarters of the serving capacity is idle during the build |
| `ENABLE_LLM_CACHE_FOR_EXTRACT` off in practice | Every retrieval experiment forces a full re-extraction |
| `vdb_*.json` stores each embedding twice | The relation store reaches 655 MB, well past GitHub's 100 MB file limit |

This repository addresses the numerals, the concurrency and the store bloat.
Caption recovery and the table-heavy retrieval path are tracked separately.

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
