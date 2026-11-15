#!/usr/bin/env bash
# Runs on the RTX box from ~/scratch/taupin/train: v2 candidates, train + val only (no test, no OOD).
# effb0 seeds 1 and 2 give the seed spread of the v1 recipe; DINOv2-S is the v2 candidate.
set -euo pipefail
PY=../.venv/bin/python
D=../data
A=../meta/attribution.csv
$PY train.py --data-root $D --attr $A --out ../runs/v2_dinov2s --arch vit_small_patch14_dinov2.lvd142m \
    --epochs 15 --bs 48 --lr 2e-4 --wd 0.05 --layer-decay 0.75
for s in 1 2; do
    $PY train.py --data-root $D --attr $A --out ../runs/v1_seed$s --seed $s
done
$PY train.py --data-root $D --attr $A --out ../runs/v2_dinov2s_seed1 --arch vit_small_patch14_dinov2.lvd142m \
    --epochs 15 --bs 48 --lr 2e-4 --wd 0.05 --layer-decay 0.75 --seed 1
echo DONE
