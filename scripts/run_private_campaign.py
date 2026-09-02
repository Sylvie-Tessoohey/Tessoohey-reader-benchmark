"""Run a pinned Reader on a private corpus, retaining requests for deterministic replay.

This is an external benchmark harness. It never changes Reader source files.
Run in a private environment with the Reader and benchmark installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def verify_git_checkout(root, expected_commit, label):
    """Require the exact planned commit and reject tracked local modifications."""
    if not expected_commit:
        raise SystemExit(f"Campaign plan must pin {label.lower()}_commit")
    commit=subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if commit != expected_commit:
        raise SystemExit(f"{label} checkout differs from the planned exact commit")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise SystemExit(f"{label} checkout contains tracked modifications")
    return commit


def verify_prompt(root, plan):
    identity=plan["prompt_identity"]
    expected={"src/tessoohey_reader/ai/openai_provider.py",
              "src/tessoohey_reader/ai/models.py", "src/tessoohey_reader/semantic/models.py"}
    if identity.get("scheme")!="reader-prompt-files-v1" or set(identity.get("files",{}))!=expected:
        raise ValueError("Prompt identity must cover instructions, request construction and response schemas")
    if digest(identity)!=plan["prompt_sha256"]:
        raise ValueError("Prompt fingerprint does not match planned identity")
    for name, expected_hash in identity["files"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected_hash:
            raise ValueError(f"Actual prompt component differs: {name}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--reader-checkout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    benchmark_root=Path(__file__).resolve().parents[1]
    benchmark_commit=verify_git_checkout(benchmark_root,plan.get("benchmark_commit"),"Benchmark")
    root=args.reader_checkout.resolve()
    commit=verify_git_checkout(root,plan.get("reader_commit"),"Reader")
    verify_prompt(root, plan)
    if args.output.exists():
        raise SystemExit("Use a new output directory; existing campaign evidence must not be overwritten")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required in this private execution environment")
    # Load only the checkout that was verified, not a similarly named installed Reader.
    sys.path.insert(0, str(root/"src"))
    from reader_benchmark.core import compare, validate_reference, reference_payload_sha256
    from reader_benchmark.cli import render_markdown
    from tessoohey_reader.ai.config import AISettings
    from tessoohey_reader.ai.openai_provider import OpenAIProvider
    from tessoohey_reader.extraction import extract_pdf_with_report
    from openai import OpenAI
    import pymupdf

    prepared=[]
    for case in plan["cases"]:
        ref=json.loads((args.plan.parent/case["reference_path"]).read_text())
        validate_reference(ref)
        if ref["status"]!="validated" or ref["annotation_status"]!="complete":
            raise SystemExit(f"{case['case_id']}: complete, explicitly approved reference required")
        if reference_payload_sha256(ref)!=case["reference_payload_sha256"]:
            raise SystemExit(f"{case['case_id']}: reference content changed after campaign freeze")
        source=args.plan.parent/case["pdf_path"]
        data=source.read_bytes()
        with pymupdf.open(stream=data, filetype="pdf") as pdf: count=len(pdf)
        actual={"sha256":hashlib.sha256(data).hexdigest(), "size_bytes":len(data), "page_count":count}
        if any(actual[k]!=ref["source"][k] for k in actual):
            raise SystemExit(f"{case['case_id']}: PDF fingerprint differs from reference")
        prepared.append((case,ref,data,actual))
    os.environ["TESSOOHEY_READER_COMMIT"]=commit
    settings=AISettings(provider=plan["provider"],model=plan["model"],prompt_version=plan["prompt_version"],
                        **plan["parameters"])
    client=OpenAI(max_retries=0)
    args.output.mkdir(parents=True)
    write(args.output/"environment.json", {"python":sys.version,"reader_commit":commit,
        "benchmark_commit":benchmark_commit,
        "packages":{k:importlib.metadata.version(k) for k in ("openai","pydantic","PyMuPDF")}})
    summaries=[]
    for case,reference,data,source in prepared:
        out=args.output/case["case_id"];out.mkdir()
        calls=[]
        class RecordingResponses:
            def parse(self, **kwargs):
                index=len(calls)+1
                request={**kwargs,"text_format":kwargs["text_format"].model_json_schema()}
                # Full request and response remain in the private campaign directory.
                record={"call":index,"request_sha256":digest(request),
                        "instructions_sha256":hashlib.sha256(kwargs["instructions"].encode()).hexdigest()}
                calls.append(record)
                write(out/f"call-{index:03}-request.json",request)
                try:
                    response=client.responses.parse(**kwargs)
                except Exception as exc:
                    record["error_type"]=type(exc).__name__
                    write(out/"calls.json",calls)
                    raise
                record["response_id"]=getattr(response,"id",None)
                record["actual_model"]=getattr(response,"model",None)
                write(out/f"call-{index:03}-response.json",response.model_dump(mode="json"))
                write(out/"calls.json",calls)
                return response
        class RecordingClient:
            responses=RecordingResponses()
        provider=OpenAIProvider(settings=settings,client=RecordingClient())
        try:
            artifacts=extract_pdf_with_report(data,filename=case["case_id"]+".pdf",settings=settings,provider=provider)
            content=artifacts.content.model_dump(mode="json")
            execution=artifacts.execution_report.model_dump(mode="json")
            write(out/"content.json",content);write(out/"execution-report.json",execution)
            tokens=execution["ai"]["token_usage"]
            run={"reader_commit":commit,"benchmark_commit":benchmark_commit,
                 "schema_version":content["schema_version"],"provider":settings.provider,
                 "model":settings.model,"parameters":plan["parameters"],"prompt_version":settings.prompt_version,
                 "prompt_sha256":plan["prompt_sha256"],"prompt_identity":plan["prompt_identity"],
                 "actual_calls":calls,"source":source,"run_date":execution["run_date"],
                 "execution_parameters":{"sdk_max_retries":0},
                 "duration_ms":execution["duration_ms"],"tokens":tokens,
                 "cost":None,"cost_unavailable_reason":"No verified price schedule supplied"}
            if tokens is None:run["tokens_unavailable_reason"]="Reader did not return usage; inspect recorded calls"
            write(out/"run.json",run)
            result=compare(reference,content,run)
            write(out/"comparison.json",result)
            (out/"comparison.md").write_text(render_markdown(result))
            summaries.append({k:result[k] for k in ("case_id","annotation_status","extraction_status","functional_verdict","counts")})
        except Exception as exc:
            # A harness error is not an invented Reader extraction_status.
            write(out/"harness-error.json",{"exception_type":type(exc).__name__,"message":str(exc)})
            summaries.append({"case_id":case["case_id"],"campaign_status":"harness_error","extraction_status":None})
        write(args.output/"campaign-summary.json",{"campaign_id":plan["campaign_id"],
            "benchmark_commit":benchmark_commit,"reader_commit":commit,
            "cases":summaries,"gate1_validated":False})
    print(json.dumps({"campaign_id":plan["campaign_id"],"benchmark_commit":benchmark_commit,
                      "reader_commit":commit,"cases":summaries},ensure_ascii=False))
    return 0 if all(x.get("functional_verdict")=="PASS" for x in summaries) else 2


if __name__=="__main__":
    raise SystemExit(main())
