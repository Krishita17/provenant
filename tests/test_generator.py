"""The synthetic generator is deterministic and ships no weights/datasets."""

import json
import os

from provenant.data.generate import generate


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_generation_is_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate(str(a), seed=7)
    generate(str(b), seed=7)
    for rel in ["synthetic/finetune_stack/ground_truth.json",
                "synthetic/finetune_stack/provenant_fixtures.yaml",
                "synthetic/multihop_finetune/config/finetune.yaml"]:
        assert _read(a / rel) == _read(b / rel)


def test_seed_changes_revision_hashes(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate(str(a), seed=7)
    generate(str(b), seed=8)
    fa = _read(a / "synthetic/finetune_stack/provenant_fixtures.yaml")
    fb = _read(b / "synthetic/finetune_stack/provenant_fixtures.yaml")
    assert fa != fb  # hashes differ with the seed


def test_no_real_weights_in_placeholders(tmp_path):
    generate(str(tmp_path), seed=7)
    for root, _dirs, files in os.walk(tmp_path):
        for f in files:
            if f.endswith((".safetensors", ".onnx", ".gguf")):
                content = _read(os.path.join(root, f))
                assert "PLACEHOLDER ARTIFACT" in content


def test_ground_truth_declares_a_provenance_gap(tmp_path):
    generate(str(tmp_path), seed=7)
    gt = json.load(open(tmp_path / "synthetic/vision_pipeline/ground_truth.json"))
    statuses = {c["name"]: c["provenance_status"] for c in gt["components"]}
    assert statuses["models/detector.onnx"] == "unknown"
