from taupin.engine import ROTATIONS, Field, crw_level, plan_rotation

UPLAND = Field(texture="clay-loam", organic_matter_pct=5.0)
POCKET = Field(texture="clay-loam", organic_matter_pct=12.0)  # wet depression, OM to be measured


def levels(fld, key, **kw):
    return [(r.wireworm, r.corn_rootworm, r.prescription_supportable) for r in plan_rotation(ROTATIONS[key], fld, **kw)]


def count(fld, key):
    return sum(r.prescription_supportable for r in plan_rotation(ROTATIONS[key], fld))


def test_single_factor_never_supports_prescription():
    # RAP: the combination of factors drives risk; sod return alone on clay-loam stays MODERATE.
    for key in ROTATIONS:
        assert count(UPLAND, key) == 0
    assert levels(UPLAND, "B_corn_soy_wheat")[0] == ("MODERATE", "LOW", False)


def test_high_om_pocket_counts():
    assert [count(POCKET, k) for k in ROTATIONS] == [5, 2, 1, 2]   # D: corn in years 1, 3, 5


def test_buckwheat_is_not_a_prescription_crop():
    r = plan_rotation(ROTATIONS["C_with_buckwheat"], POCKET)[1]
    assert r.crop == "buckwheat" and r.wireworm == "HIGH" and not r.prescription_supportable


def test_crw_first_year_corn_low_then_builds():
    assert [x[1] for x in levels(UPLAND, "A_continuous_corn")] == ["LOW", "MODERATE", "HIGH", "HIGH", "HIGH"]
    assert crw_level("corn", ["corn", "wheat"]) [0] == "LOW"
    assert crw_level("soybean", ["corn"])[0] == "NONE"


def test_trap_count_overrides_factors():
    # H. abbreviatus threshold is 3 larvae/trap: 3.5 confirms HIGH even on upland clay-loam.
    r = plan_rotation(ROTATIONS["B_corn_soy_wheat"], UPLAND, traps={2026: 3.5})[0]
    assert r.wireworm == "HIGH" and r.prescription_supportable
    r = plan_rotation(ROTATIONS["B_corn_soy_wheat"], POCKET, traps={2026: 0.5})[0]
    assert r.wireworm == "MODERATE" and not r.prescription_supportable


def test_every_decision_has_a_cited_trace():
    for r in plan_rotation(ROTATIONS["C_with_buckwheat"], POCKET):
        assert r.trace and all("[" in t for t in r.trace)
