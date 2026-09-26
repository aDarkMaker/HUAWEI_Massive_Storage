#!/usr/bin/env bash
# Build the index through the vendored baseline.
#
# Usage:
#   bash scripts/build_index.sh [env-file]
#
# Defaults to configs/env.tuned, which only raises throughput; pass
# configs/env.baseline to reproduce the organiser's reference timing.
#
# All paths handed to the baseline are absolute, and every artifact it produces
# (store, logs, results) is redirected under runs/ or index/ so third_party
# stays pristine.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${1:-${REPO_ROOT}/configs/env.tuned}"
DOC_FILE_PATH="${DOC_FILE_PATH:-${REPO_ROOT}/data/parsed_norm}"
RAG_STORAGE="${RAG_STORAGE:-${REPO_ROOT}/index/current}"

require_file "${ENV_SOURCE}"
require_dir "${RAG_DIR}"
require_dir "${DOC_FILE_PATH}"

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
