"""Render synthetic project specs into realistic projects + ground truth.

For each :class:`~provenant.data.specs.ProjectSpec` this writes:

* the project files (``requirements.txt``, configs, scripts, notebooks and
  zero-information placeholder artifacts whose *names* carry the signal);
* ``provenant_fixtures.yaml`` — a cached-metadata record for every resolvable
  component, so the resolver runs fully offline and deterministically;
* ``ground_truth.json`` — the gold component set, lineage edges and expected
  license findings the pipeline is scored against.

Determinism: all content is a pure function of the specs and ``seed`` (which
only perturbs synthetic revision hashes), so re-running ``make data`` with the
same seed reproduces byte-identical projects.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

import yaml

from ..model import component_id, ComponentType
from .specs import all_specs, ProjectSpec, CompSpec, Surface
from ..resolve.status import classify_provenance


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _synthetic_hash(name: str, version: Optional[str], seed: int) -> str:
    raw = f"{name}@{version or 'default'}:{seed}".encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:40]


def _ref_value(name: str, revision: Optional[str]) -> str:
    return f"{name}@{revision}" if revision else name


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# --------------------------------------------------------------------------- #
# Per-surface rendering buffers
# --------------------------------------------------------------------------- #
_CODE_HEADER = (
    '"""Generated training/inference script (synthetic project).\n'
    "No model weights or datasets are distributed; references are identifiers only.\n"
    '"""\n'
    "from transformers import AutoModelForCausalLM, AutoModelForImageSegmentation\n"
    "from datasets import load_dataset\n"
    "from sentence_transformers import SentenceTransformer\n"
    "import onnxruntime as ort\n\n\n"
    "def build():\n"
)

_LOCAL_PLACEHOLDER = (
    "PLACEHOLDER ARTIFACT\n"
    "This file contains no model weights. Provenant references components by\n"
    "identifier and content hash only and redistributes no weights or datasets.\n"
    "component: {name}\n"
)


def _code_line(api: Optional[str], name: str, revision: Optional[str]) -> str:
    if api == "load_dataset":
        return f'    ds = load_dataset("{name}")'
    if api == "SentenceTransformer":
        return f'    embed = SentenceTransformer("{name}")'
    if api == "onnxruntime.InferenceSession":
        return f'    sess = ort.InferenceSession("{name}")'
    # default: a model from_pretrained call
    cls = api or "AutoModelForCausalLM"
    if revision:
        return f'    model = {cls}.from_pretrained("{name}", revision="{revision}")'
    return f'    model = {cls}.from_pretrained("{name}")'


def _notebook(source_lines: list[str]) -> dict:
    cell_src = ["import_cell = True\n"]
    cell_src += [ln.strip() + "\n" for ln in source_lines]
    return {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from datasets import load_dataset\n",
                    "from transformers import AutoModel\n",
                ]
                + [ln.strip() + "\n" for ln in source_lines],
            }
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


# --------------------------------------------------------------------------- #
# Ground truth
# --------------------------------------------------------------------------- #
def _ground_truth(spec: ProjectSpec) -> dict:
    comps = []
    rels = []
    findings = []
    for c in spec.components:
        status = classify_provenance(c.license, c.source_kind, c.resolvable)
        comps.append(
            {
                "id": component_id(c.type, c.name),
                "type": c.type,
                "name": c.name,
                "version": c.version,
                "license": c.license,
                "source_kind": c.source_kind,
                "provenance_status": status,
                "file_present": bool(c.appears),
            }
        )
        if c.finetuned_from:
            rels.append(
                {"src": c.name, "dst": c.finetuned_from, "rel_type": "finetuned_from"}
            )
        for ds in c.trained_on:
            rels.append({"src": c.name, "dst": ds, "rel_type": "trained_on"})
        for cat in c.expected_findings:
            findings.append({"component_id": component_id(c.type, c.name), "category": cat})
    return {
        "project": {"name": spec.name, "kind": spec.kind},
        "components": comps,
        "relationships": rels,
        "expected_findings": findings,
    }


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _fixture_record(c: CompSpec, seed: int) -> dict:
    rec = {
        "key": f"{c.type}:{c.name}",
        "type": c.type,
        "name": c.name,
        "source_kind": c.source_kind,
        "license": c.license,
        "publisher": c.publisher,
        "publish_date": c.publish_date,
        "card_summary": c.card_summary,
    }
    if c.source_url:
        rec["source_url"] = c.source_url
    if c.version:
        rec["revisions"] = {c.version: _synthetic_hash(c.name, c.version, seed)}
        rec["default_revision"] = c.version
    # Card-based lineage signals: only present when the project files do NOT
    # already carry them, so card-based reconstruction is genuinely exercised.
    if c.lineage_from_card:
        card = {}
        if c.finetuned_from:
            card["base_model"] = c.finetuned_from
        if c.trained_on:
            card["datasets"] = list(c.trained_on)
        if card:
            rec["card"] = card
    return rec


# --------------------------------------------------------------------------- #
# Project rendering
# --------------------------------------------------------------------------- #
def render_project(spec: ProjectSpec, base_out: str, seed: int = 7) -> str:
    sub = "synthetic" if spec.kind == "synthetic" else "real"
    proj_rel = os.path.join(base_out, sub, spec.name)
    proj_dir = proj_rel

    requirements: list[str] = []
    configs: dict[str, dict] = {}
    code_files: dict[str, list[str]] = {}
    shell_files: dict[str, list[str]] = {}
    notebooks: dict[str, list[str]] = {}
    local_files: list[tuple[str, str]] = []  # (path, component name)

    for c in spec.components:
        for s in c.appears:
            if s.kind == "requirement":
                requirements.append(f"{c.name}=={s.revision}")
            elif s.kind == "config":
                cfg = configs.setdefault(s.file, {})
                # A URL-sourced component is referenced in configs by its URL,
                # the way a real project pins an off-hub download.
                if c.source_kind == "url" and c.source_url:
                    value = c.source_url
                else:
                    value = _ref_value(c.name, s.revision)
                if s.key == "datasets":
                    cfg.setdefault("datasets", [])
                    cfg["datasets"].append(value)
                else:
                    cfg[s.key] = value
            elif s.kind == "code":
                code_files.setdefault(s.file, []).append(
                    _code_line(s.api, c.name, s.revision)
                )
            elif s.kind == "notebook":
                notebooks.setdefault(s.file, []).append(
                    _code_line(s.api, c.name, s.revision).strip()
                )
            elif s.kind == "path":
                # A framework-specific loader path that generic discovery does
                # not recognise (an intentional, measured blind spot).
                code_files.setdefault(s.file, []).append(
                    f'    loader = {s.api or "ImageFolder"}("{c.name}")'
                )
            elif s.kind == "shell":
                url = c.source_url or ""
                out = f"models/{os.path.basename(c.name)}"
                shell_files.setdefault(s.file, []).append(
                    f'wget "{url}" -O "{out}"'
                )
            elif s.kind == "local":
                local_files.append((s.file, c.name))

    # --- write files ------------------------------------------------------- #
    all_reqs = sorted(set(requirements) | set(spec.noise_requirements))
    if all_reqs:
        header = "# Synthetic project dependencies.\n"
        _write(os.path.join(proj_dir, "requirements.txt"), header + "\n".join(all_reqs) + "\n")

    for fpath, cfg in configs.items():
        _write(
            os.path.join(proj_dir, fpath),
            "# Synthetic training/inference config.\n" + yaml.safe_dump(cfg, sort_keys=True),
        )

    for fpath, lines in code_files.items():
        body = _CODE_HEADER + "\n".join(lines) + "\n    return model\n"
        _write(os.path.join(proj_dir, fpath), body)

    for fpath, lines in shell_files.items():
        body = "#!/usr/bin/env bash\n# Synthetic download script.\nset -euo pipefail\n" + "\n".join(lines) + "\n"
        _write(os.path.join(proj_dir, fpath), body)

    for fpath, lines in notebooks.items():
        _write(os.path.join(proj_dir, fpath), json.dumps(_notebook(lines), indent=1) + "\n")

    for fpath, name in local_files:
        _write(os.path.join(proj_dir, fpath), _LOCAL_PLACEHOLDER.format(name=name))

    # --- fixtures ---------------------------------------------------------- #
    records = [_fixture_record(c, seed) for c in spec.components if c.resolvable]
    _write(
        os.path.join(proj_dir, "provenant_fixtures.yaml"),
        "# Cached, point-in-time metadata for this project's components.\n"
        "# Offline resolution source; no weights or datasets are included.\n"
        + yaml.safe_dump({"components": records}, sort_keys=False),
    )

    # --- ground truth ------------------------------------------------------ #
    gt = _ground_truth(spec)
    with open(os.path.join(proj_dir, "ground_truth.json"), "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2)
        fh.write("\n")

    # --- a short README for the synthetic project -------------------------- #
    _write(
        os.path.join(proj_dir, "README.md"),
        f"# Synthetic project: {spec.name}\n\n{spec.description}\n\n"
        "Generated by Provenant's synthetic project generator. All identifiers are\n"
        "invented; no model weights or datasets are distributed. `ground_truth.json`\n"
        "holds the gold component set, lineage edges and expected findings used to\n"
        "score the pipeline.\n",
    )
    return proj_dir


def generate(base_out: str = "examples", seed: int = 7) -> list[str]:
    """Generate every synthetic project under ``<base_out>/synthetic/``."""
    paths = []
    for spec in all_specs():
        paths.append(render_project(spec, base_out, seed=seed))
    return paths


if __name__ == "__main__":  # pragma: no cover
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "examples"
    for p in generate(out):
        print("generated", p)
