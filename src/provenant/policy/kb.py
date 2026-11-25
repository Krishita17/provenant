"""Loader and query surface for the editable policy knowledge base."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import yaml

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config")


def _config_path(name: str) -> str:
    return os.path.abspath(os.path.join(_CONFIG_DIR, name))


@dataclass
class LicenseInfo:
    id: str
    display_name: str
    cls: str                      # permissive|copyleft|non_commercial|restricted|public_domain|unknown
    commercial_use: object        # True|False|"conditional"
    share_alike: bool
    acceptable_use_restrictions: bool
    url: Optional[str] = None

    @property
    def is_non_commercial(self) -> bool:
        return self.cls == "non_commercial" or self.commercial_use is False

    @property
    def is_permissive(self) -> bool:
        return self.cls in ("permissive", "public_domain")

    @property
    def is_restrictive(self) -> bool:
        """Known, but carries obligations/restrictions beyond permissive use."""
        return (
            self.cls in ("copyleft", "restricted")
            or self.share_alike
            or self.acceptable_use_restrictions
        )

    @property
    def is_unknown_class(self) -> bool:
        return self.cls == "unknown"


class Compatibility:
    """Verdicts for combining a component license with commercial distribution."""

    OK = "compatible"
    OBLIGATION = "compatible_with_obligations"
    CONDITIONAL = "conditional"
    CONFLICT = "conflict"
    REVIEW = "needs_review"


class PolicyKB:
    def __init__(
        self,
        licenses: dict,
        defaults: dict,
        flagged_host_substrings: list[str],
        flagged_identifier_prefixes: list[str],
        version: str = "",
    ):
        self._licenses: dict[str, LicenseInfo] = {}
        for lid, d in licenses.items():
            self._licenses[lid] = LicenseInfo(
                id=lid,
                display_name=d.get("display_name", lid),
                cls=d.get("class", "unknown"),
                commercial_use=d.get("commercial_use", "conditional"),
                share_alike=bool(d.get("share_alike", False)),
                acceptable_use_restrictions=bool(d.get("acceptable_use_restrictions", False)),
                url=d.get("url"),
            )
        self.defaults = defaults or {}
        self.flagged_host_substrings = [s.lower() for s in flagged_host_substrings]
        self.flagged_identifier_prefixes = flagged_identifier_prefixes
        self.version = version

    # -- loading ------------------------------------------------------------- #
    @classmethod
    def load(cls) -> "PolicyKB":
        with open(_config_path("license_kb.yaml"), encoding="utf-8") as fh:
            lic = yaml.safe_load(fh)
        flagged_path = _config_path("flagged_sources.yaml")
        flagged = {}
        if os.path.isfile(flagged_path):
            with open(flagged_path, encoding="utf-8") as fh:
                flagged = yaml.safe_load(fh) or {}
        return cls(
            licenses=lic.get("licenses", {}),
            defaults=lic.get("defaults", {}),
            flagged_host_substrings=flagged.get("flagged_host_substrings", []),
            flagged_identifier_prefixes=flagged.get("flagged_identifier_prefixes", []),
            version=str(lic.get("version", "")),
        )

    # -- queries ------------------------------------------------------------- #
    def license_info(self, license_id: Optional[str]) -> Optional[LicenseInfo]:
        if not license_id:
            return None
        return self._licenses.get(license_id.lower()) or self._unknown(license_id)

    def _unknown(self, license_id: str) -> LicenseInfo:
        return LicenseInfo(
            id=license_id,
            display_name=license_id,
            cls="unknown",
            commercial_use="conditional",
            share_alike=False,
            acceptable_use_restrictions=False,
        )

    @property
    def assume_commercial_use(self) -> bool:
        return bool(self.defaults.get("assume_commercial_use", True))

    def is_flagged_source(self, source: Optional[str], name: Optional[str] = None) -> bool:
        hay = (source or "").lower()
        if any(sub in hay for sub in self.flagged_host_substrings):
            return True
        nm = (name or "").lower()
        return any(nm.startswith(p.lower()) for p in self.flagged_identifier_prefixes)

    def known_license_ids(self) -> list[str]:
        return [lid for lid in self._licenses if lid != "other"]

    def compatibility_with_commercial(self, info: Optional[LicenseInfo]) -> str:
        """How a single component's license combines with commercial distribution."""
        if info is None:
            return Compatibility.REVIEW
        if info.is_non_commercial:
            return Compatibility.CONFLICT
        if info.is_unknown_class:
            return Compatibility.REVIEW
        if info.commercial_use == "conditional" or info.acceptable_use_restrictions:
            return Compatibility.CONDITIONAL
        if info.share_alike or info.cls == "copyleft":
            return Compatibility.OBLIGATION
        return Compatibility.OK

    def pair_compatibility(self, dataset_license: str, model_license: str) -> str:
        """Verdict for using ``dataset_license`` data under a model distributed
        under ``model_license`` (for the compatibility-matrix figure)."""
        d = self.license_info(dataset_license)
        m = self.license_info(model_license)
        if d and d.is_non_commercial:
            # A non-commercial dataset conflicts with any commercially-usable model.
            if m and (m.is_permissive or m.commercial_use in (True, "conditional")):
                return Compatibility.CONFLICT
            return Compatibility.CONDITIONAL
        if d and (d.share_alike or d.cls == "copyleft"):
            return Compatibility.OBLIGATION
        if (d and d.is_unknown_class) or (m and m.is_unknown_class):
            return Compatibility.REVIEW
        if m and m.acceptable_use_restrictions:
            return Compatibility.CONDITIONAL
        return Compatibility.OK
