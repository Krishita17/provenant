"""Stage-level checks: discovery, resolution and the risk analyzer."""

import os

from provenant.discover import discover_project
from provenant.resolve import resolve_bom
from provenant.lineage import reconstruct_lineage
from provenant.analyze import analyze_bom
from provenant.evaluate import run_pipeline
from conftest import project


def _finding_set(bom):
    return {(f.component_id, f.category) for f in bom.findings}


def test_discovery_finds_models_datasets_frameworks(synthetic_base):
    pdir = project(synthetic_base, "finetune_stack")
    bom = discover_project(pdir)
    names = {(c.type, c.name) for c in bom.components}
    assert ("model", "acme/base-lm-1b") in names
    assert ("model", "myorg/base-lm-1b-chat") in names
    assert ("dataset", "research-lab/dialogs-nc") in names
    assert ("framework", "transformers") in names


def test_discovery_ignores_non_ai_dependencies(synthetic_base):
    bom = discover_project(project(synthetic_base, "vision_pipeline"))
    names = {c.name for c in bom.components}
    assert "numpy" not in names and "opencv-python" not in names


def test_local_artifact_reconciles_with_named_model(synthetic_base):
    bom = discover_project(project(synthetic_base, "finetune_stack"))
    chat = bom.by_id("model:myorg/base-lm-1b-chat")
    # the .safetensors file merges into the config-referenced model, not a dupe
    assert chat is not None and chat.hash is not None
    assert bom.by_id("model:models/base-lm-1b-chat.safetensors") is None


def test_resolver_fills_license_and_marks_unknown(synthetic_base):
    pdir = project(synthetic_base, "rag_app")
    bom = discover_project(pdir)
    resolve_bom(bom, pdir)
    minilm = bom.by_id("model:opencorp/minilm-embed")
    assert minilm.license == "apache-2.0" and minilm.provenance_status == "resolved"
    llm = bom.by_id("model:sketchy-hub/uncensored-llm")
    assert llm.license is None and llm.provenance_status != "resolved"


def test_analyzer_non_commercial_and_incompatibility(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "finetune_stack"))
    f = _finding_set(bom)
    assert ("dataset:research-lab/dialogs-nc", "non_commercial") in f
    assert ("model:myorg/base-lm-1b-chat", "license_incompatibility") in f


def test_analyzer_flagged_source_and_missing_provenance(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "rag_app"))
    f = _finding_set(bom)
    assert ("model:sketchy-hub/uncensored-llm", "flagged_source") in f
    assert ("model:sketchy-hub/uncensored-llm", "missing_provenance") in f
    assert ("model:opencorp/minilm-embed", "unpinned") in f


def test_analyzer_restrictive_license(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "vision_pipeline"))
    f = _finding_set(bom)
    assert ("model:visionlab/segmenter-v2", "restrictive_license") in f
    assert ("dataset:opencorp/streetscapes", "restrictive_license") in f


def test_every_finding_is_explainable(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "finetune_stack"))
    for finding in bom.findings:
        assert bom.by_id(finding.component_id) is not None
        assert finding.rule_id and finding.recommendation
        assert finding.evidence  # cites a rule/term/source
