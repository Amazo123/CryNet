#!/usr/bin/env bash
# Deploy a model that has passed the gate.
#
#   bash research/loudspeech/deploy_model.sh [candidate_out_dir]
#
# Copies the artifacts into research/out (the reference copy), into the
# firmware's crynet_model component, and then runs the drift check that
# makes sure the firmware and the reference agree byte for byte.
#
# It does NOT build or flash: that is the next step, and it is a separate
# decision.
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
PY="/c/Users/HP/AppData/Local/Programs/Python/Python311/python.exe"
SRC="${1:-research/_out}"
FW="firmware/hub_infer/components/crynet_model/include"

if [ ! -f "$SRC/crynet_int8.tflite" ]; then
  echo "no model in $SRC" >&2
  exit 1
fi

echo "=== gate report ==="
cat research/loudspeech/gate/gate.json 2>/dev/null || echo "(no gate report — run gate_model.py first)"

echo
echo "=== copying artifacts ==="
for f in crynet_int8.tflite crynet_float.tflite crynet.keras model_data.h \
         crynet_tables.h dsp_crynet.c dsp_crynet.h crynet_infer_example.c \
         deploy_config.json metrics.json c_parity.json; do
  if [ -f "$SRC/$f" ]; then
    cp -f "$SRC/$f" "research/out/$f"
    echo "  research/out/$f"
  fi
done

# the firmware keeps the model, the calibrated tables and the contract
cp -f "$SRC/model_data.h"    "$FW/model_data.h"
cp -f "$SRC/crynet_tables.h" "$FW/crynet_tables.h"
cp -f "$SRC/deploy_config.json" "$FW/deploy_config.json"
echo "  $FW/{model_data.h,crynet_tables.h,deploy_config.json}"

echo
echo "=== drift check ==="
$PY firmware/tools/check_artifact_drift.py
echo
echo "=== the deployed model's numbers ==="
$PY -c "
import json
d = json.load(open('research/out/deploy_config.json'))
print('  sha256   ', d['model_sha256'])
print('  bytes    ', d['model_bytes'])
print('  threshold', d.get('threshold'))
m = json.load(open('research/out/metrics.json'))
print('  selected ', m['selected'], '| val AUC', round(m['variants'][m['selected']]['val_auc'], 4))
"
