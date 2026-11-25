"""Component discovery: find the AI components a project is made of.

Discovery is deliberately signal-oriented and pluggable: each kind of surface
form (requirements, configs, code calls, notebooks, download scripts, local
weight artifacts) has its own detector, and the breadth of detectors is what
determines how complete the resulting bill of materials can be.
"""

from .discovery import discover_project, DISCOVERY_SIGNALS  # noqa: F401
