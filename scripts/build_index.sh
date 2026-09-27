#!/usr/bin/env bash
# Build a fresh index through the vendored baseline.
#
# Usage:
#   bash scripts/build_index.sh [env-file] [--index <dir>]
#
# Defaults to configs/env.tuned, which only raises throughput; pass
# configs/env.baseline to reproduce the organiser's reference timing.
#
# DESTRUCTIVE BY DESIGN: this writes into the target store directory. Pointing
# it at index/baseline_0713 would overwrite the reference artifacts. The script
# refuses to target a directory that already holds a usable store unless
# --force is passed. Building into index/baseline_0713 would also be pointless:
# all 100 documents are already in its processed_file_set, so every file would
# be skipped and the normalized corpus would never be read.
#
# All paths handed to the baseline are absolute, so nothing depends on the
# working directory the vendored scripts happen to run from.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${REPO_ROOT}/configs/env.tuned"
RAG_STORAGE="${REPO_ROOT}/index/current"
DOC_FILE_PATH="${REPO_ROOT}/data/parsed_norm"
FORCE=0

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --index) RAG_STORAGE="${2:?--index needs a path}"; shift 2 ;;
        --docs) DOC_FILE_PATH="${2:?--docs needs a path}"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage 0 ;;
        -*) printf 'unknown option: %s\n\n' "$1" >&2; usage 1 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done

if [[ ${#POSITIONAL[@]} -gt 0 ]]; then
    ENV_SOURCE="${POSITIONAL[0]}"
fi

require_file "${ENV_SOURCE}"
require_dir "${RAG_DIR}"
require_dir "${DOC_FILE_PATH}"

# Safety first: refuse to clobber an existing store before doing anything else,
# so a typo is caught even in an environment where the endpoints are down.
if looks_like_store "${RAG_STORAGE}" && [[ "${FORCE}" != "1" ]]; then
    printf 'refusing to overwrite an existing store: %s\n' "${RAG_STORAGE}" >&2
    printf 'pass --force to build into it, or --index <other-dir> to build elsewhere\n' >&2
    if [[ -s "${RAG_STORAGE}/kv_store_doc_status.json" ]]; then
        printf 'note: this store already has document status, so processed documents\n' >&2
        printf '      would be skipped and the new corpus would not be read\n' >&2
    fi
    exit 1
fi

# LightRAG streams data out through temporary subdirectories and only removes
# them on a clean finish, so an interrupted run leaves empty directories that a
# later run can trip over.
leftovers="$(empty_subdirs "${RAG_STORAGE}")"
if [[ -n "${leftovers}" ]]; then
    printf 'cleaning empty leftovers from an interrupted run:\n'
    printf '%s\n' "${leftovers}" | sed 's/^/  /'
    printf '%s\n' "${leftovers}" | xargs rmdir 2>/dev/null || true
fi

bash "${REPO_ROOT}/scripts/check_endpoints.sh" "${ENV_SOURCE}" || exit 1

RUN_DIR="$(new_run_dir build)"
export DOTENV_FILE="${RUN_DIR}/.env"

materialize_env "${ENV_SOURCE}" "${DOTENV_FILE}" \
    "${DOC_FILE_PATH}" "${RAG_STORAGE}" "${RUN_DIR}/bench" "${RUN_DIR}"

printf 'run dir     : %s\n' "${RUN_DIR}"
printf 'env source  : %s\n' "${ENV_SOURCE}"
printf 'documents   : %s\n' "${DOC_FILE_PATH}"
printf 'rag storage : %s\n' "${RAG_STORAGE}"
printf 'env file    : %s\n' "${DOTENV_FILE}"

cd "${RAG_DIR}"
bash "${RAG_EXPERIMENTS}/run.sh" run_rag_build 2>&1 | tee "${RUN_DIR}/build.log"

printf 'build log   : %s\n' "${RUN_DIR}/build.log"
