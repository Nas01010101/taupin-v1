"""Rule engine for wireworm (taupin / ver fil-de-fer) and corn rootworm risk in Quebec field crops.

Every rule carries the source it comes from, so a rule trace can be printed next to a decision.
The engine does not decide whether insecticide-coated seed is used: since 1 Aug 2025 that needs an
agronomist's prescription. It only reports whether the documented risk factors would support one.
"""
from dataclasses import dataclass, field

SRC = {
    "RAP": "RAP Grandes cultures, Méthode standard de dépistage des VFF (Agri-Réseau doc. 115269)",
    "SAGUEZ": "Saguez et al. 2017, Environ. Entomol. 46:1165, doi:10.1093/ee/nvx116",
    "NORONHA": "Noronha et al. 2023, Arthropod-Plant Interact., doi:10.1007/s11829-023-09982-9",
    "MAPAQ_CRW": "MAPAQ / RAP fiche chrysomèle des racines du maïs (Agri-Réseau doc. 118135)",
    "QC_2025": "Code de gestion des pesticides, D. 470-2025: certificate + prescription for class 3A seed from 1 Aug 2025",
}

GRASS = {"corn", "wheat", "barley", "oat", "sod"}  # Poaceae: hosts that sustain wireworm populations
# Crops whose insecticide-coated (class 3A) seed needs a prescription since 1 Aug 2025 (QC_2025).
PRESCRIPTION_CROPS = {"corn", "soybean", "wheat", "barley", "oat", "canola"}
# Economic thresholds, larvae per trap per count (RAP).
TRAP_THRESHOLD = {"hypnoidus": 3.0, "agriotes": 1.0, "limonius": 1.0, "melanotus": 1.0}
LEVELS = ["LOW", "MODERATE", "HIGH"]


@dataclass
class Field:
    texture: str = "clay-loam"        # "sand", "loamy-sand", "organic" count as light/organic soils
    organic_matter_pct: float = 5.0
    dominant_genus: str = "hypnoidus"  # H. abbreviatus = 72 % of Quebec wireworms (SAGUEZ)


@dataclass
class YearRisk:
    year: int
    crop: str
    wireworm: str
    corn_rootworm: str
    prescription_supportable: bool
    trace: list = field(default_factory=list)


def wireworm_factors(fld: Field, history: list, years_since_sod: int) -> list:
    """Return the RAP risk factors present. RAP stresses that the combination matters, not one factor."""
    f = []
    if fld.texture in {"sand", "loamy-sand", "organic"}:
        f.append(("light or organic soil", "RAP"))
    if fld.organic_matter_pct > 10:
        f.append(("organic matter > 10 %", "RAP"))
    grass_run = 0
    for crop in reversed(history):
        if crop not in GRASS:
            break
        grass_run += 1
    # Sod return and long grass runs are one biological factor (grass hosts); counted once.
    if years_since_sod <= 2 or grass_run >= 3:
        f.append((f"grass history (years since sod={years_since_sod}, grass run={grass_run})", "RAP"))
    return f


def wireworm_level(fld, history, years_since_sod, trap_mean=None):
    factors = wireworm_factors(fld, history, years_since_sod)
    level = min(len(factors), 2)
    trace = [f"WW factor: {name} [{SRC[s]}]" for name, s in factors]
    if history and history[-1] == "buckwheat" and level > 0:
        level -= 1  # larval survival 15 % on buckwheat vs 44 % on barley over 120 d (NORONHA)
        trace.append(f"WW -1: previous buckwheat slows larval growth/survival, not a biofumigant [{SRC['NORONHA']}]")
    if trap_mean is not None:
        thr = TRAP_THRESHOLD[fld.dominant_genus]
        level = 2 if trap_mean >= thr else min(level, 1)
        trace.append(f"WW trap mean {trap_mean} vs threshold {thr}/trap ({fld.dominant_genus}) [{SRC['RAP']}]")
    return LEVELS[level], trace


def crw_level(crop, history):
    """Rotation breaks the cycle; extended diapause is not observed in Quebec (MAPAQ_CRW)."""
    if crop != "corn":
        return "NONE", []
    run = 0
    for c in reversed(history):
        if c != "corn":
            break
        run += 1
    level = LEVELS[min(run, 2)]
    return level, [f"CRW: {run} prior corn year(s) -> {level} [{SRC['MAPAQ_CRW']}]"]


def plan_rotation(crops, fld, start_year=2026, years_since_sod=1, prior=("sod", "sod", "sod"), traps=None):
    """Score each year of a rotation. `traps` maps year -> observed mean larvae/trap (optional)."""
    traps = traps or {}
    history, out = list(prior), []
    for i, crop in enumerate(crops):
        year = start_year + i
        ww, t1 = wireworm_level(fld, history, years_since_sod + i, traps.get(year))
        crw, t2 = crw_level(crop, history)
        ok = crop in PRESCRIPTION_CROPS and ww == "HIGH"
        t3 = [f"Prescription {'supportable' if ok else 'not supported'} for {crop} [{SRC['QC_2025']}]"]
        out.append(YearRisk(year, crop, ww, crw, ok, t1 + t2 + t3))
        history.append(crop)
    return out


ROTATIONS = {
    "A_continuous_corn": ["corn"] * 5,
    "B_corn_soy_wheat": ["corn", "soybean", "wheat", "corn", "soybean"],
    "C_with_buckwheat": ["corn", "buckwheat", "soybean", "wheat", "corn"],
}
