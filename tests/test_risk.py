"""The field risk model: its labels match the paper's published counts and its file is usable."""
import csv
import json
import math
import pathlib

RISK = pathlib.Path(__file__).parent.parent / "risk"


def bait():
    return list(csv.DictReader(open(RISK / "data/labrie_bait_digitized.csv")))


def test_digitized_counts_match_the_paper():
    # Labrie et al. 2020: 5 soybean fields above 1 wireworm per trap; 2 corn fields reached 3 per trap.
    rows = bait()
    assert len(rows) == 82
    soy = [r for r in rows if r["crop"] == "Soybean" and float(r["mean"]) >= 1]
    corn3 = [r for r in rows if r["crop"] == "Corn" and float(r["mean"]) >= 3]
    assert len(soy) == 5 and len(corn3) == 2
    corn = [r for r in rows if r["crop"] == "Corn"]
    below = sum(float(r["mean"]) < 1 for r in corn) / len(corn)
    assert len(corn) == 68 and below > 0.9  # the paper reports 92.6 %


def test_every_site_with_a_count_has_covariates_and_weather():
    key = lambda r: (r["crop"], r["year"], r["site"])
    sites = {key(r) for r in csv.DictReader(open(RISK / "data/labrie_sites.csv"))}
    power = {key(r) for r in csv.DictReader(open(RISK / "data/power_features.csv"))}
    assert all(key(r) in sites and key(r) in power for r in bait())


def predict(model, x):
    z = model["intercept"]
    for f in model["features"]:
        v = x[f["name"]]
        v = {"log1p": math.log1p, "log": math.log}.get(f["transform"], float)(v)
        z += model["coef"][f["name"]] * (v - f["mean"]) / f["sd"]
    return 1 / (1 + math.exp(-z))


def test_model_file_predicts_and_orders_fields():
    model = json.loads((RISK / "model/risk_model.json").read_text())
    assert model["kind"] == "logistic" and model["provenance"] == "trained"
    assert set(model["coef"]) == {f["name"] for f in model["features"]}
    dry_sand = predict(model, {"light_soil": 1, "forage_years": 0, "gwet_spring": 0.6, "tsoil_winter_min_c": -19})
    wet_clay = predict(model, {"light_soil": 0, "forage_years": 0, "gwet_spring": 0.85, "tsoil_winter_min_c": -11})
    assert 0 < wet_clay < dry_sand < 1


def test_reported_metrics_are_the_measured_ones():
    metrics = json.loads((RISK / "model/metrics.json").read_text())
    model = json.loads((RISK / "model/risk_model.json").read_text())
    chosen = metrics["models"]["compact"]
    assert metrics["n"] == 82 and metrics["positives"] == 11
    assert model["metrics"]["auc_leave_one_field_out"] == chosen["auc_leave_one_field_out"]
    assert chosen["auc_leave_one_field_out"] > metrics["models"]["rule_prior"]["auc"]
