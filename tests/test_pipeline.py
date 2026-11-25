"""End-to-end accuracy of the pipeline against ground truth."""

import os

import pytest

from provenant.evaluate import evaluate_project, run_pipeline, evaluate
from conftest import project, REPO_ROOT


def _gold(pdir):
    return os.path.join(pdir, "ground_truth.json")


def test_every_synthetic_project_scores_perfectly_on_core_metrics(synthetic_projects):
    for pdir in synthetic_projects:
        res = evaluate_project(pdir, _gold(pdir))
        assert res["lineage"]["f1"] == 1.0, f"{res['name']} lineage"
        assert res["finding"]["f1"] == 1.0, f"{res['name']} findings"
        assert res["provenance_accuracy"] == 1.0, f"{res['name']} provenance"
        assert res["unknown"]["precision"] == 1.0, f"{res['name']} unknown precision"
        assert res["cyclonedx_valid"] and res["spdx_valid"], f"{res['name']} aibom"


def test_final_component_recall_is_complete_via_lineage_expansion(synthetic_base):
    # multihop references two ancestors only via cards; expansion must recover them.
    res = evaluate_project(project(synthetic_base, "multihop_finetune"),
                           _gold(project(synthetic_base, "multihop_finetune")))
    assert res["component"]["recall"] == 1.0
    assert res["lineage"]["tp"] == 4  # chat->sft, sft->base, chat->nc, sft->mix


def test_discovery_measures_its_own_blind_spot(synthetic_base):
    # vision_pipeline plants a raw-path dataset no generic detector can see.
    res = evaluate_project(project(synthetic_base, "vision_pipeline"),
                           _gold(project(synthetic_base, "vision_pipeline")))
    assert res["discovery_recall"] < 1.0
    assert res["component"]["recall"] < 1.0


def test_unknown_provenance_is_reported_not_guessed(synthetic_base):
    bom, _ = run_pipeline(project(synthetic_base, "vision_pipeline"))
    det = bom.by_id("model:models/detector.onnx")
    assert det is not None
    assert det.license is None
    assert det.provenance_status == "unknown"


def test_real_examples_resolve_offline_and_score(tmp_path):
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)  # references/gold is repo-relative
    try:
        metrics = evaluate(["examples/real"], str(tmp_path), gold_dir="references/gold")
    finally:
        os.chdir(cwd)
    o = metrics["overall"]
    assert o["n_projects"] == 2
    assert o["lineage"]["f1"] == 1.0
    assert o["finding"]["f1"] == 1.0
    assert o["cyclonedx_valid"] == 2 and o["spdx_valid"] == 2
