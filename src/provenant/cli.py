"""Command-line entry point: ``python -m provenant.cli <command>``.

Every command runs fully offline. Pipeline stages are idempotent — each runs the
chain up to and including its stage and writes an inspectable artifact — so they
can be invoked individually (as the Makefile does) or via ``all``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .model import BOM
from .discover import discover_project
from .resolve import resolve_bom
from .lineage import reconstruct_lineage
from .analyze import analyze_bom
from .aibom import assemble_cyclonedx, assemble_spdx, validate_cyclonedx, validate_spdx


def _build_bom(project_dir: str, upto: str) -> BOM:
    bom = discover_project(project_dir)
    if upto == "discover":
        return bom
    resolve_bom(bom, project_dir)
    if upto == "resolve":
        return bom
    reconstruct_lineage(bom, project_dir)
    if upto == "lineage":
        return bom
    analyze_bom(bom)
    return bom


def _write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


def _stage(args, upto: str, artifact: str) -> None:
    bom = _build_bom(args.project, upto)
    os.makedirs(args.out, exist_ok=True)
    bom.save(os.path.join(args.out, artifact))
    counts = {
        "components": len(bom.components),
        "relationships": len(bom.relationships),
        "findings": len(bom.findings),
    }
    print(f"[{upto}] {args.project} -> {os.path.join(args.out, artifact)}  {counts}")


def cmd_gen_data(args) -> None:
    from .data.generate import generate

    for p in generate(args.out, seed=args.seed):
        print("generated", p)


def cmd_discover(args):
    _stage(args, "discover", "discovered.json")


def cmd_resolve(args):
    _stage(args, "resolve", "resolved.json")


def cmd_lineage(args):
    _stage(args, "lineage", "lineage.json")


def cmd_analyze(args):
    _stage(args, "analyze", "bom.json")


def cmd_bom(args):
    bom = _build_bom(args.project, "analyze")
    os.makedirs(args.out, exist_ok=True)
    cdx = assemble_cyclonedx(bom)
    spdx = assemble_spdx(bom)
    _write_json(os.path.join(args.out, "aibom.cdx.json"), cdx)
    _write_json(os.path.join(args.out, "aibom.spdx.json"), spdx)
    validate_cyclonedx(cdx)
    validate_spdx(spdx)
    print(f"[bom] wrote + validated CycloneDX ML-BOM and SPDX AI-profile docs in {args.out}")


def cmd_report(args):
    from .report import render_project_report

    bom = _build_bom(args.project, "analyze")
    paths = render_project_report(bom, args.out)
    print(f"[report] {args.project} -> {args.out}")
    for k, v in paths.items():
        print(f"    {k}: {v}")


def cmd_all(args):
    cmd_report(args)


def cmd_eval(args):
    from .evaluate import evaluate

    parents = [p.strip() for p in args.projects.split(",") if p.strip()]
    metrics = evaluate(parents, args.out, gold_dir=args.gold)
    o = metrics["overall"]
    print(f"[eval] {o['n_projects']} projects")
    print(f"    discovery recall     : {o['discovery_recall']}")
    print(f"    lineage   P/R/F1     : {o['lineage']['precision']}/{o['lineage']['recall']}/{o['lineage']['f1']}")
    print(f"    finding   P/R/F1     : {o['finding']['precision']}/{o['finding']['recall']}/{o['finding']['f1']}")
    print(f"    provenance accuracy  : {o['provenance_accuracy']}")
    print(f"    unknown   P/R        : {o['unknown']['precision']}/{o['unknown']['recall']}")
    print(f"    AIBOM valid (cdx/spdx): {o['cyclonedx_valid']}/{o['spdx_valid']} of {o['n_projects']}")
    print(f"    wrote {os.path.join(args.out, 'metrics.json')}")


def cmd_figures(args):
    from .report.figures import generate_figures

    produced = generate_figures(args.results, args.out)
    print(f"[figures] wrote {len(produced)} figures to {args.out}")
    for p in produced:
        print("    ", p)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="provenant", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen-data", help="generate synthetic projects + ground truth")
    g.add_argument("--out", default="examples")
    g.add_argument("--seed", type=int, default=7)
    g.set_defaults(func=cmd_gen_data)

    for name, func in [("discover", cmd_discover), ("resolve", cmd_resolve),
                       ("lineage", cmd_lineage), ("analyze", cmd_analyze),
                       ("bom", cmd_bom), ("report", cmd_report), ("all", cmd_all)]:
        p = sub.add_parser(name, help=f"run pipeline through '{name}'")
        p.add_argument("project", help="path to the ML project directory")
        p.add_argument("--out", default="results/out")
        p.set_defaults(func=func)

    e = sub.add_parser("eval", help="score the pipeline against ground truth")
    e.add_argument("--projects", default="examples/synthetic,examples/real")
    e.add_argument("--gold", default="references/gold")
    e.add_argument("--out", default="results")
    e.set_defaults(func=cmd_eval)

    f = sub.add_parser("figures", help="regenerate figures from results")
    f.add_argument("--results", default="results")
    f.add_argument("--out", default="figures")
    f.set_defaults(func=cmd_figures)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
