#!/usr/bin/env bash
# Start the query server against an existing index.
#
# Usage:
#   bash scripts/serve_index.sh [options]
#
#   --index <dir>   index directory (default: index/baseline_0713 when it
#                   exists, otherwise index/current, otherwise the most
#                   recently modified directory under index/)
#   --env <file>    environment template (default: configs/env.tuned)
#   -h, --help      show this message
#
# Two things this script handles that are easy to get wrong by hand:
#
# 1. Working directory. A store built from data/parsed_norm holds absolute image
#    paths and works from anywhere. A legacy store such as index/baseline_0713
#    holds relative paths of the form mineru-parsed/<doc>/auto/images/<hash>.jpg,
#    which only resolve when the server runs from third_party/RAG-Anything. The
#    script detects which case applies and starts the server accordingly.
#
# 2. The link that repairs those relative paths. It is created only when the
#    store needs it, and lives inside the vendored tree as an untracked symlink.
#    Undo it with: bash scripts/enable_vlm_images.sh --remove

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${REPO_ROOT}/configs/env.tuned"
INDEX_REQUESTED=""
DOC_FILE_PATH="${REPO_ROOT}/data/parsed_norm"

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --index) INDEX_REQUESTED="${2:?--index needs a path}"; shift 2 ;;
        --env) ENV_SOURCE="${2:?--env needs a path}"; shift 2 ;;
        --docs) DOC_FILE_PATH="${2:?--docs needs a path}"; shift 2 ;;
        -h|--help) usage 0 ;;
        -*) printf 'unknown option: %s\n\n' "$1" >&2; usage 1 ;;
        *) printf 'unexpected argument: %s\n\n' "$1" >&2; usage 1 ;;
    esac
done

require_file "${ENV_SOURCE}"
require_dir "${RAG_DIR}"

if [[ -z "${INDEX_REQUESTED}" ]]; then
    INDEX_REQUESTED="${REPO_ROOT}/index/current"
fi

# Same rule as run_eval: an explicit --index must name a usable store, while a
# default request may fall back to any usable store.
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
fi

bash "${REPO_ROOT}/scripts/check_endpoints.sh" "${ENV_SOURCE}" serve || exit 1

# A legacy store references images by a relative prefix; a normalized store uses
# absolute paths and needs none of this.
needs_image_link() {
    local store="$1"
    local chunks="${store}/kv_store_text_chunks.json"
    [[ -f "${chunks}" ]] || return 1
    grep -q 'Image Path: mineru-parsed/' "${chunks}"
}

RUN_DIR="$(new_run_dir serve)"
export DOTENV_FILE="${RUN_DIR}/.env"

materialize_env "${ENV_SOURCE}" "${DOTENV_FILE}" \
    "${DOC_FILE_PATH}" "${RAG_STORAGE}" "${RUN_DIR}/bench" "${RUN_DIR}"

printf 'run dir     : %s\n' "${RUN_DIR}"
printf 'rag storage : %s\n' "${RAG_STORAGE}"
printf 'env file    : %s\n' "${DOTENV_FILE}"

if needs_image_link "${RAG_STORAGE}"; then
    printf 'image paths : relative, repairing them so multimodal retrieval stays on\n'
    bash "${REPO_ROOT}/scripts/enable_vlm_images.sh" || exit 1
else
    printf 'image paths : absolute, no link required\n'
    # Remove a stale link so it cannot mask a genuine path problem.
    if [[ -L "${RAG_DIR}/mineru-parsed" ]]; then
        bash "${REPO_ROOT}/scripts/enable_vlm_images.sh" --remove
    fi
fi

printf '\nstarting server from %s\n' "${RAG_DIR}"
printf 'evaluate in another terminal with: bash scripts/run_eval.sh --index %s\n\n' "${RAG_STORAGE}"

cd "${RAG_DIR}"
bash "${RAG_EXPERIMENTS}/run.sh" run_rag_server 2>&1 | tee "${RUN_DIR}/serve.log"
