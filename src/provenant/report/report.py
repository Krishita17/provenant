"""Render the human- and machine-readable deliverables for one project."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Optional

from ..model import BOM, ComponentType, RelationType, Severity
from ..policy import PolicyKB
from ..aibom import assemble_cyclonedx, assemble_spdx
from ..analyze import RULES
from .graph import render_provenance_graph

_CAVEAT = (
    "> **Informational, not legal advice.** This report supports human governance "
    "review. License classifications and compatibility findings are informational "
    "and must be confirmed by someone qualified for licensing decisions. "
    "Unresolved provenance is reported as `unknown` rather than guessed, and the "
    "bill of materials is a point-in-time artifact."
)

_SARIF_LEVEL = {"high": "error", "medium": "warning", "low": "note", "info": "note"}


# --------------------------------------------------------------------------- #
# Derived views
# --------------------------------------------------------------------------- #
def _parent_of(bom: BOM, comp_id: str) -> Optional[str]:
    for r in bom.relationships:
        if r.src == comp_id and r.rel_type == RelationType.FINETUNED_FROM:
            c = bom.by_id(r.dst)
            return c.name if c else r.dst
    return None


def _license_class(kb: PolicyKB, license: Optional[str]) -> str:
    info = kb.license_info(license)
    if info is None:
        return "unknown"
    return info.cls


def component_table_rows(bom: BOM, kb: Optional[PolicyKB] = None) -> list[dict]:
    kb = kb or PolicyKB.load()
    findings_by_comp: dict[str, list[str]] = {}
    for f in bom.findings:
        findings_by_comp.setdefault(f.component_id, []).append(f.category)
    rows = []
    for c in sorted(bom.components, key=lambda c: (c.type, c.name)):
        rows.append({
            "component": c.name,
            "type": c.type,
            "version": c.version or "",
            "hash": (c.hash or "")[:19],
            "source": c.source or (c.source_kind if c.source_kind != "unknown" else ""),
            "license": c.license or "unknown",
            "license_class": _license_class(kb, c.license),
            "provenance": c.provenance_status,
            "lineage_parent": _parent_of(bom, c.id) or "",
            "risk": ", ".join(sorted(set(findings_by_comp.get(c.id, [])))) or "-",
        })
    return rows


def summary_counts(bom: BOM, kb: Optional[PolicyKB] = None) -> dict:
    kb = kb or PolicyKB.load()
    by_type = Counter(c.type for c in bom.components)
    by_license_class = Counter(_license_class(kb, c.license) if c.license else "unknown"
                               for c in bom.components)
    by_severity = Counter(f.severity for f in bom.findings)
    by_category = Counter(f.category for f in bom.findings)
    by_provenance = Counter(c.provenance_status for c in bom.components)
    return {
        "components_total": len(bom.components),
        "by_type": dict(by_type),
        "by_license_class": dict(by_license_class),
        "findings_total": len(bom.findings),
        "by_severity": dict(by_severity),
        "by_category": dict(by_category),
        "by_provenance": dict(by_provenance),
    }


# --------------------------------------------------------------------------- #
# SARIF
# --------------------------------------------------------------------------- #
def build_sarif(bom: BOM) -> dict:
    rule_ids = sorted({f.rule_id for f in bom.findings})
    rules = [
        {
            "id": rid,
            "name": rid,
            "shortDescription": {"text": RULES.get(rid, rid)},
        }
        for rid in rule_ids
    ]
    results = []
    for f in bom.findings:
        locations = []
        for ev in f.evidence:
            if ev.path:
                loc = {"physicalLocation": {"artifactLocation": {"uri": ev.path}}}
                if ev.line:
                    loc["physicalLocation"]["region"] = {"startLine": ev.line}
                locations.append(loc)
        result = {
            "ruleId": f.rule_id,
            "level": _SARIF_LEVEL.get(f.severity, "note"),
            "message": {"text": f"{f.message} Recommendation: {f.recommendation}"},
            "properties": {
                "category": f.category,
                "component": f.component_id,
                "severity": f.severity,
            },
        }
        if f.related_component_id:
            result["properties"]["related_component"] = f.related_component_id
        if locations:
            result["locations"] = locations
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Provenant",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/Krishita17/provenant",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def render_markdown(bom: BOM, kb: Optional[PolicyKB] = None,
                    graph_rel: Optional[str] = None) -> str:
    kb = kb or PolicyKB.load()
    name = bom.project.get("name", "project")
    s = summary_counts(bom, kb)
    rows = component_table_rows(bom, kb)

    out = [f"# AIBOM & Provenance Risk Report — `{name}`", ""]
    out.append(_CAVEAT)
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(_md_table(
        ["Metric", "Value"],
        [
            ["Components", s["components_total"]],
            ["  models / datasets / frameworks",
             f'{s["by_type"].get("model",0)} / {s["by_type"].get("dataset",0)} / {s["by_type"].get("framework",0)}'],
            ["Provenance resolved / partial / unknown",
             f'{s["by_provenance"].get("resolved",0)} / {s["by_provenance"].get("partial",0)} / {s["by_provenance"].get("unknown",0)}'],
            ["Findings (total)", s["findings_total"]],
            ["  high / medium / low / info",
             f'{s["by_severity"].get("high",0)} / {s["by_severity"].get("medium",0)} / {s["by_severity"].get("low",0)} / {s["by_severity"].get("info",0)}'],
        ],
    ))
    out.append("")

    out.append("## Components")
    out.append("")
    out.append("The signature artifact: every component with its source, license, "
               "lineage parent and risk.")
    out.append("")
    out.append(_md_table(
        ["Component", "Type", "Version", "Source", "License", "Class", "Provenance", "Lineage parent", "Risk"],
        [[r["component"], r["type"], r["version"] or "—", r["source"] or "—",
          r["license"], r["license_class"], r["provenance"],
          r["lineage_parent"] or "—", r["risk"]] for r in rows],
    ))
    out.append("")

    out.append("## Risk findings")
    out.append("")
    if not bom.findings:
        out.append("_No risk findings._")
    else:
        for f in bom.findings:
            comp = bom.by_id(f.component_id)
            cname = comp.name if comp else f.component_id
            out.append(f"### [{f.severity.upper()}] {f.category} — `{cname}`")
            out.append("")
            out.append(f"- **Rule**: `{f.rule_id}` — {RULES.get(f.rule_id,'')}")
            out.append(f"- **Finding**: {f.message}")
            if f.related_component_id:
                rc = bom.by_id(f.related_component_id)
                out.append(f"- **Related component**: `{rc.name if rc else f.related_component_id}`")
            out.append(f"- **Recommendation**: {f.recommendation}")
            ev_bits = []
            for ev in f.evidence:
                loc = f" ({ev.path}:{ev.line})" if ev.path and ev.line else (f" ({ev.path})" if ev.path else "")
                ev_bits.append(f"{ev.source}: {ev.detail}{loc}")
            if ev_bits:
                out.append(f"- **Evidence**: " + "; ".join(ev_bits))
            out.append("")

    out.append("## Provenance graph")
    out.append("")
    if graph_rel:
        out.append(f"![Provenance graph]({graph_rel})")
    else:
        out.append("_No provenance edges reconstructed for this project._")
    out.append("")

    out.append("## Method & limitations")
    out.append("")
    out.append("- Discovery is signal-based and can miss components it has no "
               "detector for; recall is measured, not assumed.")
    out.append("- Metadata and licenses are a point-in-time snapshot resolved from "
               "cached fixtures; re-run to refresh.")
    out.append("- License findings are informational governance signals, not a "
               "legal determination.")
    out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def render_project_report(bom: BOM, out_dir: str, timestamp=None) -> dict:
    """Write every deliverable for ``bom`` into ``out_dir`` and return paths."""
    os.makedirs(out_dir, exist_ok=True)
    kb = PolicyKB.load()

    cdx = assemble_cyclonedx(bom) if timestamp is None else assemble_cyclonedx(bom, timestamp)
    spdx = assemble_spdx(bom) if timestamp is None else assemble_spdx(bom, timestamp)
    paths = {}

    paths["cyclonedx"] = os.path.join(out_dir, "aibom.cdx.json")
    with open(paths["cyclonedx"], "w", encoding="utf-8") as fh:
        json.dump(cdx, fh, indent=2)
        fh.write("\n")

    paths["spdx"] = os.path.join(out_dir, "aibom.spdx.json")
    with open(paths["spdx"], "w", encoding="utf-8") as fh:
        json.dump(spdx, fh, indent=2)
        fh.write("\n")

    paths["sarif"] = os.path.join(out_dir, "report.sarif.json")
    with open(paths["sarif"], "w", encoding="utf-8") as fh:
        json.dump(build_sarif(bom), fh, indent=2)
        fh.write("\n")

    # Provenance graph (skipped cleanly if there are no edges).
    graph_rel = None
    if bom.relationships:
        graph_svg = os.path.join(out_dir, "provenance_graph.svg")
        graph_png = os.path.join(out_dir, "provenance_graph.png")
        render_provenance_graph(bom, graph_png, graph_svg)
        paths["graph_svg"] = graph_svg
        paths["graph_png"] = graph_png
        graph_rel = "provenance_graph.svg"

    paths["report"] = os.path.join(out_dir, "report.md")
    with open(paths["report"], "w", encoding="utf-8") as fh:
        fh.write(render_markdown(bom, kb, graph_rel))

    paths["components_csv"] = os.path.join(out_dir, "components.csv")
    rows = component_table_rows(bom, kb)
    with open(paths["components_csv"], "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["component"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    paths["bom"] = os.path.join(out_dir, "bom.json")
    bom.save(paths["bom"])
    return paths
