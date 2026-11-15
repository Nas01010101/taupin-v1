"""Inputs, score and ranking of the trained field model as the bake computes them."""
import json
import math
import pathlib

import pytest

from taupin import fieldrisk as fr

ROOT = pathlib.Path(__file__).parent.parent
MODEL = json.loads((ROOT / "web/data/risk_model.json").read_text())


def test_power_features_use_the_same_windows_as_the_training_fetch():
    p = {"GWETROOT": {"20250331": 0.1, "20250401": 0.6, "20250531": 0.8, "20250601": 0.1, "20250415": -999.0},
         "TSOIL1": {"20231231": -30.0, "20241201": -9.0, "20250115": -12.5, "20250331": -1.0,
                    "20250401": -40.0, "20250201": -999.0}}
    f = fr.power_features(p, 2025)
    assert f == {"gwet_spring": 0.7, "tsoil_winter_min_c": -12.5}
    assert fr.power_features(p, 2027) == {"gwet_spring": None, "tsoil_winter_min_c": None}


def test_score_at_the_training_means_is_the_intercept():
    at_mean = {f["name"]: f["mean"] for f in MODEL["features"]}
    at_mean["forage_years"] = math.expm1(at_mean["forage_years"])  # log1p is undone
    assert fr.score(MODEL, at_mean) == pytest.approx(MODEL["intercept"])
    light = dict(at_mean, light_soil=1)
    f = next(f for f in MODEL["features"] if f["name"] == "light_soil")
    assert fr.score(MODEL, light) - fr.score(MODEL, at_mean) == pytest.approx(MODEL["coef"]["light_soil"] * (1 - f["mean"]) / f["sd"])


def test_transform_rejects_an_unknown_kind():
    assert fr.transform("log1p", 0) == 0
    with pytest.raises(ValueError):
        fr.transform("sqrt", 4)


def test_light_soil_matches_the_training_definition():
    assert fr.is_light("Sandy loam") == fr.is_light("Sand") == 1
    assert fr.is_light("Organic") == fr.is_light("Clay loam") == fr.is_light("Loamy sand") == 0


def test_first_number_keeps_the_number_of_a_written_duration():
    assert fr.first_number("> 1") == 1 and fr.first_number("5 +") == 5 and fr.first_number("") == 0


def test_cutpoints_split_the_sorted_scores_in_thirds():
    assert fr.cutpoints([9, 1, 5, 3, 7, 2, 8, 4, 6]) == [3, 6]


def test_committed_field_inputs_match_a_fresh_ranking():
    if not (ROOT / "risk/data/labrie_sites.csv").exists():
        pytest.skip("risk/ training tables not in this checkout")
    rows = fr.training_inputs()
    assert len(rows) == 82 and sum(r["light_soil"] for r in rows) == 26  # mean 0.31707 in the model file
    baked = json.loads((ROOT / "web/data/field_risk.json").read_text())
    assert baked["rank_cutpoints"] == [round(c, 4) for c in fr.cutpoints(fr.training_scores(MODEL, rows))]
    assert set(baked["per_year"]) >= {"2025", "2026"}


def test_web_model_is_the_trained_file_unchanged():
    src = ROOT / "risk/model/risk_model.json"
    if not src.exists():
        pytest.skip("risk/ not in this checkout")
    assert (ROOT / "web/data/risk_model.json").read_bytes() == src.read_bytes()
