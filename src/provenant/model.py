"""Core data model shared by every stage of the Provenant pipeline.

The pipeline is a sequence of pure transformations over a single in-memory
representation (:class:`BOM`) that is serialized to JSON between stages, so each
``make`` target can run independently and be inspected on disk.

Design notes
------------
* ``provenance_status`` is a first-class value with an explicit ``UNKNOWN``
  member. Unresolvable provenance is *reported*, never guessed.
* Every :class:`Component`, :class:`Relationship` and :class:`Finding` carries
  ``evidence`` — the file/line/snippet or rule that justifies it — so every
  output is explainable back to the project it was derived from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enumerated string constants (kept as plain strings for trivial JSON round-trip)
# --------------------------------------------------------------------------- #
class ComponentType:
    MODEL = "model"
    DATASET = "dataset"
    FRAMEWORK = "framework"
    ALL = (MODEL, DATASET, FRAMEWORK)


class SourceKind:
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    URL = "url"
    GITHUB = "github"
    REGISTRY = "registry"
    UNKNOWN = "unknown"


class ProvenanceStatus:
    #: source, version/hash and license all resolved
    RESOLVED = "resolved"
    #: some identifying metadata resolved, but at least one of source/license/
    #: version is missing
    PARTIAL = "partial"
    #: the component could not be resolved at all — reported, never fabricated
    UNKNOWN = "unknown"
    ALL = (RESOLVED, PARTIAL, UNKNOWN)


class RelationType:
    FINETUNED_FROM = "finetuned_from"
    TRAINED_ON = "trained_on"
    DERIVED_FROM = "derived_from"
    USES_FRAMEWORK = "uses_framework"
    ALL = (FINETUNED_FROM, TRAINED_ON, DERIVED_FROM, USES_FRAMEWORK)


class Severity:
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    #: ordering helper, most severe first
    ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


@dataclass
class Evidence:
    """Where a fact came from — the basis for explainability."""

    source: str  # e.g. "config", "model_card", "requirements.txt", "policy_kb"
    detail: str  # human-readable description of the signal
    path: Optional[str] = None  # project-relative file that carried the signal
    line: Optional[int] = None  # 1-indexed line, when known
    snippet: Optional[str] = None  # the raw text the signal was read from

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Component:
    """A single AI component: a model, dataset or binding framework."""

    id: str
    type: str
    name: str
    version: Optional[str] = None
    hash: Optional[str] = None
    source: Optional[str] = None
    source_kind: str = SourceKind.UNKNOWN
    license: Optional[str] = None          # resolved license identifier/name
    license_source: Optional[str] = None   # how the license was determined
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    card_summary: Optional[str] = None
    provenance_status: str = ProvenanceStatus.UNKNOWN
    commercial_use: Optional[bool] = None  # filled from policy KB during analysis
    evidence: list[Evidence] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Component":
        d = dict(d)
        d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
        return cls(**d)


@dataclass
class Relationship:
    """A directed provenance edge between two components."""

    src: str          # component id of the dependent (e.g. the fine-tune)
    dst: str          # component id of the parent (e.g. the base model)
    rel_type: str
    confidence: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Relationship":
        d = dict(d)
        d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
        return cls(**d)


@dataclass
class Finding:
    """A single risk/compliance finding, always tied to a component and a rule."""

    id: str
    category: str
    severity: str
    component_id: str
    rule_id: str
    message: str
    recommendation: str
    evidence: list[Evidence] = field(default_factory=list)
    related_component_id: Optional[str] = None  # for cross-lineage conflicts

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        d = dict(d)
        d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
        return cls(**d)


@dataclass
class BOM:
    """The working bill of materials carried through the whole pipeline."""

    project: dict[str, Any] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    # -- component helpers --------------------------------------------------- #
    def by_id(self, cid: str) -> Optional[Component]:
        for c in self.components:
            if c.id == cid:
                return c
        return None

    def add_component(self, comp: Component) -> Component:
        """Add a component, merging evidence if the id already exists."""
        existing = self.by_id(comp.id)
        if existing is None:
            self.components.append(comp)
            return comp
        existing.evidence.extend(comp.evidence)
        return existing

    def has_relationship(self, src: str, dst: str, rel_type: str) -> bool:
        return any(
            r.src == src and r.dst == dst and r.rel_type == rel_type
            for r in self.relationships
        )

    def add_relationship(self, rel: Relationship) -> None:
        if not self.has_relationship(rel.src, rel.dst, rel.rel_type):
            self.relationships.append(rel)

    # -- serialization ------------------------------------------------------- #
    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "components": [c.to_dict() for c in self.components],
            "relationships": [r.to_dict() for r in self.relationships],
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BOM":
        return cls(
            project=d.get("project", {}),
            components=[Component.from_dict(c) for c in d.get("components", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=False)
            fh.write("\n")

    @classmethod
    def load(cls, path: str) -> "BOM":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# --------------------------------------------------------------------------- #
# Identity helpers
# --------------------------------------------------------------------------- #
def component_id(ctype: str, name: str, version: Optional[str] = None) -> str:
    """Build a stable, human-readable component id.

    Examples
    --------
    ``model:meta-llama/Llama-2-7b@main`` or ``dataset:imdb`` (version omitted).
    """
    base = f"{ctype}:{name}"
    if version:
        return f"{base}@{version}"
    return base
