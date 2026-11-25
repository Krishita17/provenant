"""The rule engine: evaluate components + lineage against the policy KB."""

from __future__ import annotations

from typing import Optional

from ..model import BOM, Component, ComponentType, Evidence, Finding, Severity
from ..policy import PolicyKB
from ..lineage import provenance_subgraph

#: The rule catalogue, surfaced in the report and README for explainability.
RULES = {
    "LIC-NC-001": "Component is under a non-commercial license.",
    "LIC-RESTRICT-001": "Component license carries share-alike / acceptable-use / copyleft obligations.",
    "LIC-REVIEW-001": "Component license is present but non-standard and needs human review.",
    "LIC-INCOMPAT-001": "A commercially-usable model has a non-commercial component in its lineage.",
    "PROV-MISSING-001": "No license/provenance could be resolved for this component.",
    "PIN-001": "Component is not pinned to a version or content hash.",
    "SRC-FLAG-001": "Component is sourced from a flagged / untrusted origin.",
}

_CATEGORY = {
    "LIC-NC-001": "non_commercial",
    "LIC-RESTRICT-001": "restrictive_license",
    "LIC-REVIEW-001": "license_review",
    "LIC-INCOMPAT-001": "license_incompatibility",
    "PROV-MISSING-001": "missing_provenance",
    "PIN-001": "unpinned",
    "SRC-FLAG-001": "flagged_source",
}


def _finding(rule_id: str, comp: Component, severity: str, message: str,
             recommendation: str, evidence: list[Evidence],
             related: Optional[str] = None) -> Finding:
    return Finding(
        id=f"{rule_id}:{comp.id}" + (f"->{related}" if related else ""),
        category=_CATEGORY[rule_id],
        severity=severity,
        component_id=comp.id,
        rule_id=rule_id,
        message=message,
        recommendation=recommendation,
        evidence=evidence,
        related_component_id=related,
    )


def analyze_bom(bom: BOM, kb: Optional[PolicyKB] = None) -> BOM:
    """Attach risk/compliance findings to ``bom`` (in place) and return it."""
    kb = kb or PolicyKB.load()
    findings: list[Finding] = []

    for comp in bom.components:
        info = kb.license_info(comp.license)
        if info is not None:
            comp.commercial_use = (
                not info.is_non_commercial
                and info.commercial_use in (True, "conditional")
            )

        # --- missing provenance (no resolvable license) --------------------- #
        if comp.license is None:
            sev = Severity.HIGH if comp.type == ComponentType.MODEL else Severity.MEDIUM
            findings.append(_finding(
                "PROV-MISSING-001", comp, sev,
                f"No license or provenance could be resolved for {comp.type} "
                f"'{comp.name}'.",
                "Identify the component's source and license before use; treat as "
                "unvetted until resolved. Provenant reports this as 'unknown' "
                "rather than guessing.",
                [Evidence("analyzer", f"provenance status = {comp.provenance_status}")],
            ))
        else:
            # --- license class findings ------------------------------------ #
            if info.is_non_commercial:
                findings.append(_finding(
                    "LIC-NC-001", comp, Severity.HIGH,
                    f"{comp.type.capitalize()} '{comp.name}' is under "
                    f"{info.display_name} (non-commercial).",
                    "Do not use in a commercial system without a separate grant; "
                    "confirm the terms with someone qualified.",
                    [Evidence("policy_kb", f"license '{comp.license}' class=non_commercial")],
                ))
            elif info.is_restrictive:
                detail = []
                if info.share_alike:
                    detail.append("share-alike/copyleft obligations")
                if info.acceptable_use_restrictions:
                    detail.append("acceptable-use restrictions")
                if not detail:
                    detail.append("restrictive terms")
                findings.append(_finding(
                    "LIC-RESTRICT-001", comp, Severity.MEDIUM,
                    f"{comp.type.capitalize()} '{comp.name}' is under "
                    f"{info.display_name} ({', '.join(detail)}).",
                    "Review the obligations (e.g. relicensing, redistribution or "
                    "use-case limits) against your intended use.",
                    [Evidence("policy_kb", f"license '{comp.license}' class={info.cls}")],
                ))
            elif info.is_unknown_class:
                findings.append(_finding(
                    "LIC-REVIEW-001", comp, Severity.INFO,
                    f"{comp.type.capitalize()} '{comp.name}' declares a "
                    f"non-standard license ('{comp.license}').",
                    "Have someone qualified review the actual terms; the class "
                    "could not be determined automatically.",
                    [Evidence("policy_kb", f"license '{comp.license}' class=unknown")],
                ))

        # --- unpinned (known component, unknown version) -------------------- #
        if (
            comp.provenance_status == "resolved"
            and not comp.version
            and not comp.hash
        ):
            findings.append(_finding(
                "PIN-001", comp, Severity.LOW,
                f"{comp.type.capitalize()} '{comp.name}' is not pinned to a "
                f"version or content hash.",
                "Pin a revision/hash so the component is verifiable and the BOM "
                "is reproducible.",
                [Evidence("analyzer", "no version and no content hash present")],
            ))

        # --- flagged source ------------------------------------------------- #
        if kb.is_flagged_source(comp.source, comp.name):
            findings.append(_finding(
                "SRC-FLAG-001", comp, Severity.HIGH,
                f"{comp.type.capitalize()} '{comp.name}' is sourced from a "
                f"flagged origin ({comp.source}).",
                "Do not trust this component until its origin and integrity are "
                "independently verified.",
                [Evidence("policy_kb", f"source matches a flagged host rule")],
            ))

    # --- cross-lineage license incompatibility ----------------------------- #
    if kb.assume_commercial_use:
        for comp in bom.components:
            if comp.type != ComponentType.MODEL:
                continue
            info = kb.license_info(comp.license)
            commercial_model = (
                info is not None
                and not info.is_non_commercial
                and (info.is_permissive or info.commercial_use in (True, "conditional"))
            )
            if not commercial_model:
                continue
            for other_id in sorted(provenance_subgraph(bom, comp.id)):
                other = bom.by_id(other_id)
                if other is None:
                    continue
                oinfo = kb.license_info(other.license)
                if oinfo is not None and oinfo.is_non_commercial:
                    findings.append(_finding(
                        "LIC-INCOMPAT-001", comp, Severity.HIGH,
                        f"Model '{comp.name}' ({info.display_name}) has a "
                        f"non-commercial component '{other.name}' "
                        f"({oinfo.display_name}) in its lineage.",
                        "A commercial release would inherit the non-commercial "
                        "restriction; re-source the component or restrict use. "
                        "Confirm with someone qualified.",
                        [Evidence("analyzer",
                                  "commercial model reaches a non-commercial "
                                  "component via provenance edges")],
                        related=other_id,
                    ))

    findings.sort(key=lambda f: (Severity.ORDER.get(f.severity, 9), f.component_id, f.rule_id))
    bom.findings = findings
    return bom
