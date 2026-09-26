#!/usr/bin/env bash
# Shared helpers for the repository entry-point scripts.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAG_DIR="${REPO_ROOT}/third_party/RAG-Anything"
RAG_EXPERIMENTS="rag-anything-experiments"

new_run_dir() {
    local step="$1"
    local run_dir="${REPO_ROOT}/runs/$(date +%Y%m%d_%H%M%S)_${step}"
    mkdir -p "${run_dir}"
    printf '%s' "${run_dir}"
}

require_dir() {
    [[ -d "$1" ]] || {
        printf 'missing directory: %s\n' "$1" >&2
        exit 1
    }
}

require_file() {
    [[ -f "$1" ]] || {
        printf 'missing file: %s\n' "$1" >&2
        exit 1
    }
}

# Copy an env template into the run directory with all paths made absolute, so
# the vendored scripts behave identically regardless of their working directory
# and never write artifacts back into third_party.
materialize_env() {
    local source_file="$1"
    local target_file="$2"
    local doc_file_path="$3"
    local rag_storage="$4"
    local benchmark_name="$5"
    local log_dir="$6"

    sed \
        -e "s|^DOC_FILE_PATH=.*|DOC_FILE_PATH=${doc_file_path}|" \
        -e "s|^RAG_STORAGE=.*|RAG_STORAGE=${rag_storage}|" \
        -e "s|^BENCH_QUERIES=.*|BENCH_QUERIES=${REPO_ROOT}/assets/queries_30.json|" \
        -e "s|^BENCHMARK_NAME=.*|BENCHMARK_NAME=${benchmark_name}|" \
        -e "s|^LOG_DIR=.*|LOG_DIR=${log_dir}|" \
        "${source_file}" > "${target_file}"
}
