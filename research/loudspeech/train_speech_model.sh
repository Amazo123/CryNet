#!/usr/bin/env bash
# The retrain: the same notebook, with the loud-speech corpus added.
#
#   bash research/loudspeech/train_speech_model.sh [kinds]
#
# The notebook is run locally, in full mode, with the speech corpus built
# first.  The artifacts land in research/_out (scratch); they are NOT
# deployed by this script — deployment is a separate, deliberate step.
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
PY="/c/Users/HP/AppData/Local/Programs/Python/Python311/python.exe"
KINDS="${1:-conv_cnn}"
LOG="research/loudspeech/train_full.log"

if [ ! -f research/_cache/speech__fsd50k_speech.zip ]; then
  echo "=== building the speech corpus ==="
  $PY -I research/loudspeech/build_speech_zip.py --limit 6000
fi

echo "=== training: kinds=$KINDS ==="
export CRYNET_FAST=0
export CRYNET_KINDS="$KINDS"
export CRYNET_EPOCHS=35
export CRYNET_MINING_ROUNDS=1
export CRYNET_CACHE="$ROOT/research/_cache"
export CRYNET_WORK="$ROOT/research/_work"
export CRYNET_OUT="$ROOT/research/_out"

mkdir -p "$CRYNET_WORK" "$CRYNET_OUT"
cd research
$PY run_notebook_local.py 2>&1 | tee "../$LOG"
echo "=== done; artifacts in $CRYNET_OUT ==="
