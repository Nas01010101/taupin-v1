# Taupin: build spec

Taupin (French for click beetle, the adult of the wireworm) is a soil-insect scouting tool for
Quebec field crops, submitted to NASA Space Apps 2026 ("Field Shift: Adapting Farms with NASA
Data"). Deadline: Sunday 2026-11-15 23:59 local. Repo: `~/Projects/taupin`, MIT.

## What the user does

1. Opens the app (static web page; also runs offline and installs as an app).
2. Sees a 3D model of the field: Parc-nature du Bois-de-Liesse, Secteur des Champs
   (a 600 m square centred on 45.5013 N, 73.7651 W), a protected meadow used as a stand-in for St. Lawrence Lowland
   farmland returning to crops. Nothing is dug or collected there.
3. Drops a photo of an insect found in the soil. A model running in the browser names it
   (or says "unclear: send to the lab") and the photo is pinned on the field.
4. Reads what that means: bait-trap window from NASA soil temperature, and wireworm /
   corn rootworm risk for three 5-year rotations, each line naming its source.

## Sources to port (same owner, MIT)

- `~/Projects/wireworm-risk-twin`: `core/risk_engine.py` + tests (cited rules, 2025-08-01
  prescription rule), `scripts/make_figures.py` (trap-window date from POWER `TSOIL1`),
  `assets/insects/` + `ATTRIBUTION.md` (6 Commons photos), `data/power_daily.json`.
- `~/Projects/field-shift`: `web/twin/scene.js` (Three.js terrain scene), `web/twin/photo.js`
  (photo pins), `src/fieldshift/twin.py` (`bake`), and the fetched park data in `data/park/`
  (`dem.tif` NASADEM, `rgb.tif` + `ndvi.tif` from HLS, `power_daily.json`, `site.json`).
  Superseded on 2026-11-14: the field layers now come from `src/taupin/layers.py` (HRDEM lidar, HLS,
  Landsat, IRDA soil map); see `DATA_SOURCES.md`.
  The park is not corn, so place the parcel at the site centre instead of `pick_parcel`.

## Ownership (two agents work at once; stay in your lane)

| Path | Owner |
|---|---|
| `train/`, `model/`, `data/` | ML agent |
| everything else (`src/`, `web/`, `tests/`, `docs/`, `README.md`, `.github/`, git) | eng agent |

Only the eng agent runs git. The ML agent writes files and never runs `git add/commit`.

## Model contract (ML agent produces, app consumes)

- `model/taupin.onnx`: input `image` float32 `[1,3,S,S]` (RGB, resized so the short side is S
  then centre-cropped, scaled to 0..1, normalised with `mean`/`std`), output `logits` `[1,N]`.
  Opset ≤ 17, runs in onnxruntime-web (wasm) and onnxruntime (CPU). Target ≤ 25 MB.
- `model/labels.json`:
  `{"classes":[{"id":"wireworm","name":"Wireworm (click beetle larva)","pest":true}, ...],
    "input_size":224,"mean":[..],"std":[..],"temperature":1.0,"abstain_below":0.0,
    "version":"..."}`.
  The app shows `softmax(logits/temperature)`; top-1 below `abstain_below` → "unclear".
- `model/metrics.json`: per-class precision/recall/F1, macro-F1, accuracy, coverage and
  accuracy at the abstain threshold, confusion matrix, counts per split, on (a) the sealed
  in-distribution test split and (b) an out-of-distribution set from a different source.
  Include the zero-shot CLIP baseline on the same splits.
- `model/MODEL_CARD.md`: data, licences, splits, numbers, known failure cases.
- `data/attribution.csv`: one row per image (url, author, licence, source id, class, split).
  Images themselves are not committed; `train/` holds the script that downloads them.
- `data/samples/<class_id>/*.jpg`: 3 CC0/CC-BY photos per class (≤ 200 KB each) for the
  website gallery and the demo, each with a row in `attribution.csv`.

Classes: wireworm larva, click beetle adult, corn rootworm adult, white grub, ground beetle
(beneficial), plus look-alikes that farmers confuse with wireworms (millipede, earthworm) and
a catch-all "other". The ML agent fixes the final list from what open-licence data supports
and writes it to `labels.json`; the app reads the list, it is not hard-coded.

## Constraints

- The Mac has 16 GB and is swapping. No model training, large builds or long-running servers
  on it. Training goes to the RTX box or Colab (`~/.claude/docs/resources.md`,
  `~/.claude/docs/colab.md`; `res pick` then `res claim`, `res release` after).
- Ports 8765 and 8770 are in use by other work; use 8780 or above and stop what you start.
- Nothing leaves the machine: no `git push`, no `gh repo create`, no uploads of project or
  personal details. Outward steps are reported as exact commands for the owner to approve.
- Requests to outside services carry no name, email or location.
- Only open-licence inputs (CC0, CC-BY, public domain, MIT/Apache/BSD code and weights).
  CC-BY-NC material is not used anywhere.
- Text in README, docs, UI and commits states what a thing is and does; no quality
  adjectives, no "from scratch"/"end-to-end". Numbers come from `model/metrics.json` or a
  cited source, never invented.
- Files under 500 lines, tests for new code.
