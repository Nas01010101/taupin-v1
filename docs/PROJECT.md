# Taupin: project file

NASA Space Apps 2026, challenge "Field Shift: Adapting Farms with NASA Data".
Submission closes 2026-11-15 23:59 local time. Last updated 2026-11-15.

## Pitch

In Quebec, farmers now need an agronomist's prescription for insecticide-coated seeds, even though
over 90 % of fields don't actually need them.

Our planner compares five-year crop rotations to break pest cycles naturally. Using NASA satellite
weather and soil data, we generate a 3D model of the field showing when and where to scout.

Farmers snap a field photo, our open-source ML model sorts the image and updates the 3D map, or
sends uncertain samples to Quebec's lab.

## Who uses it and for what

A grain farmer and their agronomist, between snowmelt and seeding. The prescription rule
(Code de gestion des pesticides, D. 470-2025, in force 1 August 2025) asks the agronomist to justify
coated seed field by field. The justification is a bait-trap count. Taupin covers the work around
that count:

| Step | What the farmer gets | Data behind it |
|---|---|---|
| Plan | wireworm and corn rootworm level per year for three rotations, 2026 to 2030 | rule engine with a source per rule (`src/taupin/engine.py`) |
| Scout: when | the week to set bait traps (soil at 12 °C in the top 10 cm) | NASA POWER `TSOIL1`, 1995 to 2025 |
| Scout: which fields | the field's rank (low, middle or high third) among 82 Quebec fields | field risk model: 2 field-form answers + 2 NASA POWER values |
| Scout: where | ten trap points spread over four scouting zones, as GPX, CSV and GeoJSON | lidar relief and wetness index, NASA HLS NDVI, Landsat surface temperature, soil map |
| Count | a sheet for three lifts per trap; each lift compared on its own with the threshold of the dominant species | RAP method, Agri-Réseau doc. 115269 (`web/js/scout.js`) |
| Identify | the animal in a photo, or "unclear: send to the lab" | photo classifier with an abstain threshold |
| Document | a text record with the trap date, points, counts, ranking and photos | all of the above, with sources |

Taupin never decides the prescription. The agronomist signs.

## Prior work and where Taupin sits

VFF QC (CÉROM and MAPAQ, 2017, https://cerom.qc.ca/vffqc/) already predicts a wireworm risk level
per field. It is a boosted regression tree fitted on close to 800 Quebec fields scouted since 2011,
with region, organic matter, soil texture, elevation, three years of previous crops, the current
crop and tillage as inputs (CÉROM final report PV-3.2-2015-002). It runs inside Info-Sols and needs
an account. Agronomists use it with the decision tree of the Ordre des agronomes du Québec.

Taupin does not replace it. What Taupin adds around it:

| VFF QC | Taupin |
|---|---|
| one risk level for the whole field | trap points spread over the field's soil, relief and vegetation zones |
| no weather or satellite input | NASA POWER soil temperature and soil wetness; satellite layers per cell |
| no calendar | the week the soil reaches the trapping temperature |
| current year | five years, three rotations side by side |
| identification by sending samples | photo model in the browser, with the lab as the fallback |
| account required, model and data not published | open code, open model, public data, runs offline |

Taupin's own risk model is fitted on 82 public fields, about a tenth of VFF QC's data. It is an
open complement, not a stronger predictor.

## What exists today

| Part | State | Evidence |
|---|---|---|
| Web app (risk table, photo classification in the browser, offline) | on `main` | `web/`, `tests/test_web.py` |
| 3D field from lidar, HLS, Landsat and the soil map, with scouting zones and trap points | on `build` | `src/taupin/layers.py`, `web/js/scene.js`, `tests/test_layers.py` |
| Count sheet, trap files (GPX, CSV, GeoJSON), agronomist record, lab route | on `build` | `web/js/scout.js`, `web/test/scout.test.mjs` |
| Rule engine for wireworm and corn rootworm | on `main` | `src/taupin/engine.py`, `tests/test_engine.py` |
| Trap date from NASA POWER soil temperature | on `main` | `src/taupin/bake.py`: mean 14 May over 1995 to 2025, 8 May in 2025 |
| Photo classifier v2 (DINOv2-S, 8 classes, ONNX, 23 MB) | on `build` (v1 on `main`) | `model/metrics.json`, `model/MODEL_CARD.md` |
| Field risk model fitted on Quebec bait-trap fields | on `build` | `risk/`, `risk/model/metrics.json`, `tests/test_risk.py` |
| Launchers for macOS, Windows and Linux | on `main` | `run.command`, `run.bat`, `run.sh` |
| Pitch deck | 7 slides, published as a web page | shared as "anyone with the link"; open it once in a private window before submission |
| Trap dates and field ranking for any coordinates | on `build` | `web/js/power.js`, `web/test/power.test.mjs` |
| Six-step farmer flow on the first screen; model numbers under "Details" | on `claude/two-versions` | `web/index.html`, `web/app.css` |
| Photo finds logged with a position on the device, pins, CSV and GeoJSON export, in the record | on `claude/two-versions` | `web/js/finds.js`, `web/test/finds.test.mjs` |
| Research outline and challenge fit | on `claude/two-versions` | `docs/RESEARCH.md`, `docs/CHALLENGE_FIT.md` |
| Four rotations scored on dry-year water, bare-soil heavy rain, USLE cover, nitrogen, residue and pests; farmer priorities; why, evidence, gaps and risks per rotation | on `soil-water` | `web/js/soilwater.js`, `web/js/swui.js`, `web/data/crops.json`, `web/data/rotations.json`, `web/test/soilwater.test.mjs` |
| GPM IMERG daily rain and SMAP L4 soil moisture | on `soil-water` | `src/taupin/weather.py`, `src/taupin/smap.py`, `tests/test_soilwater_bake.py` |

## Data

| Source | Variables | Used for |
|---|---|---|
| NASA POWER daily point API (MERRA-2, 0.5 x 0.625 degree) | `TSOIL1`, `GWETROOT`, `PRECTOTCORR`, `T2M` | trap date; four of the risk model's candidate features |
| NASA GPM IMERG via POWER (`IMERG_PRECTOT`, UTC days), POWER `T2M_MAX`, `T2M_MIN`, 2001 to 2025 | daily rain, air temperature | rotation water need, season rain, heavy-rain days on bare soil |
| NASA SMAP L4 analysed root-zone soil moisture, GIBS, 252 dates, 2015 to 2025 | m3/m3 | check of the POWER wetness input (anomaly r = 0.78, 126 months) |
| FAO-56, OMAFRA 23-005, CRAAQ and MAPAQ grids, Lal 2005, CGQ yields | crop coefficients, USLE C, nitrogen rates, residue ratios | rotation soil and water columns (`web/data/crops.json`) |
| NASA HLS v2.0 (L30 and S30), 23 clear summer scenes, 2020 to 2025 | NDVI | vegetation layer of the 3D field; one input of the scouting zones |
| Landsat 8/9 Collection 2 Level-2, 46 clear April and May scenes, 2016 to 2025 | surface temperature | spring warm and cold parts of the field |
| NRCan HRDEM lidar, 1 m, 2023 | terrain, canopy height | relief, slope, wetness index and open ground of the 3D field |
| IRDA soil map (1:20 000), AAFC CanSIS tables | soil units, texture | soil layer and soil profile of the 3D field |
| OpenStreetMap, way 542903996 (ODbL) | park outline | keeps the trap points inside the park |
| Labrie et al. 2020, PLoS ONE 15(2): e0229136, CC BY 4.0 | bait-trap counts and field covariates, 84 fields, 2012 to 2016 | labels and covariates of the risk model |
| iNaturalist, GBIF and Wikimedia Commons photos | open-licence images, credits in `data/attribution.csv` | photo classifier |

The demo field is a 600 m square in the Secteur des Champs of the Parc-nature du Bois-de-Liesse,
centred on 45.5013 N, 73.7651 W. It is a park used as a stand-in, not a crop field: the park covers
28.0 ha of the 36 ha square, and only 1.3 ha is open ground where a trap could go. The mapped
meadows are about half regrown under the 2023 lidar. `DATA_SOURCES.md` lists every layer with its
source, licence and access date.

## Models

### Photo classifier

DINOv2-S fine-tuned, classes: wireworm, click beetle, corn rootworm, white grub, ground beetle,
millipede, earthworm, other. Numbers from `model/metrics.json`:

| Split | n | Accuracy | Accuracy above the abstain threshold | Share answered | Wireworm named (argmax) |
|---|---|---|---|---|---|
| Validation | 976 | 0.946 | 0.981 | 0.900 | 58 of 61 |
| Sealed test | 756 | 0.925 | 0.975 | 0.849 | 51 of 55 |
| Outside sources, audited | 491 | 0.927 | 0.974 | 0.853 | 17 of 19 |

Below a confidence of 0.892 the app answers "unclear: send to the lab". The previous version
(EfficientNet-B0) scores 0.861 on the same test photos and 0.862 on the same outside photos.

Limits, stated as measured:

- The outside set was audited by eye by one person, after a poor wireworm result prompted a look:
  157 of 648 images were removed (`data/ood_audit.csv`). On all 648 the model scores 0.765.
- 92 of the 157 removed images still got an answer instead of "unclear". A photo that shows no
  soil animal can get a confident name.
- The 0.892 threshold (98 % validation target) was chosen after the 95 % and 98 % targets had both
  been scored on test and outside photos.
- Museum and lab specimens score 0.771 (n 48) against 0.944 for field photos (n 443).
- The browser runtime was checked in Node on 24 photos and in the app in Chromium on the same 24
  (20 named, 4 unclear, 0 wrong). Those 24 come from the test split.

### Field risk model

Question: which fields will reach 1 wireworm per bait trap?

- Labels: bar heights read from Figures 1 and 3 of Labrie et al. 2020 (`risk/digitize.py`),
  82 fields, 11 at or above 1 per trap. The reading reproduces the paper's counts: 5 soybean fields
  at or above 1 per trap, 2 corn fields at or above 3 per trap.
- Features: light soil, years in forage (field form), spring root-zone soil wetness and winter
  minimum soil temperature (NASA POWER).
- Model: L2 logistic regression, four features (`risk/fit.py`).

| Model | AUC, leave one field out | Year out | Region out | Weather cell out |
|---|---|---|---|---|
| RAP risk-factor count (not fitted) | 0.57 | | | |
| Field covariates only | 0.67 | 0.44 | 0.54 | 0.70 |
| NASA POWER only | 0.75 | 0.77 | 0.72 | 0.77 |
| Shipped: 2 field + 2 NASA features | 0.80 (95 % CI 0.63 to 0.93) | 0.68 | 0.65 | 0.77 |

Limits, stated as measured:

- The four shipped features were chosen after seeing the cross-validation of the first three sets,
  so 0.80 is optimistic.
- The Brier score (0.110) barely beats the base rate (0.116). The output is a ranking for where to
  put traps first, not a probability and not a decision.
- 82 fields, 5 years, 15 weather cells: the weather features may partly stand for year and region.
- A grass previous crop did not predict wireworms in this data (AUC 0.44), although the RAP method
  lists it as a risk factor.

## Fit with the judging criteria

The full table, with file paths and weak points, is in `docs/CHALLENGE_FIT.md`.

| Criterion | What answers it |
|---|---|
| Impact | 92.6 % of corn fields in Labrie et al. 2020 were under 1 wireworm per trap; the tool gives farmer and agronomist the count that shows it for one field |
| Creativity | adds the when and the where inside the field to the existing field-level tool (VFF QC), with open code and data |
| Validity | every rule carries a source; both models report held-out scores and their limits |
| Relevance | NASA POWER sets the trap date and supplies two of the four risk-model features; NASA-only features rank fields better than field covariates alone; NASA HLS and Landsat are two of the layers the trap points are spread over |
| Presentation | 7-slide deck with captures of the running app; public repo; runs with one command |

## Gaps being worked on

| Gap | State | Next step |
|---|---|---|
| Usefulness to a farmer: trap locations, install dates, count sheet, agronomist record | done on `build` | trap points as GPX, CSV and GeoJSON; three-lift count sheet; text record |
| 3D field drawn from soil, terrain and NASA layers instead of a schematic surface | done on `build` | 300 x 300 cells of 2 m from HRDEM, HLS, Landsat and the soil map |
| The scouting zones are classes of the layers, not a wireworm risk map | known | no public data gives wireworm counts inside a field; the app says so |
| Crop history per year (AAFC Annual Crop Inventory) is not in the app | open | the demo square is a park, so the rotation plans start from sod |
| Risk model shown in the app next to the rule trace | done on `build` | `web/data/field_risk.json`; the output is a rank, not a probability |
| Photos that are not soil animals still get an answer (92 of 157 audited-out images) | known | add a "not a soil animal" check or more such training photos; say so in the app |
| No test photos taken in Quebec fields; outside-set audit has one rater | open | field photos from trails on 15 November, labelled as staged where they are |
| "Over 90 %" | two sources, same research group | Labrie et al. 2020: 92.6 % of corn fields under 1 wireworm per trap (84 fields, 2012 to 2016). CÉROM report PV-3.2-2015-002: the threshold was exceeded in 10 % of cases in the 2011 to 2015 surveys, and in 25 % of 163 sites chosen for higher risk in 2016. Cite both in the deck |
| Deck slide 6 and its capture showed the previous photo model | done | rebuilt from `model/metrics.json`; the cover runs `web/js/scene.js` on the same layer files as the app |
| "Use my field": any coordinates, live NASA POWER call | done on `build` | `web/js/power.js` asks NASA POWER for TSOIL1 and GWETROOT at the entered coordinates and gives the trap date, the yearly dates and the field ranking; the two coordinates are the only thing sent. For the demo site the browser result equals the baked `soil.json` and `field_risk.json` (31 years of dates, 11 years of ranking inputs, 0 differences). The 3D field, the trap points and the pest levels stay the demo square; the rotation water columns use the field's own IMERG rain |
| 3D field and trap points for any field | open | needs lidar, HLS, Landsat and the soil map fetched per field; today they are baked for one square |
| Route to the Quebec lab for unclear photos | done on `build` | an unclear photo shows the lab's steps: online form first, then images by email or samples by post, first answer in 24 to 48 h (MAPAQ Laboratoire d'expertise et de diagnostic en phytoprotection, quebec.ca). The farmer sends it; the app sends nothing |
| French interface | open | the users are Quebec farmers |
| One file listing every data source with licence and access date | done | `DATA_SOURCES.md` |
| Digitized corn counts give 6 fields at or above 1 per trap; the paper reports 5 of 68 | known | one field sits on the threshold; noted in `risk/digitize.py` |
| The demo field is a park, not a farm; 1.3 ha of the square is open ground | known | shown as a scenario; no trapping or digging in the park |
| No field trial of the tool with a farmer or agronomist | known | outside the weekend's scope |

### Soil and water: what the rotation model leaves out

The brief asks for soil health and water. Step 6 now scores four rotations on five priorities. The
demo field on equal weights, fall plough, as `web/js/soilwater.js` computes them from
`web/data/weather.json` (the tests check the nitrogen totals and the rank order):

| Rotation | Dry-year water, mm | Heavy rain on bare soil, days in 5 years | USLE C | N to buy, kg/ha in 5 years | Residue, t/ha a year |
|---|---|---|---|---|---|
| Corn every year | 32 spare | 7 | 0.40 | 725 | 7.7 |
| Corn and soybean (current) | 18 short | 8.5 | 0.44 | 415 | 5.7 |
| Corn, soybean, wheat | 47 short | 9.6 | 0.43 | 400 | 5.1 |
| With buckwheat | 35 short, 1 year unknown | ? | 0.4 | ? | 5.7 |

Corn every year ranks first on equal weights. That is the model's output, and it shows what the
model leaves out:

| Gap | Effect on the ranking | Next step |
|---|---|---|
| Soil water stored at sowing is not counted | a crop sown early (wheat) looks drier than it is | FAO-56 Ch. 8 soil water balance started from SMAP or GWETROOT at sowing, with available water from the CanSIS soil tables |
| No yield penalty for corn after corn | corn every year gets full residue and no yield loss | a sourced penalty from Quebec or Ontario trials applied to yield, residue and nitrogen |
| No cover crops | wheat and soybean years keep bare soil after harvest | a cover crop option after wheat and soybean, with its USLE C and nitrogen effect |
| USLE uses C only; K and LS of the field are not used | soil loss is compared, not estimated in t/ha | A = R K LS C P for the demo square from HRDEM slope and CanSIS texture; slope class from the farmer elsewhere |
| Buckwheat has no FAO-56 coefficient, Quebec nitrogen rate or CGQ yield | its rotation ranks after the fully scored ones | find a measured coefficient and a CRAAQ rate; until then ? stays ? |
| Pest levels are the demo square's for any field | pest points do not follow the farmer's history | ask for the last two crops and feed them to `web/js/risk.js` |
| Equal weights, no yield or price | the ranking ignores income | farmer weights per priority; CGQ prices per crop |
| SMAP for the demo field only | no satellite soil moisture for another field | check whether GIBS answers browser requests; if yes, fetch the 0.4 degree box for the entered point |

## Submission checklist

- [ ] Deck at 7 slides or fewer (done), public link, no login (shared as "anyone with the link"; check it in a private window)
- [ ] Public repository with licence, README, run commands
- [ ] References list covering NASA POWER, GPM IMERG, SMAP L4, FAO-56, OMAFRA 23-005, CRAAQ and MAPAQ nitrogen grids, Lal 2005, HLS, Landsat, HRDEM, IRDA, CanSIS, OpenStreetMap, Labrie et al. 2020, GBIF, Wikimedia Commons, VFF QC, RAP and MAPAQ documents
- [ ] All text in English
- [ ] Every number in the deck and README traceable to `model/metrics.json` or `risk/model/metrics.json`
