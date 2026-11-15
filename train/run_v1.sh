#!/usr/bin/env bash
# Runs on the RTX box from ~/scratch/taupin/train: train v1, CLIP baselines, final evaluation.
set -euo pipefail
PY=../.venv/bin/python
D=../data
A=../meta/attribution.csv
$PY train.py --data-root $D --attr $A --out ../runs/v1 --arch efficientnet_b0.ra_in1k --epochs 15
$PY clip_baseline.py --data-root $D --attr $A --out ../runs/clip_b32 --model ViT-B-32 --pretrained laion2b_s34b_b79k --final
$PY final_eval.py --ckpt ../runs/v1/best.pt --data-root $D --attr $A --clip ../runs/clip_b32 \
    --model-dir ../model_v1 --version v1-effb0 --final
echo DONE
