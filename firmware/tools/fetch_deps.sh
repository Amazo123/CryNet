#!/usr/bin/env bash
# Fetch the vendored firmware dependencies at their pinned revisions.
#
# The CryNet firmware builds against exactly these commits; they are not
# tracked in this repository so the history stays readable.
#
#   bash firmware/tools/fetch_deps.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/../third_party"

TFLM_REPO="https://github.com/espressif/esp-tflite-micro.git"
TFLM_REV="dd4085950a119d9e33a6de1d7be1fc7fe29e0cfc"

NN_REPO="https://github.com/espressif/esp-nn.git"
NN_REV="744d48deae6aa4a4d7b93b6a80f548d5298813a4"

clone_at() {
    local repo="$1" rev="$2" dir="$3"
    if [ -d "${dir}/.git" ]; then
        echo "==> ${dir} already present"
    else
        echo "==> cloning ${repo} -> ${dir}"
        git clone --filter=blob:none "${repo}" "${dir}"
    fi
    echo "==> checking out ${rev}"
    git -C "${dir}" fetch --depth 1 origin "${rev}" || true
    git -C "${dir}" checkout "${rev}"
}

mkdir -p "${DEST}"
clone_at "${TFLM_REPO}" "${TFLM_REV}" "${DEST}/esp-tflite-micro"
clone_at "${NN_REPO}" "${NN_REV}" "${DEST}/esp-nn"

echo
echo "Dependencies ready:"
echo "  esp-tflite-micro  $(git -C "${DEST}/esp-tflite-micro" rev-parse HEAD)"
echo "  esp-nn            $(git -C "${DEST}/esp-nn" rev-parse HEAD)"
