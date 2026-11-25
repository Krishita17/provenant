"""Provenant — an AI Bill of Materials (AIBOM) generator for model & dataset provenance.

Provenant walks an ML project, discovers its AI components (models, datasets and
binding frameworks), resolves their metadata and licenses, reconstructs lineage
into a provenance graph, analyzes license/provenance risk, and assembles a
standards-aligned AIBOM (CycloneDX ML-BOM / SPDX AI-profile compatible) plus a
human-readable risk report.

Author: Krishita Sanjay Choksi.

The findings this tool produces are informational and are not a legal license
determination. See ``docs/scope_and_provenance.md``.
"""

__version__ = "0.1.0"
__author__ = "Krishita Sanjay Choksi"
