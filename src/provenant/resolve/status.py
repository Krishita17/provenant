"""Provenance-status classification.

Shared by the resolver (which classifies real resolution results) and the data
generator (which labels ground truth the same way), so the tool is scored
against exactly the rule it applies. ``unknown`` is a first-class outcome:
unresolvable provenance is reported here, never guessed upstream.
"""

from __future__ import annotations

from typing import Optional

from ..model import ProvenanceStatus

#: Source kinds that represent an external origin we can point a reviewer at.
EXTERNAL_ORIGINS = {"huggingface", "github", "registry", "url"}


def classify_provenance(
    license: Optional[str],
    source_kind: Optional[str],
    record_found: bool,
) -> str:
    """Classify how completely a component's origin and terms are known.

    Parameters
    ----------
    license:
        The resolved license identifier, or ``None`` if none could be resolved.
    source_kind:
        The component's source kind (e.g. ``huggingface``, ``local``).
    record_found:
        Whether a metadata record (fixture or hub) was found for the component.

    Returns
    -------
    One of :class:`~provenant.model.ProvenanceStatus` ``RESOLVED`` / ``PARTIAL``
    / ``UNKNOWN``.
    """
    external = source_kind in EXTERNAL_ORIGINS
    if license and (record_found or external):
        return ProvenanceStatus.RESOLVED
    if license or record_found or external:
        return ProvenanceStatus.PARTIAL
    return ProvenanceStatus.UNKNOWN
