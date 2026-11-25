"""Regenerate every README figure from ``results/metrics.json``.

All figures are code-generated and regenerable via ``make figures`` — none is
hand-drawn. Colours are chosen to stay legible for colourblind readers and are
always paired with text labels.
"""

from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

from ..policy import PolicyKB, Compatibility  # noqa: E402

_TYPE_COLOR = {"model": "#2166AC", "dataset": "#B35806", "framework": "#6B6B6B"}
_PROV_COLOR = {"resolved": "#1A9850", "partial": "#FDAE61", "unknown": "#D73027"}
_SEV_COLOR = {"high": "#D73027", "medium": "#FDAE61", "low": "#4393C3", "info": "#999999"}
_BAR = "#2166AC"
_COMPAT_COLOR = {
    Compatibility.OK: "#1A9850",
    Compatibility.OBLIGATION: "#A6D96A",
    Compatibility.CONDITIONAL: "#FDAE61",
    Compatibility.CONFLICT: "#D73027",
    Compatibility.REVIEW: "#BBBBBB",
}
_COMPAT_LABEL = {
    Compatibility.OK: "OK",
    Compatibility.OBLIGATION: "obligations",
    Compatibility.CONDITIONAL: "conditional",
    Compatibility.CONFLICT: "CONFLICT",
    Compatibility.REVIEW: "review",
}


def _save(fig, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _bar(ax, labels, values, colors, title, ylabel="count"):
    bars = ax.bar(labels, values, color=colors, edgecolor="#333333", linewidth=0.6)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(axis="x", labelsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                f"{v:g}", ha="center", va="bottom", fontsize=8.5)
    if values:
        ax.set_ylim(0, max(values) * 1.18 + 0.5)


# --------------------------------------------------------------------------- #
# Individual figures
# --------------------------------------------------------------------------- #
def fig_components_overview(agg, out_dir):
    by_type = agg["by_type"]
    by_lic = agg["by_license_class"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    t_labels = [t for t in ("model", "dataset", "framework") if t in by_type]
    _bar(ax1, t_labels, [by_type[t] for t in t_labels],
         [_TYPE_COLOR[t] for t in t_labels], "Components by type")
    l_order = ["permissive", "public_domain", "copyleft", "restricted", "non_commercial", "unknown"]
    l_labels = [l for l in l_order if l in by_lic]
    _bar(ax2, [l.replace("_", "\n") for l in l_labels], [by_lic[l] for l in l_labels],
         [_BAR] * len(l_labels), "Components by license class")
    fig.suptitle("AIBOM composition (all evaluated projects)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return _save(fig, out_dir, "components_overview.png")


def fig_findings_by_category(agg, out_dir):
    by_cat = agg["by_category"]
    order = ["license_incompatibility", "non_commercial", "flagged_source",
             "missing_provenance", "restrictive_license", "unpinned", "license_review"]
    labels = [c for c in order if c in by_cat] + [c for c in by_cat if c not in order]
    values = [by_cat[c] for c in labels]
    fig, ax = plt.subplots(figsize=(8, 4))
    _bar(ax, [l.replace("_", "\n") for l in labels], values, [_BAR] * len(labels),
         "Risk findings by category (all projects)")
    return _save(fig, out_dir, "findings_by_category.png")


def fig_provenance_completeness(agg, out_dir):
    by_prov = agg["by_provenance"]
    labels = [p for p in ("resolved", "partial", "unknown") if p in by_prov]
    values = [by_prov[p] for p in labels]
    fig, ax = plt.subplots(figsize=(6, 4))
    _bar(ax, labels, values, [_PROV_COLOR[p] for p in labels],
         "Provenance completeness (the honesty chart)", ylabel="components")
    return _save(fig, out_dir, "provenance_completeness.png")


def fig_accuracy(overall, out_dir):
    metrics = [
        ("Discovery recall", overall["discovery_recall"]),
        ("Lineage precision", overall["lineage"]["precision"]),
        ("Lineage recall", overall["lineage"]["recall"]),
        ("Finding precision", overall["finding"]["precision"]),
        ("Finding recall", overall["finding"]["recall"]),
        ("Provenance accuracy", overall["provenance_accuracy"]),
        ("Unknown precision", overall["unknown"]["precision"]),
        ("Unknown recall", overall["unknown"]["recall"]),
    ]
    labels = [m[0] for m in metrics][::-1]
    values = [m[1] for m in metrics][::-1]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(labels, values, color=_BAR, edgecolor="#333333", linewidth=0.6)
    ax.set_xlim(0, 1.08)
    ax.axvline(1.0, color="#999999", linestyle=":", linewidth=1)
    ax.set_title("Accuracy vs. hand/ground-truth labels", fontsize=11, fontweight="bold")
    ax.set_xlabel("score (1.0 = perfect)", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    for b, v in zip(bars, values):
        ax.text(min(v + 0.01, 1.01), b.get_y() + b.get_height() / 2,
                f"{v:.2f}", va="center", fontsize=8.5)
    fig.tight_layout()
    return _save(fig, out_dir, "accuracy_vs_ground_truth.png")


def fig_conflict_prevalence(overall, out_dir):
    n = overall["n_projects"]
    with_c = overall["projects_with_license_conflict"]
    fig, ax = plt.subplots(figsize=(5, 4))
    _bar(ax, ["with license\nconflict", "without"], [with_c, n - with_c],
         ["#D73027", "#1A9850"], "License-conflict prevalence across projects",
         ylabel="projects")
    return _save(fig, out_dir, "license_conflict_prevalence.png")


def fig_compatibility_matrix(out_dir):
    kb = PolicyKB.load()
    rows = ["apache-2.0", "cc-by-4.0", "cc-by-sa-4.0", "cc-by-nc-4.0", "other"]   # dataset
    cols = ["apache-2.0", "mit", "openrail", "llama-2-community"]                  # model
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for i, d in enumerate(rows):
        for j, m in enumerate(cols):
            verdict = kb.pair_compatibility(d, m)
            ax.add_patch(plt.Rectangle((j, len(rows) - 1 - i), 1, 1,
                         facecolor=_COMPAT_COLOR[verdict], edgecolor="white", linewidth=2))
            ax.text(j + 0.5, len(rows) - 1 - i + 0.5, _COMPAT_LABEL[verdict],
                    ha="center", va="center", fontsize=8,
                    color="white" if verdict in (Compatibility.CONFLICT,) else "#111111")
    ax.set_xticks([j + 0.5 for j in range(len(cols))])
    ax.set_xticklabels(cols, fontsize=8.5, rotation=15, ha="right")
    ax.set_yticks([len(rows) - 1 - i + 0.5 for i in range(len(rows))])
    ax.set_yticklabels(rows, fontsize=8.5)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(0, len(rows))
    ax.set_xlabel("model distribution license", fontsize=9)
    ax.set_ylabel("dataset license", fontsize=9)
    ax.set_title("License compatibility (dataset × model, assuming commercial use)",
                 fontsize=11, fontweight="bold")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    return _save(fig, out_dir, "license_compatibility_matrix.png")


# --------------------------------------------------------------------------- #
# Architecture diagram (matplotlib) + Mermaid source
# --------------------------------------------------------------------------- #
_ARCH_STAGES = [
    ("ML project", "configs · scripts · model refs · requirements · notebooks", "#E4E4E4"),
    ("1 · Component discovery", "local artifacts · hub refs · datasets · frameworks", "#CDE3F0"),
    ("2 · Metadata resolver", "version/hash · source · model & dataset license · card", "#CDE3F0"),
    ("3 · Lineage reconstructor", "fine-tune → base → datasets  (provenance graph)", "#BBDFF0"),
    ("4 · Risk & compliance analyzer", "restrictive/NC · incompatibility · missing · unpinned · flagged", "#CDE3F0"),
    ("5 · AIBOM assembler", "CycloneDX ML-BOM · SPDX AI-profile", "#CDE3F0"),
    ("6 · Report generator", "AIBOM JSON · provenance graph · risk report · SARIF/MD", "#CDE3F0"),
]


def fig_architecture(out_dir):
    fig, ax = plt.subplots(figsize=(8.5, 9.5))
    n = len(_ARCH_STAGES)
    box_w, box_h = 7.2, 1.0
    gap = 0.42
    y = n * (box_h + gap)
    centers = []
    for title, sub, color in _ARCH_STAGES:
        edge = "#2166AC" if title[0].isdigit() else "#6B6B6B"
        box = FancyBboxPatch((0.4, y), box_w, box_h,
                             boxstyle="round,pad=0.02,rounding_size=0.08",
                             facecolor=color, edgecolor=edge, linewidth=1.8)
        ax.add_patch(box)
        ax.text(0.4 + box_w / 2, y + box_h * 0.62, title, ha="center", va="center",
                fontsize=10.5, fontweight="bold")
        ax.text(0.4 + box_w / 2, y + box_h * 0.24, sub, ha="center", va="center",
                fontsize=7.6, color="#333333")
        centers.append(y)
        y -= (box_h + gap)

    for i in range(n - 1):
        y_top = centers[i]
        y_bot = centers[i + 1] + box_h
        ax.add_patch(FancyArrowPatch((0.4 + box_w / 2, y_top), (0.4 + box_w / 2, y_bot),
                     arrowstyle="-|>", mutation_scale=16, color="#444444", linewidth=1.5))

    # Policy KB side-box feeding the analyzer (stage index 4).
    kb_y = centers[4] + box_h / 2
    ax.add_patch(FancyBboxPatch((8.0, kb_y - 0.5), 2.3, 1.0,
                 boxstyle="round,pad=0.02,rounding_size=0.08",
                 facecolor="#FBE3D0", edgecolor="#B35806", linewidth=1.6))
    ax.text(9.15, kb_y, "License /\npolicy KB", ha="center", va="center",
            fontsize=8.5, fontweight="bold")
    ax.add_patch(FancyArrowPatch((8.0, kb_y), (0.4 + box_w, kb_y),
                 arrowstyle="-|>", mutation_scale=14, color="#B35806", linewidth=1.4))

    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, (n) * (box_h + gap) + box_h)
    ax.axis("off")
    ax.set_title("Provenant architecture", fontsize=13, fontweight="bold", pad=10)
    fig.tight_layout()
    return _save(fig, out_dir, "architecture.png")


_MERMAID = """flowchart TD
    P["ML project<br/>configs · scripts · model refs · requirements · notebooks"]
    D1["1 · Component discovery<br/>local artifacts · hub refs · datasets · frameworks"]
    D2["2 · Metadata resolver<br/>version/hash · source · model & dataset license · card"]
    D3["3 · Lineage reconstructor<br/>fine-tune → base → datasets (provenance graph)"]
    KB["License / policy KB<br/>terms · compatibility · flagged sources"]
    D4["4 · Risk & compliance analyzer<br/>restrictive/NC · incompatibility · missing · unpinned · flagged"]
    D5["5 · AIBOM assembler<br/>CycloneDX ML-BOM · SPDX AI-profile"]
    D6["6 · Report generator<br/>AIBOM JSON · provenance graph · risk report · SARIF/MD"]
    P --> D1 --> D2 --> D3 --> D4 --> D5 --> D6
    KB --> D4
"""


def write_mermaid(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "architecture.mmd")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_MERMAID)
    return path


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def generate_figures(results_dir: str, out_dir: str) -> list[str]:
    with open(os.path.join(results_dir, "metrics.json"), encoding="utf-8") as fh:
        metrics = json.load(fh)
    overall = metrics["overall"]
    agg = overall["aggregate"]

    produced = [
        fig_architecture(out_dir),
        write_mermaid(out_dir),
        fig_components_overview(agg, out_dir),
        fig_findings_by_category(agg, out_dir),
        fig_provenance_completeness(agg, out_dir),
        fig_accuracy(overall, out_dir),
        fig_conflict_prevalence(overall, out_dir),
        fig_compatibility_matrix(out_dir),
    ]
    return produced
