"""Metadata resolution: turn bare component references into described components.

Offline, the resolver reads cached metadata fixtures (the packaged base store
plus any ``provenant_fixtures.yaml`` that travels with a project). Online is an
opt-in, read-only extension point (:mod:`provenant.resolve.hub`) that is never
required for any ``make`` target.
"""

from .resolver import resolve_bom, Resolver  # noqa: F401
from .status import classify_provenance  # noqa: F401
