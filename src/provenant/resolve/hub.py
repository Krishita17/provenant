"""Optional, read-only online metadata enrichment.

This module is the *only* place Provenant would reach the network, and nothing
in the default pipeline or any ``make`` target imports it. It is a thin,
clearly-bounded extension point: given components the offline resolver could not
resolve, it may query public model/dataset hub metadata endpoints (read-only)
and cache the results back into the local fixture store.

It is intentionally inert unless a caller passes ``online=True`` *and* opts in
here, so the project stays fully reproducible offline. The default
implementation does nothing and documents what a live resolver would populate.
"""

from __future__ import annotations

from ..model import BOM, Evidence


def enrich_online(bom: BOM) -> BOM:
    """Enrich unresolved components from public hub metadata (opt-in, read-only).

    The reference build ships this as a no-op so that evaluation is fully
    offline and deterministic. A deployment that enables online resolution would
    here, for each still-unknown component:

    * issue a read-only request to the component's hub metadata endpoint;
    * populate ``license``, ``publisher``, ``publish_date``, ``card_summary``
      and revision hashes from the response;
    * cache the record into the local fixture store for reproducibility;
    * re-run :func:`provenant.resolve.status.classify_provenance`.

    It never downloads weights or datasets and never sends project-identifying
    data in request parameters.
    """
    for comp in bom.components:
        if comp.license is None and comp.source_kind in ("huggingface", "github"):
            comp.evidence.append(
                Evidence(
                    "resolver",
                    "online resolution available but disabled in this build; "
                    "component left as reported (not guessed)",
                )
            )
    return bom
