"""AIBOM assembly: emit standards-aligned bills of materials.

Two documents are produced from the same resolved BOM:

* a **CycloneDX 1.6 ML-BOM** (``machine-learning-model`` / ``data`` / ``library``
  components, model cards, ``dependencies`` carrying the provenance graph, and
  findings as annotations); and
* an **SPDX 2.3 document with AI-profile annotations** (packages + typed
  relationships for lineage).

Generated documents validate against the bundled profile schemas
(``schemas/*.json``) — self-contained subsets of the upstream CycloneDX 1.6 and
SPDX 2.3 schemas covering exactly the fields Provenant emits, so validation runs
fully offline.
"""

from .assembler import (  # noqa: F401
    assemble_cyclonedx,
    assemble_spdx,
    validate_cyclonedx,
    validate_spdx,
    FIXED_TIMESTAMP,
)
