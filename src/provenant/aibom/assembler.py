"""Assemble CycloneDX ML-BOM and SPDX AI-profile documents from a BOM."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Optional

from ..model import BOM, Component, ComponentType, RelationType

FIXED_TIMESTAMP = "2026-01-01T00:00:00Z"
_UUID_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")
_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

# CycloneDX component type per Provenant component type.
_CDX_TYPE = {
    ComponentType.MODEL: "machine-learning-model",
    ComponentType.DATASET: "data",
    ComponentType.FRAMEWORK: "library",
}

# SPDX license expression mapping for recognised ids; others become LicenseRef-*.
_SPDX_LICENSE = {
    "apache-2.0": "Apache-2.0",
    "mit": "MIT",
    "bsd-3-clause": "BSD-3-Clause",
    "cc0-1.0": "CC0-1.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc-by-sa-3.0": "CC-BY-SA-3.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "gpl-3.0": "GPL-3.0-only",
    "agpl-3.0": "AGPL-3.0-only",
}

# Provenance edge -> SPDX 2.3 relationship type.
_SPDX_REL = {
    RelationType.FINETUNED_FROM: "DESCENDANT_OF",
    RelationType.TRAINED_ON: "GENERATED_FROM",
    RelationType.DERIVED_FROM: "DESCENDANT_OF",
    RelationType.USES_FRAMEWORK: "DEPENDS_ON",
}


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z.\-]+", "-", s).strip("-") or "x"


def _spdx_license(lic: Optional[str]) -> str:
    if not lic:
        return "NOASSERTION"
    low = lic.lower()
    if low in _SPDX_LICENSE:
        return _SPDX_LICENSE[low]
    return "LicenseRef-" + _slug(lic)


def _project_name(bom: BOM) -> str:
    return str(bom.project.get("name", "project"))


# --------------------------------------------------------------------------- #
# CycloneDX ML-BOM
# --------------------------------------------------------------------------- #
def assemble_cyclonedx(bom: BOM, timestamp: str = FIXED_TIMESTAMP) -> dict:
    name = _project_name(bom)
    serial = f"urn:uuid:{uuid.uuid5(_UUID_NS, 'cdx:' + name)}"

    components = []
    for c in bom.components:
        comp = {
            "type": _CDX_TYPE.get(c.type, "library"),
            "bom-ref": c.id,
            "name": c.name,
        }
        if c.version:
            comp["version"] = c.version
        if c.license:
            comp["licenses"] = [{"license": {"name": c.license}}]
        if c.source:
            comp["externalReferences"] = [{"type": "distribution", "url": c.source}]
        props = [
            {"name": "provenant:provenance_status", "value": c.provenance_status},
            {"name": "provenant:source_kind", "value": c.source_kind},
        ]
        if c.publisher:
            props.append({"name": "provenant:publisher", "value": c.publisher})
        if c.publish_date:
            props.append({"name": "provenant:publish_date", "value": c.publish_date})
        if c.hash:
            props.append({"name": "provenant:content_hash", "value": c.hash})
        comp["properties"] = props
        if c.type == ComponentType.MODEL and c.card_summary:
            comp["modelCard"] = {
                "properties": [{"name": "summary", "value": c.card_summary}]
            }
        components.append(comp)

    # Provenance graph as CycloneDX dependencies.
    deps: dict[str, list[str]] = {}
    for r in bom.relationships:
        deps.setdefault(r.src, [])
        if r.dst not in deps[r.src]:
            deps[r.src].append(r.dst)
    dependencies = [{"ref": ref, "dependsOn": sorted(on)} for ref, on in sorted(deps.items())]

    annotations = [
        {
            "bom-ref": f"finding-{i}",
            "subjects": [f.component_id],
            "annotator": {"organization": {"name": "Provenant"}},
            "timestamp": timestamp,
            "text": f"[{f.severity.upper()}][{f.rule_id}] {f.message}",
        }
        for i, f in enumerate(bom.findings)
    ]

    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": {"components": [{"type": "application", "name": "provenant", "version": "0.1.0"}]},
            "component": {"type": "application", "name": name, "bom-ref": f"app:{_slug(name)}"},
        },
        "components": components,
        "dependencies": dependencies,
    }
    if annotations:
        doc["annotations"] = annotations
    return doc


# --------------------------------------------------------------------------- #
# SPDX 2.3 (AI-profile annotations)
# --------------------------------------------------------------------------- #
def assemble_spdx(bom: BOM, timestamp: str = FIXED_TIMESTAMP) -> dict:
    name = _project_name(bom)
    doc_uuid = uuid.uuid5(_UUID_NS, "spdx:" + name)
    id_map: dict[str, str] = {}
    for i, c in enumerate(bom.components):
        id_map[c.id] = f"SPDXRef-{c.type}-{i}-{_slug(c.name)}"[:120]

    packages = []
    for c in bom.components:
        ai_type = {"model": "model", "dataset": "dataset", "framework": "framework"}[c.type]
        pkg = {
            "SPDXID": id_map[c.id],
            "name": c.name,
            "downloadLocation": c.source or "NOASSERTION",
            "licenseDeclared": _spdx_license(c.license),
            "licenseConcluded": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "primaryPackagePurpose": "OTHER",
            "versionInfo": c.version or "NOASSERTION",
            "supplier": f"Organization: {c.publisher}" if c.publisher else "NOASSERTION",
            "annotations": [
                {
                    "annotator": "Tool: provenant-0.1.0",
                    "annotationDate": timestamp,
                    "annotationType": "OTHER",
                    "comment": (
                        f"ai-profile: type={ai_type}; "
                        f"provenance_status={c.provenance_status}; "
                        f"source_kind={c.source_kind}"
                        + (f"; content_hash={c.hash}" if c.hash else "")
                    ),
                }
            ],
        }
        packages.append(pkg)

    relationships = [
        {"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": id_map[c.id],
         "relationshipType": "DESCRIBES"}
        for c in bom.components
    ]
    for r in bom.relationships:
        if r.src in id_map and r.dst in id_map:
            relationships.append({
                "spdxElementId": id_map[r.src],
                "relatedSpdxElement": id_map[r.dst],
                "relationshipType": _SPDX_REL.get(r.rel_type, "DEPENDS_ON"),
            })

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": name,
        "documentNamespace": f"https://provenant.example/spdx/{name}/{doc_uuid}",
        "creationInfo": {
            "created": timestamp,
            "creators": ["Tool: provenant-0.1.0"],
        },
        "packages": packages,
        "relationships": relationships,
        "documentDescribes": [id_map[c.id] for c in bom.components],
    }


# --------------------------------------------------------------------------- #
# Validation against bundled profile schemas
# --------------------------------------------------------------------------- #
def _load_schema(fname: str) -> dict:
    with open(os.path.join(_SCHEMA_DIR, fname), encoding="utf-8") as fh:
        return json.load(fh)


def validate_cyclonedx(doc: dict) -> None:
    """Raise ``jsonschema.ValidationError`` if ``doc`` is not a valid ML-BOM."""
    import jsonschema

    jsonschema.validate(doc, _load_schema("cyclonedx-mlbom.schema.json"))


def validate_spdx(doc: dict) -> None:
    """Raise ``jsonschema.ValidationError`` if ``doc`` is not a valid SPDX doc."""
    import jsonschema

    jsonschema.validate(doc, _load_schema("spdx-ai.schema.json"))
