#!/usr/bin/env bash
# Benchmark the served index, judge the answers and recompute the score.
#
# Usage:
#   bash scripts/run_eval.sh [env-file]
#
# The query server must already be running, because the benchmark talks to it
# over HTTP:
#   DOTENV_FILE=<run>/.env bash third_party/RAG-Anything/rag-anything-experiments/run.sh run_rag_server
#
# Results, logs and the score breakdown all land under a single runs/<ts>_eval
# directory.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${1:-${REPO_ROOT}/configs/env.tuned}"
DOC_FILE_PATH="${DOC_FILE_PATH:-${REPO_ROOT}/data/parsed_norm}"
RAG_STORAGE="${RAG_STORAGE:-${REPO_ROOT}/index/current}"

require_file "${ENV_SOURCE}"
require_dir "${RAG_DIR}"
require_dir "${RAG_STORAGE}"

RUN_DIR="$(new_run_dir eval)"
RESULTS_DIR="${RUN_DIR}/bench_results"
export DOTENV_FILE="${RUN_DIR}/.env"

materialize_env "${ENV_SOURCE}" "${DOTENV_FILE}" \
    "${DOC_FILE_PATH}" "${RAG_STORAGE}" "${RUN_DIR}/bench" "${RUN_DIR}"

BASELINE_SEARCH_TIME="$(sed -n 's/^BASELINE_SEARCH_TIME=//p' "${ENV_SOURCE}" | tail -n 1)"
BASELINE_BUILD_TIME="$(sed -n 's/^BASELINE_BUILD_TIME=//p' "${ENV_SOURCE}" | tail -n 1)"

printf 'run dir     : %s\n' "${RUN_DIR}"
printf 'env source  : %s\n' "${ENV_SOURCE}"
printf 'rag storage : %s\n' "${RAG_STORAGE}"

cd "${RAG_DIR}"
bash "${RAG_EXPERIMENTS}/run.sh" run_rag_unidocbench 2>&1 | tee "${RUN_DIR}/bench.log"
bash "${RAG_EXPERIMENTS}/run.sh" run_rag_eval_qwen_plus 2>&1 | tee "${RUN_DIR}/judge.log"

cd "${REPO_ROOT}"
PYTHONPATH="${REPO_ROOT}/src" uv run python -m hms.eval.score \
    --run-dir "${RESULTS_DIR}" \
    --baseline-search-time "${BASELINE_SEARCH_TIME}" \
    --baseline-build-time "${BASELINE_BUILD_TIME}" \
    --out "${RUN_DIR}/score.json" 2>&1 | tee "${RUN_DIR}/score.log"

printf 'artifacts   : %s\n' "${RUN_DIR}"
