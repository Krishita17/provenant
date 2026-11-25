"""Reconstruct the provenance graph from config and card signals."""

from __future__ import annotations

import json
import os
from typing import Optional

import yaml

from ..model import (
    BOM,
    Component,
    ComponentType,
    Evidence,
    Relationship,
    RelationType,
    component_id,
)
from ..discover.discovery import DATASET_CONFIG_KEYS, _SKIP_DIRS, _SKIP_FILES
from ..resolve.resolver import Resolver

BASE_KEYS = {"base_model"}
TRAINEE_KEYS = {"model_name_or_path", "pretrained_model_name_or_path"}


def _strip_rev(ref: str) -> str:
    if "@" in ref and not ref.startswith("http"):
        return ref.rpartition("@")[0]
    return ref


def _ensure(bom: BOM, resolver: Resolver, ctype: str, name: str) -> Component:
    """Return the component, creating+resolving it if referenced but unseen."""
    cid = component_id(ctype, name)
    comp = bom.by_id(cid)
    if comp is not None:
        return comp
    comp = Component(
        id=cid,
        type=ctype,
        name=name,
        source_kind="huggingface",
        evidence=[Evidence("lineage", "referenced transitively via a component card")],
    )
    bom.add_component(comp)
    resolver.resolve_component(comp)
    return comp


def _add_edge(bom: BOM, src: Component, dst: Component, rel_type: str, ev: Evidence) -> None:
    bom.add_relationship(
        Relationship(src=src.id, dst=dst.id, rel_type=rel_type, evidence=[ev])
    )


# --------------------------------------------------------------------------- #
# Config-based edges
# --------------------------------------------------------------------------- #
def _iter_config_files(project_dir: str):
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if fname in _SKIP_FILES:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".yaml", ".yml", ".json") and fname != "ground_truth.json":
                yield os.path.join(root, fname)


def _load_config(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) if path.endswith(".json") else yaml.safe_load(fh)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _config_edges(bom: BOM, resolver: Resolver, project_dir: str) -> None:
    for path in _iter_config_files(project_dir):
        data = _load_config(path)
        if not data:
            continue
        rel = os.path.relpath(path, project_dir).replace(os.sep, "/")

        base = next((_strip_rev(str(data[k])) for k in BASE_KEYS if k in data and isinstance(data[k], str)), None)
        trainee = next((_strip_rev(str(data[k])) for k in TRAINEE_KEYS if k in data and isinstance(data[k], str)), None)

        datasets: list[str] = []
        for k in DATASET_CONFIG_KEYS:
            if k in data:
                v = data[k]
                for item in (v if isinstance(v, list) else [v]):
                    if isinstance(item, str) and not item.startswith("http"):
                        datasets.append(_strip_rev(item))

        # finetuned_from: trainee derives from base
        if base and trainee:
            s = _ensure(bom, resolver, ComponentType.MODEL, trainee)
            d = _ensure(bom, resolver, ComponentType.MODEL, base)
            _add_edge(bom, s, d, RelationType.FINETUNED_FROM,
                      Evidence("config", f"base_model/model_name_or_path in {rel}", path=rel))

        # trained_on: the trainee was trained on the declared datasets
        if trainee and datasets:
            s = _ensure(bom, resolver, ComponentType.MODEL, trainee)
            for ds in datasets:
                d = _ensure(bom, resolver, ComponentType.DATASET, ds)
                _add_edge(bom, s, d, RelationType.TRAINED_ON,
                          Evidence("config", f"datasets in {rel}", path=rel))


# --------------------------------------------------------------------------- #
# Card-based edges (with transitive expansion)
# --------------------------------------------------------------------------- #
def _card_edges(bom: BOM, resolver: Resolver) -> None:
    processed: set[str] = set()
    # Fixpoint: resolving a new parent may surface a card with further ancestry.
    while True:
        progressed = False
        for comp in list(bom.components):
            if comp.id in processed:
                continue
            processed.add(comp.id)
            card = comp.extra.get("card") or {}
            base = card.get("base_model")
            if base:
                parent = _ensure(bom, resolver, ComponentType.MODEL, _strip_rev(str(base)))
                _add_edge(bom, comp, parent, RelationType.FINETUNED_FROM,
                          Evidence("model_card", f"'finetuned from' in {comp.name}'s card"))
                progressed = True
            for ds in card.get("datasets", []) or []:
                dcomp = _ensure(bom, resolver, ComponentType.DATASET, _strip_rev(str(ds)))
                _add_edge(bom, comp, dcomp, RelationType.TRAINED_ON,
                          Evidence("model_card", f"'trained on' in {comp.name}'s card"))
                progressed = True
        if not progressed:
            break


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def reconstruct_lineage(bom: BOM, project_dir: str,
                        extra_fixtures: Optional[list[str]] = None) -> BOM:
    """Populate ``bom.relationships`` with the reconstructed provenance graph."""
    resolver = Resolver.for_project(project_dir, extra_fixtures)
    _config_edges(bom, resolver, project_dir)
    _card_edges(bom, resolver)
    bom.components.sort(key=lambda c: (c.type, c.name))
    bom.relationships.sort(key=lambda r: (r.rel_type, r.src, r.dst))
    return bom


def provenance_subgraph(bom: BOM, root_id: str) -> set[str]:
    """Return every component id reachable from ``root_id`` along provenance
    edges (``finetuned_from`` / ``trained_on`` / ``derived_from``)."""
    provenance_rels = {
        RelationType.FINETUNED_FROM,
        RelationType.TRAINED_ON,
        RelationType.DERIVED_FROM,
    }
    adj: dict[str, list[str]] = {}
    for r in bom.relationships:
        if r.rel_type in provenance_rels:
            adj.setdefault(r.src, []).append(r.dst)
    seen: set[str] = set()
    stack = [root_id]
    while stack:
        node = stack.pop()
        for nxt in adj.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen
