"""AIBOM assembly and schema validity."""

import pytest

from provenant.evaluate import run_pipeline
from provenant.aibom import (
    assemble_cyclonedx, assemble_spdx, validate_cyclonedx, validate_spdx,
)
from conftest import project


def test_cyclonedx_validates_for_all_projects(synthetic_projects):
    for pdir in synthetic_projects:
        bom, _ = run_pipeline(pdir)
        validate_cyclonedx(assemble_cyclonedx(bom))  # raises on failure


def test_spdx_validates_for_all_projects(synthetic_projects):
    for pdir in synthetic_projects:
        bom, _ = run_pipeline(pdir)
        validate_spdx(assemble_spdx(bom))


def test_cyclonedx_carries_the_provenance_graph(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "multihop_finetune"))
    doc = assemble_cyclonedx(bom)
    edges = {(d["ref"], on) for d in doc["dependencies"] for on in d.get("dependsOn", [])}
    assert ("model:labB/foundation-7b-chat", "model:labA/foundation-7b-sft") in edges
    assert ("model:labA/foundation-7b-sft", "model:acme/foundation-7b") in edges


def test_spdx_maps_lineage_to_relationships(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "finetune_stack"))
    doc = assemble_spdx(bom)
    rel_types = {r["relationshipType"] for r in doc["relationships"]}
    assert "DESCENDANT_OF" in rel_types  # finetuned_from
    assert "GENERATED_FROM" in rel_types  # trained_on


def test_invalid_document_is_rejected():
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        validate_cyclonedx({"bomFormat": "NotCycloneDX", "specVersion": "1.6",
                            "version": 1, "components": []})
