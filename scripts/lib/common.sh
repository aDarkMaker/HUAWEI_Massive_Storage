#!/usr/bin/env bash
# Shared helpers for the repository entry-point scripts.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAG_DIR="${REPO_ROOT}/third_party/RAG-Anything"
RAG_EXPERIMENTS="rag-anything-experiments"

# Keys that the vendored scripts read as filesystem locations.
PATH_KEYS_RE='^(RAG_STORAGE|DOC_FILE_PATH|DOCS_PATH|PARSER_OUTPUT_DIR|BENCH_QUERIES|OUTPUT_DIR|LOG_DIR)='

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

# Copy an env template into the run directory with every path made absolute.
#
# This matters more than it looks. The vendored scripts call
# `load_dotenv(dotenv_path=DOTENV_FILE, override=True)`, which writes the
# template's raw values into os.environ. A relative value such as
# `RAG_STORAGE=index/baseline_0713` is then resolved against the *process*
# working directory, and the vendored scripts run from third_party/RAG-Anything.
# The store is looked up at third_party/RAG-Anything/index/baseline_0713, which
# does not exist, so LightRAG creates an empty store there and reports zero
# records. Nothing errors; it just silently works on the wrong directory.
absolutize_paths() {
    local file="$1"
    local tmp="${file}.tmp"
    : > "${tmp}"
    local line key value
    while IFS= read -r line || [[ -n "${line}" ]]; do
        if [[ "${line}" =~ ${PATH_KEYS_RE} ]]; then
            key="${line%%=*}"
            value="${line#*=}"
            value="${value%"${value##*[![:space:]]}"}"
            if [[ -n "${value}" && "${value}" != /* ]]; then
                printf '%s=%s\n' "${key}" "${REPO_ROOT}/${value}" >> "${tmp}"
                continue
            fi
        fi
        printf '%s\n' "${line}" >> "${tmp}"
    done < "${file}"
    mv "${tmp}" "${file}"
}

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

    absolutize_paths "${target_file}"
}

# A store the server can actually answer from: it has document status and at
# least one vector store. Guards against half-built or abandoned directories
# being picked up and evaluated as if they were real.
looks_like_store() {
    local dir="$1"
    [[ -d "${dir}" ]] || return 1
    [[ -s "${dir}/kv_store_doc_status.json" ]] || return 1
    compgen -G "${dir}/vdb_*.json" > /dev/null
}

list_index_dirs() {
    ls -dt "${REPO_ROOT}"/index/*/ 2>/dev/null | sed 's:/$::' || true
}

# Resolve which store to use.
#
# A store is only usable if it has document status and at least one vector
# store; a directory that merely exists may be the debris of an interrupted
# run, and evaluating one silently produces nonsense scores. An explicit
# request must name a usable store, otherwise the caller is told so rather than
# being quietly redirected. A default request may fall back, preferring a usable
# index/current, then the reference store, then the newest usable directory.
resolve_index_dir() {
    local requested="$1"
    local explicit="${2:-0}"

    if [[ "${explicit}" == "1" ]]; then
        looks_like_store "${requested}" || return 1
        printf '%s' "${requested}"
        return 0
    fi

    local candidate
    for candidate in "${requested}" \
                     "${REPO_ROOT}/index/current" \
                     "${REPO_ROOT}/index/baseline_0713"; do
        if looks_like_store "${candidate}"; then
            printf '%s' "${candidate}"
            return 0
        fi
    done

    while IFS= read -r candidate; do
        [[ -n "${candidate}" ]] || continue
        if looks_like_store "${candidate}"; then
            printf '%s' "${candidate}"
            return 0
        fi
    done < <(list_index_dirs)

    return 1
}

# Report directories under a store that a previous run left behind, in the
# layout LightRAG creates while streaming data out.
empty_subdirs() {
    local dir="$1"
    [[ -d "${dir}" ]] || return 0
    find "${dir}" -mindepth 1 -maxdepth 1 -type d -empty 2>/dev/null || true
}
