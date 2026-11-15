"""Write model/MODEL_CARD.md from model/metrics.json and model/labels.json.

Every number in the card is read from metrics.json so the card cannot drift from the run.

    python3 train/make_card.py --model model --notes train/card_notes.md
"""
import argparse
import json
from pathlib import Path


def pct(v):
    return "n/a" if v is None else f"{100 * v:.1f}%"


def ci(r, k):
    lo, hi = r["ci95"].get(k, [None, None])
    return f"{pct(r[k])} [{pct(lo)}, {pct(hi)}]"


def row(name, r):
    return (f"| {name} | {r['n']} | {ci(r, 'accuracy')} | {ci(r, 'macro_f1')} | "
            f"{ci(r, 'coverage_at_threshold')} | {ci(r, 'accuracy_at_threshold')} | {r['ece']:.3f} |")


WEIGHTS = {  # backbone weight licence and provenance, from each model's Hugging Face card
    "efficientnet_b0.ra_in1k": ("`timm/efficientnet_b0.ra_in1k`, Apache-2.0. Pretrained on ImageNet-1k, whose "
                                "image terms are for non-commercial research; stated so a reuser can judge it."),
    "vit_small_patch14_dinov2.lvd142m": ("`timm/vit_small_patch14_dinov2.lvd142m` (Meta DINOv2), Apache-2.0. "
                                         "Self-supervised on LVD-142M, a curated set of web images."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--notes", type=Path, required=True)
    a = ap.parse_args()
    m = json.load(open(a.model / "metrics.json"))
    lab = json.load(open(a.model / "labels.json"))
    notes = a.notes.read_text()
    classes = m["classes"]
    L = []
    L.append(f"# Taupin soil-animal photo classifier ({m['version']})\n")
    L.append("Triage model: it names the animal in a farmer's photo or answers \"unclear: send to the lab\". "
             "It is not a diagnosis; a pest call should be confirmed by a lab or an agronomist before any "
             "treatment decision.\n")
    L.append("## Model\n")
    L.append(f"- Architecture: `{m['arch']}` (timm), fine-tuned, {len(classes)} classes.")
    L.append(f"- File: `model/taupin.onnx`, {m['onnx']['bytes'] / 1e6:.1f} MB, opset {m['onnx']['opset']}, "
             f"input `image` float32 [N,3,{m['input_size']},{m['input_size']}], output `logits` [N,{len(classes)}].")
    L.append(f"- Operators: {', '.join(m['onnx']['ops'])}.")
    L.append(f"- ONNX vs PyTorch on all val, test and OOD images: max abs logit difference "
             f"{m['onnx']['max_abs_logit_diff_vs_torch']:.2e}, top-1 agreement {pct(m['onnx']['top1_agreement_vs_torch'])} "
             f"(onnxruntime {m['onnx']['ort_version']}, CPU).")
    bc = m.get("browser_check")
    if bc:
        L.append(f"- onnxruntime-web {bc['ort_web']} ({bc['backend']} backend, run in Node) on the two reference "
                 f"inputs: max abs logit difference {bc['max_abs_diff']:.2e} against onnxruntime CPU.")
    L.append(f"- Weights: {WEIGHTS.get(m['arch'], m['arch'])}")
    if m.get("test_reads") is not None:
        L.append(f"- The sealed test split was read {m['test_reads']} times (`data/test_access.log`); no "
                 "choice of model, epoch, temperature or threshold used it.")
    L.append(f"- Temperature {m['temperature']:.3f} (fit on validation). Abstain below top-1 probability "
             f"{m['abstain_below']:.3f}, chosen on validation as the lowest threshold whose answered images reach "
             f"{pct(m['abstain_target_accuracy'])} accuracy (target met on validation: {m['target_met_on_val']}).\n")
    L.append("## Classes\n")
    L.append("| id | name | pest |\n|---|---|---|")
    for c in lab["classes"]:
        L.append(f"| {c['id']} | {c['name']} | {'yes' if c['pest'] else 'no'} |")
    L.append("\n## Images per split\n")
    sp = ["train", "val", "test", "ood"]
    L.append("| class | " + " | ".join(sp) + " |\n|---|" + "---|" * len(sp))
    for c in classes:
        L.append(f"| {c} | " + " | ".join(str(m["counts_per_split"][s].get(c, 0)) for s in sp) + " |")
    L.append("| total | " + " | ".join(str(sum(m["counts_per_split"][s].values())) for s in sp) + " |")
    L.append(f"\nOOD sources: {', '.join(f'{k} {v}' for k, v in m['ood_sources'].items())}.\n")
    L.append("## Results\n")
    L.append("OOD (photos from other sources than the training data) is the headline number. Brackets are "
             "95% bootstrap intervals over images (2000 resamples). Coverage is the share of photos the model "
             "answers at the abstain threshold; the rest go to \"send to the lab\".\n")
    L.append("| model / set | n | accuracy | macro-F1 | coverage | accuracy when answering | ECE |")
    L.append("|---|---|---|---|---|---|---|")
    for s, title in [("ood", "OOD"), ("test", "in-distribution test")]:
        L.append(row(f"Taupin, {title}", m["model"][s]))
        for name, b in m["clip_zero_shot"].items():
            L.append(row(f"CLIP zero-shot {name}, {title}", b[s]))
    for k, title in [("specimen", "OOD, museum or lab specimens"), ("field_or_other", "OOD, field and other photos")]:
        if len(m["model"].get("ood_subsets", {})) == 2:  # one subset alone repeats the OOD row
            L.append(row(f"Taupin, {title}", m["model"]["ood_subsets"][k]))
            for name, b in m["clip_zero_shot"].items():
                if k in b.get("ood_subsets", {}):
                    L.append(row(f"CLIP zero-shot {name}, {title}", b["ood_subsets"][k]))
    if m["model"].get("threshold_sweep"):
        L.append("\nAbstain threshold by validation accuracy target (only the shipped target is in labels.json; "
                 "coverage / accuracy when answering):\n")
        L.append("| target | threshold | val | test | OOD |\n|---|---|---|---|---|")
        for tg, v in m["model"]["threshold_sweep"].items():
            cell = lambda h: f"{pct(h['coverage_at_threshold'])} / {pct(h['accuracy_at_threshold'])}"
            L.append(f"| {pct(float(tg))} | {v['abstain_below']:.3f} | {cell(v['val'])} | {cell(v['test'])} | "
                     f"{cell(v['ood'])} |")
    L.append("\nCLIP baselines use the same rows, a prompt ensemble per class, and their own temperature and "
             "threshold fit on the same validation split.\n")
    L.append("### Per class, OOD\n")
    L.append("| class | precision | recall | F1 | support |\n|---|---|---|---|---|")
    for c, v in m["model"]["ood"]["per_class"].items():
        L.append(f"| {c} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} | {v['support']} |")
    L.append("\n### Per class, in-distribution test\n")
    L.append("| class | precision | recall | F1 | support |\n|---|---|---|---|---|")
    for c, v in m["model"]["test"]["per_class"].items():
        L.append(f"| {c} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} | {v['support']} |")
    for s in ["ood", "test"]:
        cm = m["model"][s]["confusion_matrix"]
        L.append(f"\n### Confusion matrix, {s} (rows true, columns predicted)\n")
        L.append("| | " + " | ".join(cm["labels"]) + " |\n|---|" + "---|" * len(cm["labels"]))
        for c, r in zip(cm["labels"], cm["rows_true_cols_pred"]):
            L.append(f"| {c} | " + " | ".join(map(str, r)) + " |")
    L.append("")
    L.append(notes)
    (a.model / "MODEL_CARD.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
