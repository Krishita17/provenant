"""Lineage reconstruction — the core of Provenant.

Rebuilds a directed provenance graph (fine-tune -> base model -> training
datasets) from two kinds of scattered breadcrumbs:

* **config signals** — ``base_model`` / ``model_name_or_path`` / ``datasets``
  fields in the project's own configs; and
* **card signals** — ``base_model`` / ``datasets`` declared in a resolved
  component's model/dataset card.

Card signals let the graph reach *beyond* the project's files: a referenced base
model's own card can name *its* base and data, so the reconstructor expands the
graph transitively (a fine-tune of a fine-tune of a base) and resolves each
newly-referenced parent, producing multi-hop ancestry rather than a flat list.
"""

from .reconstruct import reconstruct_lineage, provenance_subgraph  # noqa: F401
