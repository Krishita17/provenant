"""Score the pipeline against ground truth and emit metrics + CSVs.

Metrics (all honest, all measured, never assumed):

* **discovery_recall** — of the components present in the project *files*, how
  many the file-based discovery stage finds.
* **component_recall / precision (final)** — completeness/precision of the final
  BOM after transitive lineage expansion.
* **lineage precision / recall / F1** — on provenance edges (finetuned_from,
  trained_on, derived_from) vs ground truth. The core, hardest metric.
* **finding precision / recall** — on (component, category) risk findings.
* **provenance accuracy** and **unknown precision / recall** — the gap-honesty
  calibration: does the tool report ``unknown`` exactly when it should?
* **aibom validity** — the emitted CycloneDX/SPDX documents validate against the
  bundled profile schemas.
"""

from __future__ import annotations

import copy
import csv
import json
import os
from typing import Optional

from collections import Counter

from .model import BOM, ComponentType, RelationType
from .discover import discover_project
from .resolve import resolve_bom
from .lineage import reconstruct_lineage
from .analyze import analyze_bom
from .aibom import assemble_cyclonedx, assemble_spdx, validate_cyclonedx, validate_spdx
from .policy import PolicyKB

_PROV_RELS = {RelationType.FINETUNED_FROM, RelationType.TRAINED_ON, RelationType.DERIVED_FROM}


def run_pipeline(project_dir: str):
    """Run discover -> resolve -> lineage -> analyze; return (final_bom, discovered_keys)."""
    bom = discover_project(project_dir)
    discovered_keys = {(c.type, c.name) for c in bom.components}
    resolve_bom(bom, project_dir)
    reconstruct_lineage(bom, project_dir)
    analyze_bom(bom)
    return bom, discovered_keys


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def _edge_set(rels, bom: Optional[BOM] = None):
    """Normalise relationships to (src_name, dst_name, rel_type) sets."""
    out = set()
    for r in rels:
        if isinstance(r, dict):
            if r["rel_type"] not in _PROV_RELS:
                continue
            out.add((r["src"], r["dst"], r["rel_type"]))
        else:
            if r.rel_type not in _PROV_RELS:
                continue
            s = bom.by_id(r.src)
            d = bom.by_id(r.dst)
            out.add((s.name if s else r.src, d.name if d else r.dst, r.rel_type))
    return out


def evaluate_project(project_dir: str, gold_path: str) -> dict:
    with open(gold_path, encoding="utf-8") as fh:
        gt = json.load(fh)

    bom, discovered_keys = run_pipeline(project_dir)

    gt_comps = gt["components"]
    gt_keys = {(c["type"], c["name"]) for c in gt_comps}
    gt_file_present = {(c["type"], c["name"]) for c in gt_comps if c.get("file_present")}
    final_keys = {(c.type, c.name) for c in bom.components}

    # Discovery recall (file-present components only).
    disc_tp = len(discovered_keys & gt_file_present)
    discovery_recall = round(disc_tp / len(gt_file_present), 4) if gt_file_present else 1.0

    # Final component recall/precision.
    comp_tp = len(final_keys & gt_keys)
    comp = _prf(comp_tp, len(final_keys - gt_keys), len(gt_keys - final_keys))

    # Lineage edges.
    gt_edges = _edge_set(gt["relationships"])
    pred_edges = _edge_set(bom.relationships, bom)
    lin = _prf(len(gt_edges & pred_edges), len(pred_edges - gt_edges), len(gt_edges - pred_edges))

    # Findings (component_id, category). GT ids are "type:name"; so are findings'.
    gt_findings = {(f["component_id"], f["category"]) for f in gt.get("expected_findings", [])}
    pred_findings = {(f.component_id, f.category) for f in bom.findings}
    find = _prf(len(gt_findings & pred_findings), len(pred_findings - gt_findings), len(gt_findings - pred_findings))

    # Provenance status accuracy + unknown calibration.
    gt_status = {(c["type"], c["name"]): c["provenance_status"] for c in gt_comps}
    pred_status = {(c.type, c.name): c.provenance_status for c in bom.components}
    matched = [k for k in gt_status if k in pred_status]
    correct = sum(1 for k in matched if pred_status[k] == gt_status[k])
    prov_acc = round(correct / len(matched), 4) if matched else 1.0
    # Gap-honesty is a CALIBRATION metric over components that are in the BOM:
    # does the tool report `unknown` exactly when it should? (A component that
    # was never discovered is accounted for by discovery/component recall, not
    # double-counted here.)
    matched_set = set(matched)
    gt_unknown = {k for k in matched_set if gt_status[k] == "unknown"}
    pred_unknown = {k for k in matched_set if pred_status[k] == "unknown"}
    unk = _prf(len(gt_unknown & pred_unknown), len(pred_unknown - gt_unknown), len(gt_unknown - pred_unknown))

    # AIBOM validity.
    try:
        validate_cyclonedx(assemble_cyclonedx(bom))
        cdx_valid = True
    except Exception:
        cdx_valid = False
    try:
        validate_spdx(assemble_spdx(bom))
        spdx_valid = True
    except Exception:
        spdx_valid = False

    # Breakdowns for the figures (aggregated across projects by evaluate()).
    kb = PolicyKB.load()

    def _lclass(lic):
        if not lic:
            return "unknown"
        info = kb.license_info(lic)
        return info.cls if info else "unknown"

    breakdown = {
        "by_type": dict(Counter(c.type for c in bom.components)),
        "by_license_class": dict(Counter(_lclass(c.license) for c in bom.components)),
        "by_category": dict(Counter(f.category for f in bom.findings)),
        "by_provenance": dict(Counter(c.provenance_status for c in bom.components)),
    }

    return {
        "name": gt["project"]["name"],
        "kind": gt["project"].get("kind", "synthetic"),
        "discovery_recall": discovery_recall,
        "component": comp,
        "lineage": lin,
        "finding": find,
        "provenance_accuracy": prov_acc,
        "unknown": unk,
        "cyclonedx_valid": cdx_valid,
        "spdx_valid": spdx_valid,
        "breakdown": breakdown,
        "counts": {
            "components": len(bom.components),
            "models": sum(1 for c in bom.components if c.type == ComponentType.MODEL),
            "datasets": sum(1 for c in bom.components if c.type == ComponentType.DATASET),
            "frameworks": sum(1 for c in bom.components if c.type == ComponentType.FRAMEWORK),
            "edges": len(pred_edges),
            "findings": len(bom.findings),
            "has_license_conflict": any(f.category == "license_incompatibility" for f in bom.findings),
        },
    }


def _find_gold(project_dir: str, gold_dir: str) -> Optional[str]:
    local = os.path.join(project_dir, "ground_truth.json")
    if os.path.isfile(local):
        return local
    candidate = os.path.join(gold_dir, os.path.basename(project_dir.rstrip("/")) + ".json")
    if os.path.isfile(candidate):
        return candidate
    return None


def discover_projects(parent_dirs: list[str], gold_dir: str) -> list[tuple[str, str]]:
    found = []
    for parent in parent_dirs:
        if not os.path.isdir(parent):
            continue
        for name in sorted(os.listdir(parent)):
            pdir = os.path.join(parent, name)
            if not os.path.isdir(pdir):
                continue
            gold = _find_gold(pdir, gold_dir)
            if gold:
                found.append((pdir, gold))
    return found


def _micro(projects: list[dict], path: list[str]) -> dict:
    tp = fp = fn = 0
    for p in projects:
        node = p
        for k in path:
            node = node[k]
        tp += node["tp"]; fp += node["fp"]; fn += node["fn"]
    return _prf(tp, fp, fn)


def evaluate(parent_dirs: list[str], out_dir: str, gold_dir: str = "references/gold") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    pairs = discover_projects(parent_dirs, gold_dir)
    projects = [evaluate_project(pdir, gold) for pdir, gold in pairs]

    overall = {
        "n_projects": len(projects),
        "discovery_recall": round(
            sum(p["discovery_recall"] for p in projects) / len(projects), 4) if projects else 1.0,
        "component": _micro(projects, ["component"]),
        "lineage": _micro(projects, ["lineage"]),
        "finding": _micro(projects, ["finding"]),
        "unknown": _micro(projects, ["unknown"]),
        "provenance_accuracy": round(
            sum(p["provenance_accuracy"] for p in projects) / len(projects), 4) if projects else 1.0,
        "cyclonedx_valid": sum(p["cyclonedx_valid"] for p in projects),
        "spdx_valid": sum(p["spdx_valid"] for p in projects),
        "projects_with_license_conflict": sum(
            1 for p in projects if p["counts"]["has_license_conflict"]),
    }

    # Aggregate breakdowns across all projects (for the headline charts).
    agg = {"by_type": Counter(), "by_license_class": Counter(),
           "by_category": Counter(), "by_provenance": Counter()}
    for p in projects:
        for key, counter in agg.items():
            counter.update(p["breakdown"][key])
    overall["aggregate"] = {k: dict(v) for k, v in agg.items()}

    metrics = {"overall": overall, "projects": projects}

    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
        fh.write("\n")

    # Per-project CSV (for the README results table + figures).
    with open(os.path.join(out_dir, "per_project.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "kind", "components", "edges", "findings",
                    "discovery_recall", "lineage_f1", "finding_f1",
                    "provenance_accuracy", "cyclonedx_valid", "spdx_valid"])
        for p in projects:
            w.writerow([p["name"], p["kind"], p["counts"]["components"],
                        p["counts"]["edges"], p["counts"]["findings"],
                        p["discovery_recall"], p["lineage"]["f1"], p["finding"]["f1"],
                        p["provenance_accuracy"], int(p["cyclonedx_valid"]),
                        int(p["spdx_valid"])])

    return metrics
