#!/usr/bin/env bash
# Runs on the RTX box from ~/scratch/taupin/train after the v2 choice was made on validation.
#   bash run_v2_eval.sh <ckpt> <version> [--quantize]
# CLIP ViT-B-32 is re-run on val and OOD only (its test logits from v1 stay valid: same rows,
# same weights). ViT-L-14 and BioCLIP read test once each, logged.
set -euo pipefail
PY=../.venv/bin/python
D=../data
A=../meta/attribution.csv
CKPT=$1; VER=$2; shift 2
$PY clip_baseline.py --data-root $D --attr $A --out ../runs/clip_b32 --model ViT-B-32 --pretrained laion2b_s34b_b79k
[ -f ../runs/clip_l14/test_logits.npy ] && F= || F=--final
$PY clip_baseline.py --data-root $D --attr $A --out ../runs/clip_l14 --model ViT-L-14 --pretrained laion2b_s32b_b82k $F
[ -f ../runs/bioclip/test_logits.npy ] && F= || F=--final
$PY clip_baseline.py --data-root $D --attr $A --out ../runs/bioclip --model hf-hub:imageomics/bioclip --pretrained "" $F
$PY final_eval.py --ckpt $CKPT --data-root $D --attr $A --clip ../runs/clip_b32 ../runs/clip_l14 ../runs/bioclip \
    --model-dir ../model_$VER --version $VER --final "$@"
echo DONE
