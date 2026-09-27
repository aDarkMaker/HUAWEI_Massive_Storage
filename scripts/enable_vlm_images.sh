#!/usr/bin/env bash
# Make the reference store's relative image references resolvable.
#
# The reference index stores img_path as
#   mineru-parsed/<doc>/auto/images/<hash>.jpg
# a relative path whose base directory does not exist. RAGAnything.aquery_vlm_enhanced
# validates each reference with validate_image_file, which is a Path(...).exists()
# call resolved against the query server's working directory. With all 1,112
# references failing, `images_found` stays 0 and the method falls back to a plain
# text query, silently disabling multimodal retrieval while still logging at INFO.
#
# This creates the single directory-level link that repairs the base path, then
# verifies the mapping against the working directory the query server actually uses.
# The link is working-directory dependent, so verification is not optional.
#
# Usage:
#   bash scripts/enable_vlm_images.sh            # create and verify
#   bash scripts/enable_vlm_images.sh --check    # verify only, change nothing
#   bash scripts/enable_vlm_images.sh --remove   # undo
#
# The link lives inside the vendored tree and shows up as untracked. It must never
# be committed: an absolute symlink is meaningless on another machine.

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

LINK="${RAG_DIR}/mineru-parsed"
TARGET="${REPO_ROOT}/data/parsed"
SAMPLE_DOC="commerce_manufacturing_0501317"

usage() {
    sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

verify() {
    local probe="${LINK}/${SAMPLE_DOC}/auto/images"
    local count
    count="$(find "${probe}" -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${count}" -gt 0 ]]; then
        printf 'ok      %s image files visible through %s\n' "${count}" "${LINK}"
        return 0
    fi
    printf 'FAILED  no images visible through %s\n' "${LINK}" >&2
    printf '        the query server must be started from %s for this to work\n' \
        "${RAG_DIR}" >&2
    return 1
}

case "${1:-}" in
    -h|--help) usage 0 ;;
esac

require_dir "${TARGET}"

if [[ "${1:-}" == "--remove" ]]; then
    if [[ -L "${LINK}" ]]; then
        rm "${LINK}"
        printf 'removed %s\n' "${LINK}"
    else
        printf 'not a symlink, nothing to remove: %s\n' "${LINK}"
    fi
    exit 0
fi

if [[ "${1:-}" == "--check" ]]; then
    verify
    exit $?
fi

if [[ -e "${LINK}" && ! -L "${LINK}" ]]; then
    if [[ -n "$(ls -A "${LINK}" 2>/dev/null)" ]]; then
        printf 'refusing to replace non-empty directory: %s\n' "${LINK}" >&2
        exit 1
    fi
    rmdir "${LINK}"
fi

[[ -L "${LINK}" ]] || ln -s "${TARGET}" "${LINK}"
printf 'linked  %s -> %s\n' "${LINK}" "${TARGET}"

verify || exit 1

cat <<EOF

Restart the query server from ${RAG_DIR}, then confirm the fallback is gone:

  grep -c 'No valid images found' runs/<ts>_eval/bench.log
  grep -c 'Image validation failed' runs/<ts>_eval/bench.log

Both counts should be 0. Undo this with:

  bash scripts/enable_vlm_images.sh --remove
EOF
