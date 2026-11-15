# Data sources

Each layer and number shown in the app, where it comes from, under which licence, at what native
resolution, and what it feeds. NASA sources are the core. A non-NASA source is listed with the
reason it is used.

## Field risk model

| Item | Source | Licence | Native resolution | Feeds |
|---|---|---|---|---|
| Trained logistic model, `web/data/risk_model.json` (copy of `risk/model/risk_model.json`) | Fitted on 82 bait-trapped Quebec fields, 2012 to 2016, 11 at or above 1 wireworm per trap: Labrie G. et al. 2020, PLoS ONE 15(2): e0229136, doi:10.1371/journal.pone.0229136 (S1 Table, Figs 1 and 3) | CC BY 4.0 (paper and supplement) | One value per field | Field wireworm ranking (low, middle, high third of the training fields) |
| Rank cut points, training input ranges, `web/data/field_risk.json` | Computed by `src/taupin/fieldrisk.py` from the same 82 fields and the model above | as above | One value per field | Ranking classes; the note when an input is outside the training fields |

Non-NASA reason: Labrie et al. 2020 is the published set of bait-trap counts for Quebec field
crops with field coordinates, soil texture and rotation history; no NASA product counts insects.

Validation (from `risk/model/metrics.json`): AUC 0.80 leaving one field out (95 % CI 0.63 to
0.93), 0.68 leaving one year out, 0.65 leaving one region out; the RAP rule count scores 0.57
on the same fields; Brier score 0.110 against 0.116 for the base rate. The app shows the output
as a rank, never as a probability.

## NASA POWER

Daily point API, community AG, `https://power.larc.nasa.gov/api/temporal/daily/point`. MERRA-2
assimilation, 0.5 x 0.625 degree grid (about 55 x 49 km at 45 N), so a whole field and its
neighbours share one value. NASA open data, no licence restriction; cite NASA POWER.

| Parameter | What it is | Window used | Feeds |
|---|---|---|---|
| GWETROOT | Root-zone soil wetness, 0 (dry) to 1 (saturated) | Mean 1 Apr to 31 May of the scouting year | Model input `gwet_spring` (one value for the field; not spread inside the field) |
| TSOIL1 | Soil temperature, top layer (0 to 10 cm), deg C | Minimum 1 Dec to 31 Mar before the season | Model input `tsoil_winter_min_c` |
| TSOIL1 | as above | 1 Mar to 31 Jul, first 7-day run at or above 12 deg C | Bait-trap window (`src/taupin/soil.py`, `web/data/soil.json`) |
| PRECTOTCORR | Bias-corrected precipitation, mm/day | Total 1 May to 30 Sep of the previous year (`risk/fetch_power.py`) | Candidate input in the larger fitted models (`risk/model/metrics.json`); not in the model the app runs |
| T2M | Air temperature at 2 m, deg C | Mean 15 Apr to 31 May (`risk/fetch_power.py`) | Fetched with the training features; not used by any fitted model |

The park values in `web/data/field_risk.json` come from one request for 45.5056 N, 73.7639 W,
1 Dec 2015 to 31 May 2026. That point is 480 m from the centre of the demo square (45.5013 N,
73.7651 W) and in the same 0.5 x 0.625 degree cell, so the values are the same.

GWETROOT is not spread inside the field with the wetness index: the model was fitted between
fields, and no source gives how much spring wetness varies inside one field, so any spread would
be an invented number.

## NASA GPM IMERG rain and SMAP soil moisture

| Item | Source | Licence | Native resolution | Feeds |
|---|---|---|---|---|
| Daily rain, 2001 to 2025, `web/data/weather.json` (`src/taupin/weather.py`) | NASA GPM IMERG daily precipitation through the NASA POWER daily point API, parameter `IMERG_PRECTOT`, requested with `time-standard=UTC` (with the default local solar time every value is the fill value -999) | NASA open data | 0.1 degree | Rain over each crop's season, dry-year water shortfall, heavy-rain days on bare soil (`web/js/soilwater.js`) |
| Daily air temperature, 2001 to 2025, same file | NASA POWER `T2M_MAX`, `T2M_MIN` (MERRA-2) | NASA open data | 0.5 x 0.625 degree | Hargreaves reference evapotranspiration; sowing day from the 10-day mean air temperature |
| Root-zone soil moisture, 252 dates (1st and 15th of each month, April 2015 to September 2025), `web/data/smap.json` (`src/taupin/smap.py`) | NASA SMAP L4 analysed root-zone soil moisture (0 to 100 cm), GIBS WMS layer `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture`, decoded with the GIBS colour map (bins of 0.003 m3/m3); no login | NASA open data | 9 km | Check of the POWER `GWETROOT` ranking input: monthly anomalies correlate at r = 0.78 over 126 months; soil moisture chart under "Details" |

SMAP L4 masks Montreal island at the field itself, so each value is the median of the valid cells
within 0.2 degree of the field (a box of about 45 km, close to the POWER cell). For "Your field" the
browser asks POWER for `IMERG_PRECTOT`, `T2M_MAX` and `T2M_MIN` at the entered coordinates
(`web/js/power.js` `weatherURL`); SMAP is shown for the demo field only.

## Crop, soil-loss and nitrogen values

`web/data/crops.json` gives each value a source key:

| Key | Source | Feeds |
|---|---|---|
| FAO56_T12, FAO56_T11 | Allen et al. 1998, FAO Irrigation and Drainage Paper 56, Table 12 (crop coefficients) and Table 11 (stage lengths) | Crop water need |
| FAO56_PLANT | FAO-56 Ch. 6: spring wheat sown when the 10-day mean air temperature reaches 5 C, maize at 13 C | Sowing day |
| FAO56_ET0 | FAO-56 Eq. 52 (Hargreaves) and Eq. 21 (extraterrestrial radiation) | Reference evapotranspiration |
| OMAFRA_USLE | OMAFRA Factsheet 23-005, Universal Soil Loss Equation (2023), Table 4 crop type factor, Table 5 tillage factor | USLE cover factor C |
| CRAAQ_N, MAPAQ_WHEAT_N, CRAAQ_SOY_N | CPVQ 1996 nitrogen grid for grain corn (Agri-Réseau feuillet 4B, same rates in the CRAAQ guide); MAPAQ reference grid for spring wheat; CRAAQ soybean rate | Nitrogen to buy |
| SOY_CREDIT, CPVQ_CREDIT | CRAAQ 2010 soybean credit of 25 kg N/ha, cited by N'Dayegamiye et al. 2012, doi:10.5539/sar.v1n2p257; CPVQ residue credit table | Nitrogen credit to the next crop |
| LAL_RATIO | Lal 2005, Environment International 31:575, residue to grain ratios | Crop residue returned |
| CGQ_YIELD | Concertation Grains Québec (2025), mean Quebec yields 1981 to 2023 | Grain yield behind the residue |

Taupin choices with no source: a heavy-rain day is 25 mm or more, April to November, above 0 C
mean air temperature; the soil counts as bare before the end of the FAO-56 initial stage and after
harvest; the dry year is the 1-in-5 worst season; priorities have equal weight. Buckwheat has no
FAO-56 coefficient, Quebec nitrogen rate or CGQ yield, so its years show ? and are not counted.

## Field layers

Baked by `src/taupin/layers.py` into `web/data/field.json` (manifest) and `web/data/layers/*.bin`
on one 300 x 300 grid of 2 m cells (UTM 18N, `src/taupin/grid.py`). Accessed 2026-11-14.

| Layer | Source | Licence | Native resolution | Feeds |
|---|---|---|---|---|
| Terrain height, canopy height | NRCan HRDEM lidar, project QC-600023_52_CMM_2023, DTM and DSM tiles (canelevation-dem S3) | Open Government Licence - Canada | 1 m, averaged to 2 m | 3D relief, trees (canopy = DSM minus DTM), low pocket (lowest 15 % of cells) |
| Hillshade, slope, wetness index | Computed from the HRDEM DTM: wetness index ln(a / tan b) (Beven and Kirkby 1979) with Freeman (1991) multiple flow directions after priority-flood filling (Barnes et al. 2014) | as above | 2 m | Terrain shading, wetness layer, scouting zones |
| Vegetation (NDVI) | NASA HLS v2.0, L30 and S30, mean of 23 clear June to August scenes, 2020-06-02 to 2025-08-31 (Microsoft Planetary Computer STAC) | NASA Earthdata, no restrictions | 30 m, shown as 30 m cells | Vegetation layer, scouting zones |
| Spring surface temperature | USGS Landsat 8/9 Collection 2 Level-2 band ST_B10, 46 clear April and May scenes, 2016 to 2025, each scene minus its parcel mean, then averaged (Planetary Computer STAC) | USGS, public domain | 100 m thermal, distributed at 30 m; shown as 30 m cells | Surface temperature layer, scouting zones |
| Soil map units | IRDA, cartes pédologiques numériques, sheets 31H12-101, -102, -201, -202 (study 41, 1:20 000) | Free download from IRDA; licence terms not checked | Polygons (1:20 000) | Soil layer, scouting zones |
| Soil series attributes (Terrebonne, Terres noires humique, Alluvions récentes) | AAFC CanSIS National Soil Database, soil name and layer tables, Quebec v2r20130705 | Open Government Licence - Canada | One record per series | Soil legend: drainage class, surface layer clay and organic carbon |
| Dorval series | Lajoie P. and Baril R., soil survey of Île de Montréal, Île Jésus and Île Bizard (CanSIS report PQ41), "Série Dorval": clay loam on calcareous till, drainage fairly good | Government of Canada publication | Series description | Soil legend (Dorval is not in the CanSIS Quebec tables) |
| Bait-trap rules | MAPAQ, RAP Grandes cultures, Méthode standard de dépistage des vers fil-de-fer, 16 April 2025, Agri-Réseau doc. 115269, p. 2-3 | Cited, not redistributed | Per field | 10 traps minimum, about 25 m apart, lettered A to J, GPS in decimal degrees |

The park outline is OpenStreetMap way 542903996 (ODbL, © OpenStreetMap contributors), read through
the Overpass API. It limits the trap points to the park; it covers 28.0 ha of the 36 ha square.

Unclear photos and species identification: MAPAQ, Laboratoire d'expertise et de diagnostic en
phytoprotection (quebec.ca, read 2026-11-14): online request form, then images by email or
samples by post. The app shows these steps and sends nothing.

Taupin choices with no source: canopy at or above 2 m counts as tree; trappable ground is under
2 m with at least 60 % such cells in the 30 m around it, mean NDVI at least 0.65 and 15 m in from
the parcel edge; 4 zones (k-means with a fixed seed); traps split between zones in proportion to
area, at least one per zone. The RAP protocol gives no number per hectare, no edge distance and
no rule for splitting traps between zones.
