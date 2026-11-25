# Scope, provenance and responsible use

Author: Krishita Sanjay Choksi

Provenant is a **supply-chain governance support tool**. This document states
plainly what it is for, what it is *not*, and the principles that keep it both
appropriate and credible.

## Purpose

Provenant walks an ML project and produces (1) a standards-aligned **AI Bill of
Materials** (CycloneDX ML-BOM / SPDX AI-profile compatible) of its models,
datasets and binding frameworks, and (2) a **license-and-provenance risk
report** for human review. The deliverables are the artifacts a security, legal
or procurement team needs to *document and vet* the AI components of a system.

## Not a legal license determination

License classifications and compatibility findings are **informational** and
must be confirmed by someone qualified for licensing decisions. Provenant never
asserts that you "may" or "may not" use a component commercially as a matter of
fact — it surfaces the terms and the potential conflicts so a human can decide.
A tool that overclaims license certainty is how a compliance tool creates
liability, so Provenant is deliberately framed as decision *support*.

Concretely:

* Every finding carries a **recommendation to confirm with someone qualified**.
* The policy knowledge base (`config/license_kb.yaml`) encodes *groupings*
  (permissive / copyleft / non-commercial / restricted / unknown), not legal
  advice, and is editable so an organization can apply its own policy.

## `unknown` is a first-class result

When provenance cannot be resolved, Provenant reports `unknown` rather than
guessing. Missing provenance is itself a **finding** (`PROV-MISSING-001`), and
the evaluation measures *gap honesty*: whether the tool reports `unknown`
exactly when it should (unknown precision/recall). A component that was never
discovered is accounted for separately, by discovery/component recall — the tool
measures its own blind spots rather than hiding them.

## Point-in-time artifact

Component metadata and licenses change. A generated AIBOM is a **point-in-time**
snapshot resolved from cached fixtures (offline) or, optionally, read-only hub
metadata. Re-runs are expected and the documents are timestamped.

## No redistribution

The repository **redistributes no model weights or datasets**. Components are
referenced by identifier and content hash only. The bundled synthetic projects
ship zero-information placeholder artifacts whose *names* carry the discovery
signal, and the cached metadata fixtures contain license/card/version records
only. The license snapshots for real public identifiers
(`src/provenant/data/fixtures/metadata_store.yaml`) are an informational,
point-in-time cache and must be reconfirmed upstream.

## Responsible use

* Use the AIBOM and risk report to **inform** human governance and procurement
  decisions; they do not replace legal review.
* The flagged-source list (`config/flagged_sources.yaml`) is an editable,
  illustrative example, not a claim that any real service is malicious.
* Treat discovery as incomplete by design: a signal-based walker can miss
  components it has no detector for. Recall is measured, not assumed.

## Threat-model note

Provenant is a **defensive** tool: it reads a project and reports on it. It
performs no network writes, downloads no weights, and executes none of the
project code it scans — discovery is static (file parsing and regular
expressions over configs, scripts and notebooks).
