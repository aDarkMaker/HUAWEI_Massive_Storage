#!/usr/bin/env bash
# Benchmark the served index, judge the answers and recompute the score.
#
# Usage:
#   bash scripts/run_eval.sh [options]
#
#   --env <file>         environment template (default: configs/env.tuned)
#   --index <dir>        index directory (default: index/current, or the most
#                        recently modified directory under index/ when
#                        index/current does not exist)
#   --docs <dir>         parsed corpus path recorded in the materialized env
#                        (default: data/parsed_norm)
#   -h, --help           show this message
#
# The benchmark only talks to the query server over HTTP via RAG_BINDING_HOST.
# RAG_STORAGE is consulted by the *server*, not by the benchmark, so pointing
# this script at a pre-built store such as index/baseline_0713 is enough to
# evaluate it: no rebuild and no matching server-side value are required.
#
# The query server must already be running:
#   bash scripts/serve_index.sh --index index/baseline_0713
#
# Results, logs and the score breakdown all land under a single runs/<ts>_eval
# directory.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${REPO_ROOT}/configs/env.tuned"
INDEX_REQUESTED="${REPO_ROOT}/index/current"
DOC_FILE_PATH="${REPO_ROOT}/data/parsed_norm"

usage() {
    sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env) ENV_SOURCE="${2:?--env needs a path}"; shift 2 ;;
        --index) INDEX_REQUESTED="${2:?--index needs a path}"; shift 2 ;;
        --docs) DOC_FILE_PATH="${2:?--docs needs a path}"; shift 2 ;;
        -h|--help) usage 0 ;;
        -*) printf 'unknown option: %s\n\n' "$1" >&2; usage 1 ;;
        *) printf 'unexpected argument: %s\n\n' "$1" >&2; usage 1 ;;
    esac
done

require_file "${ENV_SOURCE}"
require_dir "${RAG_DIR}"

# A rejected empty request must name the problem, not fall back to a store the
# user did not ask for; a rejected default may fall back.
INDEX_EXPLICIT=0
[[ "${INDEX_REQUESTED}" != "${REPO_ROOT}/index/current" ]] && INDEX_EXPLICIT=1

if ! RAG_STORAGE="$(resolve_index_dir "${INDEX_REQUESTED}" "${INDEX_EXPLICIT}")"; then
    printf 'no usable index directory available\n' >&2
    printf 'requested: %s\n' "${INDEX_REQUESTED}" >&2
    printf 'candidates (a store needs kv_store_doc_status.json and vdb_*.json):\n' >&2
    list_index_dirs | sed 's/^/  /' >&2
    exit 1
fi

if [[ "${RAG_STORAGE}" != "${INDEX_REQUESTED}" ]]; then
    printf 'note: %s is not a usable store, using %s\n' "${INDEX_REQUESTED}" "${RAG_STORAGE}"
    printf '      (pin it with --index)\n'
fi

bash "${REPO_ROOT}/scripts/check_endpoints.sh" "${ENV_SOURCE}" eval || exit 1

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

if [[ -d "${RESULTS_DIR}" ]]; then
    cd "${RESULTS_DIR}"
else
    cd "${REPO_ROOT}"
fi

PYTHONPATH="${REPO_ROOT}/src" uv run python -m hms.eval.score \
    --run-dir "${RESULTS_DIR}" \
    --baseline-search-time "${BASELINE_SEARCH_TIME}" \
    --baseline-build-time "${BASELINE_BUILD_TIME}" \
    --out "${RUN_DIR}/score.json" 2>&1 | tee "${RUN_DIR}/score.log"

printf 'artifacts   : %s\n' "${RUN_DIR}"
