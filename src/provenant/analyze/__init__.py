"""Risk & compliance analysis over the assembled components and lineage.

Every finding is explainable: it names the component and the rule/term it was
derived from, and (for cross-lineage conflicts) the related component. License
findings are informational governance signals, never a legal determination.
"""

from .analyzer import analyze_bom, RULES  # noqa: F401
