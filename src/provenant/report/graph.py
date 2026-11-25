"""Deterministic, dependency-light rendering of the provenance graph.

Uses a layered layout (ancestors/datasets at the bottom, fine-tunes at the top)
drawn with matplotlib — no Graphviz/system dependency — so the figure is the
auto-generated visual proof of lineage reconstruction.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

from ..model import BOM, ComponentType, RelationType  # noqa: E402

# Colourblind-safe, labelled (never colour alone).
_TYPE_STYLE = {
    ComponentType.MODEL: {"face": "#CDE3F0", "edge": "#2166AC", "label": "model"},
    ComponentType.DATASET: {"face": "#FBE3D0", "edge": "#B35806", "label": "dataset"},
    ComponentType.FRAMEWORK: {"face": "#E4E4E4", "edge": "#6B6B6B", "label": "framework"},
}
_PROVENANCE_RELS = (RelationType.FINETUNED_FROM, RelationType.TRAINED_ON, RelationType.DERIVED_FROM)


def _short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _depths(nodes, parents):
    """Longest-path depth: pure ancestors/datasets at depth 0."""
    memo = {}

    def depth(n, stack=()):
        if n in memo:
            return memo[n]
        if n in stack:  # guard against cycles
            return 0
        ps = parents.get(n, [])
        d = 0 if not ps else 1 + max(depth(p, stack + (n,)) for p in ps)
        memo[n] = d
        return d

    return {n: depth(n) for n in nodes}


def render_provenance_graph(bom: BOM, out_png: str, out_svg: str | None = None) -> None:
    # Graph nodes = components that participate in provenance edges.
    parents: dict[str, list[str]] = {}
    edge_list = []
    node_ids = set()
    for r in bom.relationships:
        if r.rel_type not in _PROVENANCE_RELS:
            continue
        parents.setdefault(r.src, []).append(r.dst)
        edge_list.append((r.src, r.dst, r.rel_type))
        node_ids.add(r.src)
        node_ids.add(r.dst)

    if not node_ids:
        return

    comps = {cid: bom.by_id(cid) for cid in node_ids}
    depths = _depths(node_ids, parents)
    max_depth = max(depths.values()) or 1

    # Group nodes by depth, order within a layer by name for determinism.
    layers: dict[int, list[str]] = {}
    for nid in node_ids:
        layers.setdefault(depths[nid], []).append(nid)
    for d in layers:
        layers[d].sort(key=lambda nid: (comps[nid].type, comps[nid].name))

    pos = {}
    max_width = max(len(v) for v in layers.values())
    col_spacing = 1.25  # > box width, so boxes never overlap
    for d, ids in layers.items():
        n = len(ids)
        span = (n - 1) * col_spacing
        for i, nid in enumerate(ids):
            pos[nid] = (i * col_spacing - span / 2.0, d)

    fig_w = max(6.0, max_width * col_spacing * 2.1)
    fig_h = max(3.0, (max_depth + 1) * 1.9)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Edges first (under boxes). Edges that skip a layer are bowed so they do
    # not pass straight through an intermediate, vertically-aligned node.
    for src, dst, rel in edge_list:
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        style = "-" if rel == RelationType.FINETUNED_FROM else "--"
        span = abs(depths[src] - depths[dst])
        rad = 0.5 if span > 1 else 0.05
        arrow = FancyArrowPatch(
            (x0, y0 - 0.18), (x1, y1 + 0.18),
            arrowstyle="-|>", mutation_scale=13, linewidth=1.4,
            linestyle=style, color="#555555", shrinkA=5, shrinkB=5,
            connectionstyle=f"arc3,rad={rad}",
        )
        ax.add_patch(arrow)

    bw, bh = 0.9, 0.34
    for nid, (x, y) in pos.items():
        c = comps[nid]
        st = _TYPE_STYLE.get(c.type, _TYPE_STYLE[ComponentType.MODEL])
        box = FancyBboxPatch(
            (x - bw / 2, y - bh / 2), bw, bh,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=st["face"], edgecolor=st["edge"], linewidth=1.6,
        )
        ax.add_patch(box)
        lic = c.license or "unknown"
        ax.text(x, y + 0.03, _short(c.name), ha="center", va="center",
                fontsize=8.5, fontweight="bold")
        ax.text(x, y - 0.10, f"{st['label']} · {lic}", ha="center", va="center",
                fontsize=6.6, color="#333333")

    # Legend.
    handles = [
        plt.Line2D([0], [0], color="#555555", linestyle="-", label="finetuned_from"),
        plt.Line2D([0], [0], color="#555555", linestyle="--", label="trained_on"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.0),
              ncol=1, frameon=True, framealpha=0.85, fontsize=8)

    half = (max_width - 1) * col_spacing / 2.0 + 0.7
    ax.set_xlim(-half, half)
    ax.set_ylim(-0.7, max_depth + 0.9)
    ax.axis("off")
    ax.set_title(f"Provenance graph — {bom.project.get('name','')}", fontsize=11, pad=16)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    if out_svg:
        fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
