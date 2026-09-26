#!/usr/bin/env bash
# Verify that the competition data is in place.
#
# The knowledge base (1.3 GB of parsed PDFs, 248 MB of source PDFs) is not
# tracked by git. Populate it once and this script will confirm the layout that
# the rest of the pipeline expects.
#
# Expected sources:
#   data/raw/pdfs/     source PDFs, one directory of 100 documents
#   data/parsed/       MinerU output, <doc>/auto/<doc>_content_list.json
#
# See docs/data.md for the full description.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

status=0

check() {
    local label="$1"
    local path="$2"
    if [[ -e "${path}" ]]; then
        printf 'ok      %-12s %s\n' "${label}" "${path}"
    else
        printf 'MISSING %-12s %s\n' "${label}" "${path}"
        status=1
    fi
}

check "raw pdfs" "${REPO_ROOT}/data/raw/pdfs"
check "parsed" "${REPO_ROOT}/data/parsed"
check "assets" "${REPO_ROOT}/assets/queries_30.json"

if [[ -d "${REPO_ROOT}/data/parsed" ]]; then
    doc_count="$(find "${REPO_ROOT}/data/parsed" -name '*_content_list.json' | wc -l | tr -d ' ')"
    printf 'parsed content lists: %s\n' "${doc_count}"
    if [[ "${doc_count}" -eq 0 ]]; then
        printf 'no content lists found; check the MinerU output layout\n' >&2
        status=1
    fi
fi

if [[ "${status}" -ne 0 ]]; then
    printf '\nPlace the missing inputs under data/, then run make normalize.\n' >&2
fi

exit "${status}"
