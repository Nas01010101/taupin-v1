# Taupin, research version: paper outline

The farmer version is the web app (`web/`). This file is the outline of a paper on the same code:
the same NASA rules (`web/js/power.js`, `src/taupin/soil.py`), the same field ranking
(`risk/`), the same photo model (`model/`, `train/`) and the same 3D field (`src/taupin/layers.py`).
Numbers under "Current results" are copied from `risk/model/metrics.json` and `model/metrics.json`.
Everything under "Planned benchmarks" is a plan; no result is claimed.

Working title: *Soil reanalysis for wireworm scouting dates and field ranking, with an abstaining
soil-animal classifier that routes unclear photos to a plant diagnostic lab.*

## 1. Question

Since 1 August 2025, insecticide-coated seed (class 3A) in Quebec needs an agronomist's
prescription (Code de gestion des pesticides, D. 470-2025). The evidence for one field is a
bait-trap count, and most fields stay under the threshold (Labrie et al. 2020, PLoS ONE 15(2):
e0229136: 5 of 68 corn fields at or above 1 wireworm per trap). Three questions:

1. Can a global soil reanalysis (NASA POWER, MERRA-2) date the bait-trap window and rank fields for
   scouting, for any coordinates, without field sensors?
2. Can a small open image model sort soil animals from a farmer's photo and abstain when it is not
   sure, at a known accuracy on the photos it answers?
3. Does routing the abstained photos to the provincial lab (MAPAQ, Laboratoire d'expertise et de
   diagnostic en phytoprotection) keep the error on answered photos low enough for field use?

## 2. Contribution

- Scouting date and field ranking from NASA soil reanalysis: `TSOIL1` (0 to 10 cm) gives the week
  the soil holds 12 °C; spring `GWETROOT` and winter minimum `TSOIL1` are two of four inputs of a
  ranking fitted on public Quebec bait-trap fields. The same code runs in the browser for any
  latitude and longitude (`web/js/power.js`), and matches the baked values for the demo site
  (`web/test/power.test.mjs`).
- An abstaining soil-animal classifier: DINOv2-S fine-tuned on 8 classes, temperature-scaled, with
  a threshold fixed on validation; it runs in the browser (ONNX, onnxruntime-web).
- Field-to-lab routing: below the threshold the app answers "unclear" and shows the lab's
  submission steps; the photo is never uploaded by the app. Finds can be logged with a position on
  the device and exported (CSV, GeoJSON) for the agronomist (`web/js/finds.js`).
- Open code, model and data list (`DATA_SOURCES.md`, `data/attribution.csv`).

## 3. Data

| Data | Use | Licence |
|---|---|---|
| NASA POWER daily point API (MERRA-2): `TSOIL1`, `GWETROOT`, 1994-12 to present | trap date, ranking inputs | NASA open data |
| Labrie et al. 2020, Figures 1 and 3, read by `risk/digitize.py`: 82 fields, 2012 to 2016, 7 regions, 15 POWER cells | ranking labels (at or above 1 per trap) and field covariates | CC BY 4.0 |
| iNaturalist, GBIF, Wikimedia Commons images, per-image credit in `data/attribution.csv` | classifier train, validation, test; outside-source set | CC0, CC BY or public domain |
| NRCan HRDEM lidar, NASA HLS v2.0, Landsat 8/9 C2 L2, IRDA soil map | 3D field and scouting zones of the demo square | see `DATA_SOURCES.md` |

Classifier split sizes (`model/metrics.json` `counts_per_split`): train 3,852, validation 976,
test 756, outside sources 491 (GBIF 334, Wikimedia Commons 157, after a one-rater audit that
removed 157 of 648; `data/ood_audit.csv`).

## 4. Methods

- Trap date: end of the first 7-day window after 1 March with mean `TSOIL1` at or above 12 °C
  (`src/taupin/soil.py`, mirrored in `web/js/power.js` `crossing`).
- Field ranking: L2 logistic regression on light soil, years in forage, spring root-zone wetness
  and winter minimum soil temperature (`risk/fit.py`). Validation: leave one field out, one year
  out, one region out, one POWER cell out; bootstrap 95 % CI; permutation test. Output reported as
  a tercile rank, not a probability.
- Classifier: `vit_small_patch14_dinov2.lvd142m` fine-tuned (`train/train.py`), temperature
  scaling on validation, abstain threshold at the 98 % validation accuracy target (0.892), export
  to int8 ONNX; browser preprocessing checked against Python on golden inputs
  (`web/test/classify.test.mjs`, `tests/`).
- Metrics: accuracy, macro-F1, coverage (share answered) and accuracy on answered photos.

## 5. Current results

Field ranking (`risk/model/metrics.json`, model `compact`):

| Metric | Value |
|---|---|
| Fields, positives | 82, 11 |
| AUC, leave one field out | 0.80 (95 % CI 0.632 to 0.927) |
| AUC, leave one year out | 0.684 |
| AUC, leave one region out | 0.647 |
| AUC, leave one POWER cell out | 0.769 |
| Brier score, base rate | 0.1096, 0.1162 |
| Comparison: NASA features only, leave one field out | 0.75 |
| Comparison: field covariates only, leave one field out | 0.67 |
| Comparison: RAP risk-factor count, not fitted | 0.569 |

Photo model (`model/metrics.json`, version `v2-dinov2s`, threshold 0.892):

| Split | n | Accuracy | Macro-F1 | Coverage | Accuracy when answered |
|---|---|---|---|---|---|
| Test (sealed) | 756 | 0.9246 | 0.9309 | 0.8492 | 0.9751 |
| Outside sources (OOD) | 491 | 0.9267 | 0.9257 | 0.8534 | 0.9737 |

## 6. Limitations

- Ranking: 82 fields and 11 positives; the four features were chosen after the first
  cross-validation, so 0.80 is optimistic; the year-out score (0.684) is the safer figure. The
  Brier score barely beats the base rate. Labels are read from published bar charts.
- POWER is a grid of about 50 km; weather features may partly stand for year and region.
- Photo model: no test photos taken in Quebec fields; the outside set was audited by one rater;
  92 of the 157 audited-out images were still answered (`model/MODEL_CARD.md`); the threshold was
  chosen after two targets were scored on test.
- Lab routing has not been measured with the lab: no turnaround or agreement data.
- The 3D field is one park square used as a stand-in; no trapping was done there.

## 7. Planned benchmark experiments (no results claimed)

| Experiment | Data | Protocol | What to check first |
|---|---|---|---|
| E1. Taupin model on a field-image pest set | CerealPestAID (Hugging Face `sheneman/CerealPestAID-dataset`; code at https://github.com/sheneman/CerealPestAID) | fine-tune and evaluate on their train/val/test split; report accuracy, macro-F1, coverage at a validation-fixed threshold | to check on the dataset card: licence (the GitHub repo and model card say MIT; dataset card licence not read), total image count (task brief says 47,136, not verified), 26 classes (verified by search), "Clickbeetles / wireworms" image count (task brief says 2,055, not verified). Their reported test accuracy on 2,381 images, by search result only: EfficientNet-B6 92.94 %, MobileNetV3-Large 90.09 %, InceptionV3 79.00 % |
| E2. Standard IP102 split | IP102 | standard train/val/test split, top-1 accuracy | reference: CT-PestNet 77.32 % (PLoS ONE 21(8), 2026, doi 10.1371/journal.pone.0356061; number seen in the abstract via search, split not confirmed). Treat 90 % and higher claims as non-standard protocols until their tables are read |
| E3. Backbone swap | same splits as `model/metrics.json` | DINOv2-S (current) against BioCLIP 2 (MIT, arXiv 2505.23883), BioCLIP 2.5, DINOv3 (Meta DINOv3 License, check terms before release) | BioCLIP 2.5 training-set size unresolved (233M images per the Imageomics models page; to check) |
| E4. More data for the rare classes | TreeOfLife-200M (about 214M images, 952,257 taxa; licence per image, to check), BIOSCAN-5M (licence to check; CC BY 3.0 not confirmed), iNaturalist and GBIF Elateridae and *Diabrotica* | add wireworm and click beetle images, keep the sealed test untouched, report the same table | per-image licences; no overlap with the sealed test |
| E5. Abstention under shift | outside-source set, Quebec field photos to be collected | coverage and answered accuracy at the fixed threshold; share of non-animal photos answered | a "not a soil animal" class or check |
| E6. Ranking with more fields | VFF QC data if shared, or new bait-trap counts | same validation design, pre-registered features | access to the data |

## 8. Candidate venues (dates and deadlines from official pages unless marked)

Searched 2026-11-15. Most 2027 pages were not found yet.

| Venue | Dates | City | Deadline | Source |
|---|---|---|---|---|
| Canadian AI 2027 | not found | not found | not found | 2026 edition: Burnaby/Vancouver, 25 to 29 May 2026, with CRV (https://www.caiac.ca/en/conferences/canadianai-2026/home) |
| CRV 2027 | not found | not found | not found | 2026: Vancouver, 25 to 28 May 2026, paper deadline 13 Feb 2026 (https://www.cipprs.org) |
| Entomological Society of Canada 2027 | not found | not found | not found | 2026 joint with Manitoba, Winnipeg, 4 to 7 Oct 2026; the joint meeting with the Société d'entomologie du Québec is ESA/ESC/SEQ, Montréal, 22 to 25 Oct 2028 (https://esc-sec.ca/annual-meetings/ , https://entsoc.org/am/fm/index) |
| CSBE/SCGAB 2027 | not found | not found | not found | 2026: Saskatoon, 19 to 22 July 2026 (https://csbe-scgab.ca/saskatoon2026-venue-and-hosts) |
| WACV 2027 (applications track) | 4 to 8 Jan 2027 (aggregator, to check) | Orlando, FL (aggregator, to check) | round 1 paper deadline 26 June 2026, passed; round 2 not confirmed; no separate applications-track deadline found | https://wacv.thecvf.com/Conferences/2027/AuthorGuides |
| CVPR 2027 | main conference 22 to 25 June 2027; workshops 20 to 21 June 2027 | Seattle | main papers 16 Nov 2026 23:59 AoE (registration closed 10 Nov); workshop proposals closed 4 Nov 2026 | https://cvpr.thecvf.com/Conferences/2027/Dates , https://cvpr.thecvf.com/Conferences/2027/CallForPapers |
| CVPR 2027 workshops: CV4Animals, Agriculture-Vision, FGVC | not announced | Seattle | not found | check the CVPR 2027 workshop list in early 2027 |

The venue rows were read from search results; the official pages could not all be opened from this
session. Check each one before planning a submission.
