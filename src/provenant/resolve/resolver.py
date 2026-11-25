"""Resolve component metadata from cached fixtures (offline, deterministic)."""

from __future__ import annotations

import os
from typing import Optional

import yaml

from ..model import BOM, Component, Evidence
from .status import classify_provenance

# Packaged base metadata store (covers the real public identifiers used by the
# bundled real-style examples).
_BASE_STORE = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures", "metadata_store.yaml")


def _load_yaml_records(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("components", []) if isinstance(data, dict) else []


class Resolver:
    """Looks components up in a merged metadata store keyed by ``type:name``."""

    def __init__(self, records: Optional[list[dict]] = None):
        self.store: dict[str, dict] = {}
        for rec in records or []:
            key = rec.get("key") or f"{rec.get('type')}:{rec.get('name')}"
            self.store[key] = rec

    @classmethod
    def for_project(cls, project_dir: str, extra_fixtures: Optional[list[str]] = None) -> "Resolver":
        records: list[dict] = []
        records += _load_yaml_records(os.path.abspath(_BASE_STORE))
        proj_fix = os.path.join(project_dir, "provenant_fixtures.yaml")
        records += _load_yaml_records(proj_fix)
        for extra in extra_fixtures or []:
            records += _load_yaml_records(extra)
        return cls(records)

    def lookup(self, comp: Component) -> Optional[dict]:
        return self.store.get(f"{comp.type}:{comp.name}")

    def resolve_component(self, comp: Component) -> None:
        rec = self.lookup(comp)
        record_found = rec is not None
        if rec:
            comp.source_kind = rec.get("source_kind", comp.source_kind)
            comp.source = rec.get("source_url", comp.source)
            comp.license = rec.get("license", comp.license)
            comp.license_source = "fixture" if rec.get("license") else comp.license_source
            comp.publisher = rec.get("publisher", comp.publisher)
            comp.publish_date = rec.get("publish_date", comp.publish_date)
            comp.card_summary = rec.get("card_summary", comp.card_summary)
            revisions = rec.get("revisions", {})
            if comp.version is None:
                comp.version = rec.get("default_revision")
            if comp.version and comp.version in revisions and not comp.hash:
                comp.hash = revisions[comp.version]
            elif not comp.hash and rec.get("default_revision") in revisions:
                comp.hash = revisions[rec["default_revision"]]
            card = rec.get("card")
            if card:
                comp.extra["card"] = card
            comp.evidence.append(
                Evidence("resolver", "metadata resolved from cached fixture store")
            )
        else:
            comp.evidence.append(
                Evidence("resolver", "no metadata record found for this component")
            )
        comp.provenance_status = classify_provenance(
            comp.license, comp.source_kind, record_found
        )


def resolve_bom(bom: BOM, project_dir: str, extra_fixtures: Optional[list[str]] = None,
                online: bool = False) -> BOM:
    """Resolve metadata for every component in ``bom`` (offline by default)."""
    resolver = Resolver.for_project(project_dir, extra_fixtures)
    for comp in bom.components:
        resolver.resolve_component(comp)
    if online:
        # Opt-in, read-only enrichment for components still unresolved.
        from .hub import enrich_online  # local import keeps offline path dependency-free

        enrich_online(bom)
    return bom
