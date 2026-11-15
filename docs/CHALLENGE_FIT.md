# Challenge fit

NASA Space Apps 2026, challenge "Field Shift: Adapting Farms with NASA Data".
Written 2026-11-15 on branch `claude/two-versions`.

## What was verified and what was not

| Item | State | Source |
|---|---|---|
| The challenge page exists | verified by search result title only | https://www.spaceappschallenge.org/2026/challenges/field-shift-adapting-farms-with-nasa-data/ |
| Challenge text (objectives, data list) | **to check**: the page could not be opened from this session (the host is outside the session's allowed network) | open the page above and paste the objectives into the table below |
| Objectives as summarised below | secondary source, not the official text | Sonoma State Space Apps 2026 page, https://edeon.sonoma.edu/nasaspaceapps-26/ |
| The five judging criteria: Impact, Creativity, Validity, Relevance, Presentation | verified by search results of the official guides; exact 2026 wording **to check** | https://www.spaceappschallenge.org/resources/judging-awards-guide , https://www.spaceappschallenge.org/resources/project-submission-guide/ |
| Official list of NASA data for this challenge | not found | |

The secondary summary of the challenge: a decision-support tool that pairs NASA Earth observations
with local soil information, crop traits and farmer priorities, so farmers can test crop rotation
strategies for soil health under changing conditions.

## Objectives

| Objective (secondary summary) | Where Taupin meets it | What is weak |
|---|---|---|
| Use NASA Earth observations | NASA POWER `TSOIL1` sets the trap week (`web/js/power.js`, `src/taupin/soil.py`); `GWETROOT` and winter `TSOIL1` are two of the four ranking inputs (`risk/fit.py`, `web/js/fieldrisk.js`); NASA HLS NDVI is a layer of the 3D field (`src/taupin/layers.py`, `web/data/layers/ndvi.bin`); NASA GPM IMERG daily rain sets the rotation water and heavy-rain columns for any coordinates (`web/js/power.js` `weatherURL`, `web/js/soilwater.js`); NASA SMAP L4 root-zone soil moisture checks the POWER wetness input, anomaly r = 0.78 over 126 months (`src/taupin/smap.py`, `web/data/smap.json`) | HLS and Landsat are baked for one square; SMAP is shown for the demo field only |
| Pair them with local soil information | IRDA soil map and CanSIS texture under the 3D field (`web/data/layers/soil.bin`); the "sand or sandy loam" ranking input | no soil map for a field outside the demo square: the farmer ticks a box |
| Crop traits and farmer priorities | FAO-56 crop coefficients and stage lengths, OMAFRA USLE crop and tillage factors, CRAAQ and MAPAQ nitrogen rates, Lal 2005 residue ratios, one source per value (`web/data/crops.json`); pest rules with a source each (`src/taupin/engine.py`, `web/data/risk.json`); the farmer ticks which of five priorities count (pests, dry-year water, soil loss, nitrogen, residue), picks the tillage and marks the current rotation (`web/js/swui.js`) | buckwheat has no FAO-56 coefficient or Quebec nitrogen rate, so its years show ?; priorities have equal weight; no yield or price; pest levels do not change with the farmer's own field |
| Test rotation strategies | four rotations including the current one (corn and soybean by default), 2026 to 2030, ranked on the chosen priorities; each card gives why it is there, the evidence, gains and losses against the current rotation, the information gaps and the risks (`web/data/rotations.json`, `web/js/swui.js` `cardsHTML`) | no yield, cost or corn-after-corn yield penalty; on equal weights corn every year ranks first because it wins water, cover and residue; fixed start (sod) because the demo square is a park |
| Soil health | USLE cover factor per crop and tillage, heavy-rain days on bare soil, crop residue returned as the organic matter input, nitrogen to buy (`web/js/soilwater.js`) | no soil organic matter balance; USLE uses C only, not the field's K and LS; no cover crops; stored soil water at sowing not counted |
| Changing conditions | trap date for each year since 1995 and its trend per decade (`web/js/power.js` `liveSoil`, `ui.trapHTML`) | the trend is shown in a details box; no climate projection |
| Usable for a farmer | six-step task flow on the first screen (`web/index.html` `nav.flow`); offline PWA (`web/sw.js`); count sheet and agronomist record (`web/js/scout.js`) | no French interface; no farmer or agronomist has tried it |

## Judging criteria

| Criterion | Where Taupin meets it | What is weak |
|---|---|---|
| Impact | the 2025 prescription rule (D. 470-2025) and the count that shows a field is under the threshold (Labrie et al. 2020: 5 of 68 corn fields at or above 1 per trap); trap points, count sheet, record (`web/js/scout.js`) | no field trial; impact on seed purchases is not measured |
| Creativity | trap week from soil reanalysis; ranking from root-zone wetness and winter soil temperature; abstaining photo model that routes unclear photos to the MAPAQ lab (`web/js/classify.js`, `web/js/ui.js` `labHTML`); finds logged on the device and fed back as the default field position (`web/js/finds.js`) | VFF QC already ranks fields; Taupin's ranking is a complement |
| Validity | every rule carries a source (`web/data/risk.json`); held-out scores and limits in `risk/model/metrics.json`, `model/metrics.json`, `model/MODEL_CARD.md`; browser results equal the baked files for the demo site (`web/test/power.test.mjs`) | ranking on 82 fields, 11 positives, features chosen after the first cross-validation (AUC 0.80 optimistic, year-out 0.684); no photos taken in Quebec fields |
| Relevance (NASA data as a core component) | the trap week and two of four ranking inputs come from NASA POWER for any coordinates; a NASA-only ranking scores 0.75 leave-one-field-out against 0.67 for field covariates only (`risk/model/metrics.json`) | HLS and Landsat layers only for the demo square |
| Presentation | numbered six-step flow, model numbers moved to "Details" at the bottom; `?demo=1` 12 s recorded demo (`web/js/demo.js`); README with GIF; deck | the deck link must be checked in a private window; deck not regenerated for the new first screen |

## Changes made on this branch for the weak points

- Presentation: the first screen is now a numbered task flow (field, trap week, where to trap,
  counts, photo, what to plant). Headings carry the step numbers. The photo-model table sits under
  "Details: what the numbers rest on". `?demo=1` keeps its layout (`web/app.css`, `.demo` rules).
- Impact and relevance: a photo result can be saved with its position (device GPS or the photo's
  EXIF GPS, both on a tap). The latest find becomes the default position for the NASA POWER lookup
  of step 1, so the farmer's own field gets NASA dates and a rank without typing coordinates
  (`web/js/finds.js`, `web/js/app.js`).
- Validity: finds go into the agronomist record and export as CSV and GeoJSON; nothing leaves the
  device (`web/js/scout.js` `findLine`, `web/test/finds.test.mjs`).
- Plain words: "model card", "model ready" and "classes" are gone from the main flow.

## Still open

- Read the official challenge page and the 2026 judging wording and update the two tables above.
- French interface.
- Lidar, HLS, Landsat and the soil map per field, so the 3D field and trap points follow step 1.
- A field trial with a farmer or an agronomist.
