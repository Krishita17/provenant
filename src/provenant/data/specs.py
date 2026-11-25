"""Declarative specifications of the synthetic ML projects.

Each :class:`ProjectSpec` is rendered by :mod:`provenant.data.generate` into a
realistic project *and* is the ground truth that project is scored against, so
the two can never drift. All identifiers here are invented (``acme/*``,
``opencorp/*``, ``labA/*`` …) — no real organization's model or dataset is named
in the synthetic set, and no weights or data are shipped.

Surface forms
-------------
A component "appears" in a project through one or more surface forms, mirroring
how real projects reference AI components:

``requirement``   a line in ``requirements.txt`` (frameworks)
``config``        a field in a YAML/JSON config (``base_model``, ``model_name_or_path``, ``datasets``)
``code``          a ``from_pretrained`` / ``load_dataset`` call in a ``.py`` file
``notebook``      the same, inside a ``.ipynb`` cell
``shell``         a download line in a ``.sh`` script
``local``         a placeholder weight artifact (``.safetensors`` / ``.onnx`` / ``.gguf`` …)

Provenance gaps
---------------
A component with ``resolvable=False`` gets **no** metadata-fixture record, so the
resolver must honestly report it as ``unknown`` — the generator plants genuine
provenance gaps to measure that the tool reports them rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Surface:
    kind: str                       # requirement|config|code|notebook|shell|local
    file: str                       # project-relative target file
    key: Optional[str] = None       # config field name, for kind == "config"
    revision: Optional[str] = None  # pinned revision, when the surface pins one
    api: Optional[str] = None       # e.g. "AutoModelForCausalLM", "load_dataset"


@dataclass
class CompSpec:
    type: str                                    # model|dataset|framework
    name: str
    appears: list[Surface]
    version: Optional[str] = None
    license: Optional[str] = None                # true license; None == genuine gap
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    source_kind: str = "huggingface"
    source_url: Optional[str] = None
    card_summary: Optional[str] = None
    resolvable: bool = True                      # False => no fixture record (gap)
    finetuned_from: Optional[str] = None         # parent model name
    trained_on: list[str] = field(default_factory=list)  # dataset names
    lineage_from_card: bool = False              # lineage signals live in the card,
    #: not in the project files (exercises card-based reconstruction)
    expected_findings: list[str] = field(default_factory=list)  # categories, for scoring


@dataclass
class ProjectSpec:
    name: str
    description: str
    components: list[CompSpec]
    kind: str = "synthetic"  # or "real"
    #: Non-AI dependencies written to requirements.txt as realistic noise that a
    #: selective discovery pass should correctly *ignore* (precision check).
    noise_requirements: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Framework shorthands
# --------------------------------------------------------------------------- #
def _fw(name: str, version: str, license: str, publisher: str, file: str = "requirements.txt") -> CompSpec:
    return CompSpec(
        type="framework",
        name=name,
        version=version,
        license=license,
        publisher=publisher,
        source_kind="registry",
        source_url=f"https://pypi.org/project/{name}/",
        publish_date="2024-01-15",
        card_summary=f"{name} {version} (PyPI).",
        appears=[Surface(kind="requirement", file=file, revision=version)],
    )


# --------------------------------------------------------------------------- #
# Project 1 — finetune_stack: full lineage with one non-commercial conflict
# --------------------------------------------------------------------------- #
def _finetune_stack() -> ProjectSpec:
    return ProjectSpec(
        name="finetune_stack",
        description="A causal-LM fine-tune declaring its base model and training "
        "datasets, one of which is non-commercial.",
        components=[
            _fw("transformers", "4.38.0", "apache-2.0", "Hugging Face"),
            _fw("torch", "2.2.0", "bsd-3-clause", "Meta"),
            _fw("datasets", "2.18.0", "apache-2.0", "Hugging Face"),
            CompSpec(
                type="model", name="acme/base-lm-1b", version="v1.0",
                license="apache-2.0", publisher="acme", publish_date="2023-09-01",
                source_url="https://huggingface.co/acme/base-lm-1b",
                card_summary="A 1B-parameter base language model.",
                appears=[
                    Surface("config", "config/train.yaml", key="base_model", revision="v1.0"),
                    Surface("code", "train.py", api="AutoModelForCausalLM", revision="v1.0"),
                ],
            ),
            CompSpec(
                type="dataset", name="research-lab/dialogs-nc", version="v3",
                license="cc-by-nc-4.0", publisher="research-lab", publish_date="2023-05-10",
                source_url="https://huggingface.co/datasets/research-lab/dialogs-nc",
                card_summary="Dialogue corpus released for non-commercial research use.",
                appears=[
                    Surface("config", "config/train.yaml", key="datasets"),
                    Surface("code", "train.py", api="load_dataset"),
                ],
                expected_findings=["non_commercial"],
            ),
            CompSpec(
                type="dataset", name="opencorp/instruct-mini", version="v2",
                license="apache-2.0", publisher="opencorp", publish_date="2023-11-20",
                source_url="https://huggingface.co/datasets/opencorp/instruct-mini",
                card_summary="Small permissive instruction-tuning dataset.",
                appears=[
                    Surface("config", "config/train.yaml", key="datasets"),
                    Surface("code", "train.py", api="load_dataset"),
                    Surface("notebook", "notebooks/explore.ipynb", api="load_dataset"),
                ],
            ),
            CompSpec(
                type="model", name="myorg/base-lm-1b-chat", version="v1.0",
                license="apache-2.0", publisher="myorg", publish_date="2024-02-01",
                source_kind="local",
                source_url=None,
                card_summary="Chat fine-tune of acme/base-lm-1b.",
                finetuned_from="acme/base-lm-1b",
                trained_on=["research-lab/dialogs-nc", "opencorp/instruct-mini"],
                appears=[
                    Surface("config", "config/train.yaml", key="model_name_or_path"),
                    Surface("local", "models/base-lm-1b-chat.safetensors"),
                ],
                # The fine-tune is Apache-licensed but trained on a non-commercial
                # dataset -> a cross-lineage incompatibility.
                expected_findings=["license_incompatibility"],
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Project 2 — rag_app: unpinned component, flagged source, genuine gap
# --------------------------------------------------------------------------- #
def _rag_app() -> ProjectSpec:
    return ProjectSpec(
        name="rag_app",
        description="A retrieval-augmented app wiring an embedding model and an "
        "LLM pulled from an untrusted host.",
        components=[
            _fw("langchain", "0.1.0", "mit", "LangChain"),
            _fw("sentence-transformers", "2.5.0", "apache-2.0", "UKP Lab"),
            _fw("faiss-cpu", "1.8.0", "mit", "Meta"),
            CompSpec(
                type="model", name="opencorp/minilm-embed",
                version=None,  # deliberately unpinned
                license="apache-2.0", publisher="opencorp", publish_date="2023-08-01",
                source_url="https://huggingface.co/opencorp/minilm-embed",
                card_summary="Small sentence-embedding model.",
                appears=[
                    Surface("config", "config/rag.yaml", key="embedding_model"),
                    Surface("code", "app.py", api="SentenceTransformer"),
                ],
                expected_findings=["unpinned"],
            ),
            CompSpec(
                type="dataset", name="opencorp/faq-corpus", version="v1",
                license="cc-by-4.0", publisher="opencorp", publish_date="2023-10-05",
                source_url="https://huggingface.co/datasets/opencorp/faq-corpus",
                card_summary="FAQ pairs for retrieval demos.",
                appears=[Surface("config", "config/rag.yaml", key="datasets")],
            ),
            CompSpec(
                type="model", name="sketchy-hub/uncensored-llm",
                version=None,
                license=None,  # unresolvable -> genuine provenance gap
                resolvable=False,
                source_kind="url",
                source_url="https://models.sketchy-hub.example/uncensored-llm.gguf",
                appears=[
                    Surface("config", "config/rag.yaml", key="llm"),
                    Surface("shell", "scripts/download_llm.sh"),
                ],
                expected_findings=["flagged_source", "missing_provenance"],
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Project 3 — vision_pipeline: local artifact gap, restrictive + share-alike
# --------------------------------------------------------------------------- #
def _vision_pipeline() -> ProjectSpec:
    return ProjectSpec(
        name="vision_pipeline",
        description="A vision inference pipeline mixing a local ONNX detector with "
        "a hub segmenter under a restrictive license.",
        noise_requirements=["numpy==1.26.0", "opencv-python==4.9.0"],
        components=[
            _fw("onnxruntime", "1.17.0", "mit", "Microsoft"),
            _fw("onnx", "1.15.0", "apache-2.0", "ONNX"),
            CompSpec(
                # A raw local dataset referenced only by a framework-specific
                # loader path -> a GENUINE discovery blind spot: no generic
                # detector matches it, so it is a measured hole in the BOM.
                type="dataset", name="data/streetscapes_raw",
                version=None, license=None, resolvable=False,
                source_kind="local",
                appears=[Surface("path", "infer.py", api="ImageFolder")],
            ),
            CompSpec(
                type="model", name="models/detector.onnx",
                version=None, license=None, resolvable=False,
                source_kind="local",
                appears=[
                    Surface("local", "models/detector.onnx"),
                    Surface("code", "infer.py", api="onnxruntime.InferenceSession"),
                ],
                expected_findings=["missing_provenance"],
            ),
            CompSpec(
                type="model", name="visionlab/segmenter-v2", version="v2.1",
                license="openrail", publisher="visionlab", publish_date="2023-12-01",
                source_url="https://huggingface.co/visionlab/segmenter-v2",
                card_summary="Street-scene segmenter; RAIL acceptable-use terms apply.",
                finetuned_from="visionlab/segmenter-base",
                trained_on=["opencorp/streetscapes"],
                lineage_from_card=True,  # base + data declared in the card, not configs
                appears=[
                    Surface("config", "config/pipeline.yaml", key="segmenter", revision="v2.1"),
                    Surface("code", "infer.py", api="AutoModelForImageSegmentation", revision="v2.1"),
                    Surface("local", "models/segmenter-v2.safetensors"),
                ],
                expected_findings=["restrictive_license"],
            ),
            CompSpec(
                type="model", name="visionlab/segmenter-base", version="v1.0",
                license="apache-2.0", publisher="visionlab", publish_date="2023-06-01",
                source_url="https://huggingface.co/visionlab/segmenter-base",
                card_summary="Base segmentation backbone.",
                # Discovered transitively from segmenter-v2's card.
                appears=[],
            ),
            CompSpec(
                type="dataset", name="opencorp/streetscapes", version="v1",
                license="cc-by-sa-4.0", publisher="opencorp", publish_date="2023-07-15",
                source_url="https://huggingface.co/datasets/opencorp/streetscapes",
                card_summary="Street scene imagery, share-alike licensed.",
                appears=[Surface("config", "config/pipeline.yaml", key="datasets")],
                expected_findings=["restrictive_license"],  # share-alike copyleft
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Project 4 — multihop_finetune: 2-hop ancestry + inherited NC conflict
# --------------------------------------------------------------------------- #
def _multihop_finetune() -> ProjectSpec:
    return ProjectSpec(
        name="multihop_finetune",
        description="A fine-tune of a fine-tune, where a non-commercial dataset "
        "high in the chain creates an inherited incompatibility.",
        components=[
            _fw("transformers", "4.38.0", "apache-2.0", "Hugging Face"),
            _fw("peft", "0.9.0", "apache-2.0", "Hugging Face"),
            CompSpec(
                type="model", name="acme/foundation-7b", version="v1.0",
                license="apache-2.0", publisher="acme", publish_date="2023-07-01",
                source_url="https://huggingface.co/acme/foundation-7b",
                card_summary="7B foundation model.",
                appears=[],  # discovered transitively from the SFT model's card
            ),
            CompSpec(
                type="model", name="labA/foundation-7b-sft", version="v2.0",
                license="apache-2.0", publisher="labA", publish_date="2023-10-01",
                source_url="https://huggingface.co/labA/foundation-7b-sft",
                card_summary="Supervised fine-tune of acme/foundation-7b.",
                finetuned_from="acme/foundation-7b",
                trained_on=["labA/sft-mix"],
                lineage_from_card=True,
                appears=[
                    Surface("config", "config/finetune.yaml", key="base_model", revision="v2.0"),
                    Surface("code", "train.py", api="AutoModelForCausalLM", revision="v2.0"),
                ],
            ),
            CompSpec(
                type="dataset", name="labA/sft-mix", version="v1",
                license="apache-2.0", publisher="labA", publish_date="2023-09-10",
                source_url="https://huggingface.co/datasets/labA/sft-mix",
                card_summary="Permissive SFT mixture.",
                appears=[],  # declared in labA/foundation-7b-sft's card
            ),
            CompSpec(
                type="dataset", name="labB/dialogs-nc", version="v1",
                license="cc-by-nc-4.0", publisher="labB", publish_date="2024-01-05",
                source_url="https://huggingface.co/datasets/labB/dialogs-nc",
                card_summary="Dialogue data, non-commercial license.",
                appears=[
                    Surface("config", "config/finetune.yaml", key="datasets"),
                    Surface("code", "train.py", api="load_dataset"),
                ],
                expected_findings=["non_commercial"],
            ),
            CompSpec(
                type="model", name="labB/foundation-7b-chat", version="v1.0",
                license="apache-2.0", publisher="labB", publish_date="2024-02-15",
                source_kind="local",
                card_summary="Chat fine-tune of labA/foundation-7b-sft.",
                finetuned_from="labA/foundation-7b-sft",
                trained_on=["labB/dialogs-nc"],
                appears=[
                    Surface("config", "config/finetune.yaml", key="model_name_or_path"),
                    Surface("local", "models/foundation-7b-chat.safetensors"),
                ],
                # Apache-licensed, but its lineage pulls in non-commercial data.
                expected_findings=["license_incompatibility"],
            ),
        ],
    )


def all_specs() -> list[ProjectSpec]:
    """Return every synthetic project specification (deterministic order)."""
    return [
        _finetune_stack(),
        _rag_app(),
        _vision_pipeline(),
        _multihop_finetune(),
    ]
