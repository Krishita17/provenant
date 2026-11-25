"""Signal-oriented discovery of models, datasets and frameworks in a project."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Optional
from urllib.parse import urlparse

import yaml

from ..model import (
    BOM,
    Component,
    ComponentType,
    Evidence,
    SourceKind,
    component_id,
)

# --------------------------------------------------------------------------- #
# Recognised signals
# --------------------------------------------------------------------------- #
MODEL_ARTIFACT_EXTS = {
    ".safetensors", ".gguf", ".ggml", ".onnx", ".pt", ".pth",
    ".h5", ".pb", ".tflite", ".ckpt", ".bin",
}
MODEL_CONFIG_KEYS = {
    "base_model", "model", "model_name", "model_name_or_path",
    "pretrained_model_name_or_path", "embedding_model", "encoder",
    "segmenter", "llm", "checkpoint",
}
DATASET_CONFIG_KEYS = {
    "dataset", "datasets", "data", "train_dataset", "eval_dataset",
    "validation_dataset", "dataset_name",
}
FRAMEWORK_WHITELIST = {
    # Libraries that bind AI components (not every pip dependency is reported).
    "transformers", "torch", "tensorflow", "jax", "flax", "datasets",
    "sentence-transformers", "onnxruntime", "onnx", "peft", "accelerate",
    "diffusers", "langchain", "llama-index", "faiss-cpu", "faiss-gpu",
    "vllm", "ctransformers", "timm", "spacy", "keras",
}

#: Human-readable catalogue of what discovery looks for (surfaced in the README).
DISCOVERY_SIGNALS = {
    "requirements": "framework pins in requirements.txt / pyproject",
    "config": "model/dataset fields in YAML/JSON configs",
    "code": "from_pretrained / load_dataset / SentenceTransformer calls",
    "notebook": "the same calls inside .ipynb cells",
    "shell": "weight downloads in .sh scripts",
    "local_artifact": "weight files by extension (.safetensors/.gguf/.onnx/...)",
}

# Files that are Provenant's own scaffolding, not project content.
_SKIP_FILES = {"provenant_fixtures.yaml", "ground_truth.json"}
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".work", "node_modules"}

_FROM_PRETRAINED = re.compile(
    r"(\w+)\.from_pretrained\(\s*['\"]([^'\"]+)['\"]"
    r"(?:[^)]*?revision\s*=\s*['\"]([^'\"]+)['\"])?",
)
_LOAD_DATASET = re.compile(r"load_dataset\(\s*['\"]([^'\"]+)['\"]")
_SENTENCE_TF = re.compile(r"SentenceTransformer\(\s*['\"]([^'\"]+)['\"]")
_INFERENCE_SESSION = re.compile(r"InferenceSession\(\s*['\"]([^'\"]+)['\"]")
_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:==|>=|<=|~=|>)?\s*([0-9][0-9A-Za-z.\-]*)?")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _rel(project_dir: str, path: str) -> str:
    return os.path.relpath(path, project_dir).replace(os.sep, "/")


def _split_revision(ref: str) -> tuple[str, Optional[str]]:
    """Split ``name@revision`` into ``(name, revision)``."""
    if "@" in ref and not ref.startswith("http"):
        name, _, rev = ref.rpartition("@")
        return name, rev or None
    return ref, None


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _name_from_url(url: str) -> tuple[str, str]:
    """Derive a stable ``second-level/stem`` name and the host from a URL."""
    parsed = urlparse(url)
    host = parsed.netloc
    labels = host.split(".")
    sld = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "unknown")
    stem = os.path.splitext(os.path.basename(parsed.path))[0] or "artifact"
    return f"{sld}/{stem}", host


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:40]


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
def _add_model(bom: BOM, name: str, version, source_kind, ev: Evidence, source=None):
    comp = Component(
        id=component_id(ComponentType.MODEL, name),
        type=ComponentType.MODEL,
        name=name,
        version=version,
        source=source,
        source_kind=source_kind,
        evidence=[ev],
    )
    return bom.add_component(comp)


def _add_dataset(bom: BOM, name: str, version, source_kind, ev: Evidence):
    comp = Component(
        id=component_id(ComponentType.DATASET, name),
        type=ComponentType.DATASET,
        name=name,
        version=version,
        source_kind=source_kind,
        evidence=[ev],
    )
    return bom.add_component(comp)


def _detect_requirements(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = _REQ_LINE.match(s)
            if not m:
                continue
            name = m.group(1).lower()
            if name not in FRAMEWORK_WHITELIST:
                continue
            version = m.group(2)
            ev = Evidence("requirements", f"pinned in {rel}", path=rel, line=i, snippet=s)
            bom.add_component(
                Component(
                    id=component_id(ComponentType.FRAMEWORK, name),
                    type=ComponentType.FRAMEWORK,
                    name=name,
                    version=version,
                    source_kind=SourceKind.REGISTRY,
                    source=f"https://pypi.org/project/{name}/",
                    evidence=[ev],
                )
            )


def _detect_config(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    try:
        with open(path, encoding="utf-8") as fh:
            if path.endswith(".json"):
                data = json.load(fh)
            else:
                data = yaml.safe_load(fh)
    except Exception:
        return
    if not isinstance(data, dict):
        return

    def handle(key: str, value):
        if isinstance(value, list):
            for v in value:
                handle(key, v)
            return
        if not isinstance(value, str) or not value.strip():
            return
        ev = Evidence("config", f"{key} in {rel}", path=rel, snippet=f"{key}: {value}")
        if key in MODEL_CONFIG_KEYS:
            if _is_url(value):
                name, host = _name_from_url(value)
                _add_model(bom, name, None, SourceKind.URL, ev, source=value)
            else:
                ref, rev = _split_revision(value)
                _add_model(bom, ref, rev, SourceKind.HUGGINGFACE, ev)
        elif key in DATASET_CONFIG_KEYS:
            if _is_url(value):
                name, host = _name_from_url(value)
                _add_dataset(bom, name, None, SourceKind.URL, ev)
            else:
                ref, rev = _split_revision(value)
                _add_dataset(bom, ref, rev, SourceKind.HUGGINGFACE, ev)

    for key, value in data.items():
        if key in MODEL_CONFIG_KEYS or key in DATASET_CONFIG_KEYS:
            handle(key, value)


def _scan_code_text(bom: BOM, rel: str, text: str) -> None:
    for m in _FROM_PRETRAINED.finditer(text):
        name, rev = m.group(2), m.group(3)
        if _is_url(name):
            nm, _ = _name_from_url(name)
            _add_model(bom, nm, None, SourceKind.URL, Evidence("code", f"from_pretrained in {rel}", path=rel, snippet=m.group(0)[:120]), source=name)
        else:
            _add_model(bom, name, rev, SourceKind.HUGGINGFACE,
                       Evidence("code", f"from_pretrained in {rel}", path=rel, snippet=m.group(0)[:120]))
    for m in _SENTENCE_TF.finditer(text):
        _add_model(bom, m.group(1), None, SourceKind.HUGGINGFACE,
                   Evidence("code", f"SentenceTransformer in {rel}", path=rel, snippet=m.group(0)[:120]))
    for m in _LOAD_DATASET.finditer(text):
        _add_dataset(bom, m.group(1), None, SourceKind.HUGGINGFACE,
                     Evidence("code", f"load_dataset in {rel}", path=rel, snippet=m.group(0)[:120]))
    for m in _INFERENCE_SESSION.finditer(text):
        name = m.group(1)
        _add_model(bom, name, None, SourceKind.LOCAL,
                   Evidence("code", f"InferenceSession in {rel}", path=rel, snippet=m.group(0)[:120]))


def _detect_python(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    with open(path, encoding="utf-8") as fh:
        _scan_code_text(bom, rel, fh.read())


def _detect_notebook(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    try:
        with open(path, encoding="utf-8") as fh:
            nb = json.load(fh)
    except Exception:
        return
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        text = "".join(src) if isinstance(src, list) else str(src)
        _scan_code_text(bom, rel, text)


def _detect_shell(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for m in re.finditer(r"https?://[^\s'\"]+", text):
        url = m.group(0)
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext not in MODEL_ARTIFACT_EXTS:
            continue
        name, host = _name_from_url(url)
        _add_model(bom, name, None, SourceKind.URL,
                   Evidence("shell", f"download in {rel}", path=rel, snippet=url), source=url)


def _detect_local_artifact(bom: BOM, project_dir: str, path: str) -> None:
    rel = _rel(project_dir, path)
    ev = Evidence("local_artifact", f"weight file {rel}", path=rel)
    file_hash = _sha256_file(path)
    # Reconcile with an already-discovered named model whose last path segment
    # matches this artifact's stem (same model, referenced two ways).
    stem = os.path.splitext(os.path.basename(rel))[0]
    for comp in bom.components:
        if comp.type != ComponentType.MODEL:
            continue
        last = comp.name.rsplit("/", 1)[-1]
        if last == stem:
            comp.evidence.append(ev)
            comp.hash = comp.hash or file_hash
            comp.extra.setdefault("local_path", rel)
            return
    # Otherwise a standalone local model named by its project-relative path.
    comp = Component(
        id=component_id(ComponentType.MODEL, rel),
        type=ComponentType.MODEL,
        name=rel,
        source_kind=SourceKind.LOCAL,
        hash=file_hash,
        evidence=[ev],
    )
    comp.extra["local_path"] = rel
    bom.add_component(comp)


# --------------------------------------------------------------------------- #
# Walk
# --------------------------------------------------------------------------- #
def discover_project(project_dir: str) -> BOM:
    """Discover every AI component referenced in ``project_dir``."""
    project_dir = os.path.abspath(project_dir)
    bom = BOM(project={"name": os.path.basename(project_dir.rstrip("/")), "path": project_dir})

    config_paths: list[str] = []
    code_paths: list[str] = []
    notebook_paths: list[str] = []
    shell_paths: list[str] = []
    artifact_paths: list[str] = []

    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if fname in _SKIP_FILES:
                continue
            full = os.path.join(root, fname)
            lower = fname.lower()
            ext = os.path.splitext(lower)[1]
            if lower in ("requirements.txt",) or lower.endswith("requirements.txt"):
                _detect_requirements(bom, project_dir, full)
            elif ext in (".yaml", ".yml", ".json") and lower != "ground_truth.json":
                config_paths.append(full)
            elif ext == ".py":
                code_paths.append(full)
            elif ext == ".ipynb":
                notebook_paths.append(full)
            elif ext == ".sh":
                shell_paths.append(full)
            if ext in MODEL_ARTIFACT_EXTS:
                artifact_paths.append(full)

    # Order matters: named references first, then reconcile local artifacts.
    for p in sorted(config_paths):
        _detect_config(bom, project_dir, p)
    for p in sorted(code_paths):
        _detect_python(bom, project_dir, p)
    for p in sorted(notebook_paths):
        _detect_notebook(bom, project_dir, p)
    for p in sorted(shell_paths):
        _detect_shell(bom, project_dir, p)
    for p in sorted(artifact_paths):
        _detect_local_artifact(bom, project_dir, p)

    # Deterministic ordering of the output.
    bom.components.sort(key=lambda c: (c.type, c.name))
    return bom
