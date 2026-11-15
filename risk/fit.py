"""Field-scale wireworm risk model fitted on Labrie et al. 2020 (PLoS ONE 15(2): e0229136).

Label: mean wireworms per bait trap (untreated and treated plots, most abundant sampling date,
read off Figs 1 and 3 by risk/digitize.py) at or above 1 per trap.
Inputs: the paper's S1 site table and NASA POWER weather at each site (risk/fetch_power.py).
Usage: python risk/fit.py <out_dir>   (writes metrics.json, risk_model.json, loo_predictions.csv)
"""
import csv, json, pathlib, re, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

HERE = pathlib.Path(__file__).parent
THRESHOLD, C, SEED = 1.0, 1.0, 0
PX = 0.05  # one pixel of the published figure is about 0.04 wireworms per trap; below this is zero

# name -> (how the app gets it, transform)
FIELD = {
    "grass_prev": ("field form: previous crop was hay, pasture or sod", "0/1"),
    "forage_years": ("field form: years in forage before this crop", "log1p"),
    "light_soil": ("soil layer: sand or sandy loam", "0/1"),
    "om_pct": ("soil layer: organic matter %", "log"),
    "no_till": ("field form: no-till", "0/1"),
    "soybean": ("field form: crop is soybean", "0/1"),
}
NASA = {
    "gwet_spring": ("NASA POWER GWETROOT, mean 1 Apr to 31 May", "identity"),
    "tsoil_spring_c": ("NASA POWER TSOIL1, mean 15 Apr to 31 May", "identity"),
    "precip_prev_mm": ("NASA POWER PRECTOTCORR, sum 1 May to 30 Sep of the previous year", "identity"),
    "tsoil_winter_min_c": ("NASA POWER TSOIL1, minimum 1 Dec to 31 Mar", "identity"),
}


def load():
    key = lambda r: (r["crop"], r["year"], r["site"])
    bait = {key(r): r for r in csv.DictReader(open(HERE / "data/labrie_bait_digitized.csv"))}
    power = {key(r): r for r in csv.DictReader(open(HERE / "data/power_features.csv"))}
    rows = []
    for r in csv.DictReader(open(HERE / "data/labrie_sites.csv")):
        if key(r) not in bait:
            continue  # two soybean sites are in S1 but not in Fig 3
        b, p = bait[key(r)], power[key(r)]
        def num(s):  # S1 writes some forage durations as "> 1" or "5 +": keep the number
            m = re.search(r"-?\d+(\.\d+)?", s.replace(",", "."))
            return float(m.group()) if m else np.nan
        u, t = (0.0 if float(b[k]) < PX else float(b[k]) for k in ("untreated", "treated"))
        rows.append({
            "key": key(r), "year": int(r["year"]), "count": (u + t) / 2,
            "area": r["area"].replace("-", " "),  # S1 spells Montérégie Est both ways
            "cell": f'{round(float(r["lat"]) * 2) / 2},{round(float(r["lon"]) / 0.625) * 0.625}',  # POWER grid cell
            "grass_prev": float(r["previous_crop"] == "Grassland"),
            "forage_years": np.log1p(num(r["forage_years"])),
            "light_soil": float(r["texture"] in ("Sand", "Sandy loam")),
            "om_pct": np.log(num(r["om_pct"])),
            "no_till": float(r["tillage"] == "No-Till"),
            "soybean": float(r["crop"] == "Soybean"),
            **{k: num(p[k]) for k in NASA},
            # RAP factor count used by src/taupin/engine.py (the literature prior)
            "prior": float(r["texture"] in ("Sand", "Organic")) + float(num(r["om_pct"]) > 10)
                     + float(r["previous_crop"] == "Grassland"),
        })
    return rows


def matrix(rows, names):
    X = np.array([[r[n] for n in names] for r in rows], float)
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isnan(X), med, X)
    return X


def fit(X, y):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    m = LogisticRegression(C=C, max_iter=2000).fit((X - mu) / sd, y)
    return m, mu, sd


def held_out(X, y, groups):
    """Predict each group with a model that never saw it."""
    p = np.zeros(len(y))
    for g in np.unique(groups):
        te = groups == g
        if y[~te].min() == y[~te].max():
            p[te] = y[~te].mean(); continue
        m, mu, sd = fit(X[~te], y[~te])
        p[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
    return p


def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    rows = load()
    y = np.array([r["count"] >= THRESHOLD for r in rows], int)
    count = np.array([r["count"] for r in rows])
    years = np.array([r["year"] for r in rows])
    rng = np.random.default_rng(SEED)
    areas, cells = (np.array([r[k] for r in rows]) for k in ("area", "cell"))
    # The first three sets were fixed before any fit. "compact" was picked after seeing their
    # cross-validation (the features that carried signal), so its scores are optimistic.
    sets = {"field": list(FIELD), "nasa": list(NASA), "field_nasa": list(FIELD) + list(NASA),
            "compact": ["light_soil", "forage_years", "gwet_spring", "tsoil_winter_min_c"]}
    metrics = {"n": len(y), "positives": int(y.sum()), "threshold_per_trap": THRESHOLD,
               "label_source": "digitized from Labrie et al. 2020 Figs 1 and 3",
               "years": sorted(set(int(v) for v in years)), "regions": len(set(areas)), "power_cells": len(set(cells)),
               "models": {}}
    prior = np.array([r["prior"] for r in rows])
    metrics["models"]["rule_prior"] = {"auc": round(roc_auc_score(y, prior), 3), "fitted": False}
    preds = {}
    for name, cols in sets.items():
        X = matrix(rows, cols)
        loo = held_out(X, y, np.arange(len(y)))
        loyo = held_out(X, y, years)
        auc = roc_auc_score(y, loo)
        boot = []
        for _ in range(2000):
            i = rng.integers(0, len(y), len(y))
            if y[i].min() != y[i].max():
                boot.append(roc_auc_score(y[i], loo[i]))
        perm = []
        for _ in range(300):  # shuffle labels, redo the whole leave-one-out
            yp = rng.permutation(y)
            perm.append(roc_auc_score(yp, held_out(X, yp, np.arange(len(y)))))
        rho = float(np.corrcoef(np.argsort(np.argsort(loo)), np.argsort(np.argsort(count)))[0, 1])
        metrics["models"][name] = {
            "features": cols, "fitted": True,
            "auc_leave_one_field_out": round(auc, 3),
            "auc_ci95": [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)],
            "auc_leave_one_year_out": round(roc_auc_score(y, loyo), 3),
            "auc_leave_one_region_out": round(roc_auc_score(y, held_out(X, y, areas)), 3),
            "auc_leave_one_power_cell_out": round(roc_auc_score(y, held_out(X, y, cells)), 3),
            "permutation_p": round((1 + sum(a >= auc for a in perm)) / (1 + len(perm)), 4),
            "brier": round(brier_score_loss(y, loo), 4),
            "brier_base_rate": round(brier_score_loss(y, np.full(len(y), y.mean())), 4),
            "rank_corr_with_count": round(rho, 3),
        }
        preds[name] = loo
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    with open(out / "loo_predictions.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["crop", "year", "site", "count", "label", "prior", *preds])
        for i, r in enumerate(rows):
            w.writerow([*r["key"], round(r["count"], 2), y[i], r["prior"], *(round(float(preds[k][i]), 4) for k in preds)])
    # exported model: all rows, the feature set named on the command line (default field_nasa)
    chosen = sys.argv[2] if len(sys.argv) > 2 else "compact"
    cols = sets[chosen]
    m, mu, sd = fit(matrix(rows, cols), y)
    spec = {**FIELD, **NASA}
    model = {
        "kind": "logistic", "version": "labrie2020-" + chosen, "provenance": "trained",
        "target": f"P(mean wireworms per bait trap >= {THRESHOLD}) for a whole field",
        "features": [{"name": c, "layer": spec[c][0], "transform": spec[c][1],
                      "mean": round(float(mu[i]), 5), "sd": round(float(sd[i]), 5)} for i, c in enumerate(cols)],
        "intercept": round(float(m.intercept_[0]), 5),
        "coef": {c: round(float(m.coef_[0][i]), 5) for i, c in enumerate(cols)},
        "metrics": {"n": len(y), "positives": int(y.sum()), **metrics["models"][chosen],
                    "rule_prior_auc": metrics["models"]["rule_prior"]["auc"]},
        "sources": ["Labrie et al. 2020, PLoS ONE 15(2): e0229136, doi:10.1371/journal.pone.0229136 (S1 Table, Figs 1 and 3; CC BY 4.0)",
                    "NASA POWER daily point API, MERRA-2, 0.5 x 0.625 degree"],
    }
    (out / "risk_model.json").write_text(json.dumps(model, indent=1))
    print(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
