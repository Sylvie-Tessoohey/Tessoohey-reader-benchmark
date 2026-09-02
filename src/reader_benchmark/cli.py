"""Offline comparison CLI. Real-data inputs and outputs must stay outside Git."""

import argparse
import json
from pathlib import Path

from reader_benchmark.core import InputError, compare, validate_reference


def render_markdown(report: dict) -> str:
    lines=["# Reader benchmark report", "", f"Case: `{report['case_id']}`",
           f"Reference validation: **{report['reference_status']}**",
           f"Annotation completeness: **{report['annotation_status']}**",
           f"Reader extraction: **{report['extraction_status']}**",
           f"Functional verdict: **{report['functional_verdict']}**", "",
           "No aggregate quality score. This report never validates Gate 1.","",
           "| Dimension | Match | Critical | Noncritical | Ambiguous | Unannotated |",
           "|---|---:|---:|---:|---:|---:|"]
    for name,c in report["dimensions"].items():
        lines.append("| "+name+" | "+" | ".join(str(c.get(k,0)) for k in ("match","critical_error","noncritical_error","ambiguity","unannotated"))+" |")
    lines.extend(["", "## Deviations", ""])
    for c in report["checks"]:
        if c["classification"] not in ("match","unannotated"):
            lines.append(f"- {c['classification']} — {c['dimension']} — `{c['reference_path']}`")
            lines.append("  Expected: "+json.dumps(c["expected"],ensure_ascii=False))
            lines.append("  Actual: "+json.dumps(c["actual"],ensure_ascii=False))
    return "\n".join(lines)+"\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    val=sub.add_parser("validate-reference")
    val.add_argument("reference",type=Path)
    cmp=sub.add_parser("compare")
    for name in ("reference","produced","run"):
        cmp.add_argument(name,type=Path)
    cmp.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        reference=json.loads(args.reference.read_text())
        if args.command=="validate-reference":
            validate_reference(reference)
            print(json.dumps({"valid":True,"reference_status":reference["status"],
                              "annotation_status":reference["annotation_status"],
                              "gold":reference["status"]=="validated" and reference["annotation_status"]=="complete"}))
            return 0
        report=compare(reference,json.loads(args.produced.read_text()),json.loads(args.run.read_text()))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        args.output.with_suffix(".md").write_text(render_markdown(report))
        print(json.dumps({k:report[k] for k in ("case_id","annotation_status","extraction_status","functional_verdict","counts")}))
        return 0 if report["functional_verdict"]=="PASS" else 2
    except (InputError,ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({"functional_verdict":"INPUT_INVALID","error":str(exc)}))
        return 3


if __name__=="__main__":
    raise SystemExit(main())
