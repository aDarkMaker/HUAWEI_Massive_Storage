#!/usr/bin/env bash
# Check that the model endpoints named in an environment file are reachable.
#
# Usage:
#   bash scripts/check_endpoints.sh [env-file] [build|eval|serve]
#
# Why this exists: the build talks to the LLM over HTTP for every chunk, and it
# discovers an unreachable endpoint only after retrying per chunk with
# exponential backoff. A build that cannot succeed therefore wastes minutes and
# fills the log with retry noise before failing. A two second check up front
# turns that into an immediate, explicit error.
#
# The two modes need different services: a build generates the index and needs
# the extraction LLM, the VLM, the embedder and the reranker; an eval only talks
# to the already-running query server and the judging LLM, because embedding and
# reranking happen inside that server.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ENV_SOURCE="${REPO_ROOT}/configs/env.tuned"
MODE="build"

for arg in "$@"; do
    case "${arg}" in
        build|eval|serve) MODE="${arg}" ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) ENV_SOURCE="${arg}" ;;
    esac
done

require_file "${ENV_SOURCE}"

# endpoint_key|label
if [[ "${MODE}" == "eval" ]]; then
    ENDPOINTS=(
        "RAG_BINDING_HOST|query server"
        "JUDGER_BINDING_HOST|judging LLM"
    )
elif [[ "${MODE}" == "serve" ]]; then
    # The server embeds and reranks in-process, so it needs those two services
    # before it can answer a single query.
    ENDPOINTS=(
        "EMBEDDING_BINDING_HOST|embedding"
        "RERANK_ENDPOINT|reranker"
        "VLLM_BINDING_HOST|VLM (query-time captioning)"
    )
else
    ENDPOINTS=(
        "LLM_BINDING_HOST|LLM (extraction)"
        "VLLM_BINDING_HOST|VLM (image captioning)"
        "EMBEDDING_BINDING_HOST|embedding"
        "RERANK_ENDPOINT|reranker"
    )
fi

status=0
declare -a missing=()

read_value() {
    sed -n "s/^$1=//p" "${ENV_SOURCE}" | tail -n 1 | tr -d '"'
}

probe() {
    local label="$1"
    local url="$2"
    # Derive the port from the URL and check that something is listening.
    local host_port="${url#*://}"
    host_port="${host_port%%/*}"
    local host="${host_port%%:*}"
    local port="${host_port##*:}"
    if [[ "${host}" == "${port}" ]]; then
        port="80"
    fi

    if "${REPO_ROOT}/.venv/bin/python" - "$host" "$port" <<'PY' 2>/dev/null
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=2):
        pass
except OSError:
    raise SystemExit(1)
PY
    then
        printf 'ok      %-32s %s\n' "${label}" "${url}"
    else
        printf 'DOWN    %-32s %s\n' "${label}" "${url}"
        missing+=("${label} -> ${url}")
        status=1
    fi
}

printf 'checking endpoints from %s\n\n' "${ENV_SOURCE}"
for entry in "${ENDPOINTS[@]}"; do
    key="${entry%%|*}"
    label="${entry##*|}"
    url="$(read_value "${key}")"
    if [[ -z "${url}" ]]; then
        printf 'unset   %-32s (%s)\n' "${label}" "${key}"
        continue
    fi
    probe "${label}" "${url}"
done

if [[ "${MODE}" == "eval" ]]; then
    MODE_LABEL="an eval"
elif [[ "${MODE}" == "serve" ]]; then
    MODE_LABEL="the query server"
else
    MODE_LABEL="a build"
fi

if [[ "${status}" -ne 0 ]]; then
    printf '\n%s endpoint(s) unreachable for %s. Fix the env file before running.\n' \
        "${#missing[@]}" "${MODE_LABEL}" >&2
    printf 'The model paths and hosts in the env file are machine-specific, so on\n' >&2
    printf 'a new host they usually need updating first:\n' >&2
    printf '  %s\n' "grep -E '^(LLM|VLLM|EMBEDDING|RERANK|JUDGER|RAG)_' ${ENV_SOURCE}" >&2
    if [[ "${MODE}" == "eval" ]]; then
        printf 'The query server is started separately:\n' >&2
        printf '  bash scripts/serve_index.sh\n' >&2
    elif [[ "${MODE}" == "serve" ]]; then
        printf 'The server embeds and reranks in-process, so it cannot serve a query\n' >&2
        printf 'until these are listening.\n' >&2
    else
        printf 'A build against a dead endpoint retries per chunk and then fails.\n' >&2
    fi
fi

exit "${status}"
