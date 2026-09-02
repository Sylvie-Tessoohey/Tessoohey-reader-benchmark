"""Compare documentary truth with Reader output without an aggregate quality score.

Reference annotations use JSON pointers into documentary_json. The most specific
ancestor annotation applies; absent annotations always mean unannotated. Expected
null/empty values are assertions only when explicitly covered by an annotation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
import math
import re
from typing import Any

DIMENSIONS = (
    "presence", "source_label", "source_value", "comparator", "unit",
    "current_vs_history", "reference_range", "association", "provenance",
    "structure", "extra_elements", "unclassified",
)


class InputError(ValueError):
    """A case is not a valid, traceable comparison input."""


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reference_payload_sha256(reference: dict) -> str:
    """Approval covers truth, annotation coverage, PDF identity and reference version."""
    keys=("case_id","reference_version","source","documentary_json","annotations","observation_inventory")
    return fingerprint(canonical({k:reference[k] for k in keys}).encode())


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def normalized_label(value: str) -> str:
    # Matching only. Field comparison retains the literal source string.
    return " ".join(value.split()).casefold()


def pointer_get(document: Any, pointer: str) -> Any:
    result = document
    if pointer == "":
        return result
    if not pointer.startswith("/"):
        raise InputError(f"Invalid JSON pointer: {pointer}")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            result = result[int(token)] if isinstance(result, list) else result[token]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise InputError(f"Unknown annotation path: {pointer}") from exc
    return result


def annotation(reference: dict, pointer: str) -> str:
    marks = reference["annotations"]
    while True:
        if pointer in marks:
            return marks[pointer]["status"]
        if not pointer:
            return "unannotated"
        pointer = pointer.rsplit("/", 1)[0]


def _validate_zone(zone: Any, pages: list[dict], path: str) -> None:
    if not isinstance(zone, dict) or zone.get("coordinate_system") != "pdf_points_top_left":
        raise InputError(f"Invalid coordinate system at {path}")
    crops = zone.get("crops", [])
    if not crops:
        raise InputError(f"Empty provenance at {path}")
    for i, crop in enumerate(crops, 1):
        try:
            page = crop["page"]
            if not isinstance(page, int) or not 1 <= page <= len(pages):
                raise ValueError()
            bounds = pages[page - 1]
            x1, y1, x2, y2 = (crop[k] for k in ("x1", "y1", "x2", "y2"))
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x1,y1,x2,y2)):
                raise ValueError()
            if crop["order"] != i or not (0 <= x1 < x2 <= bounds["width"] and 0 <= y1 < y2 <= bounds["height"]):
                raise ValueError()
        except (KeyError, ValueError, TypeError) as exc:
            raise InputError(f"Invalid crop at {path}") from exc


def observations(document: dict) -> list[dict]:
    output = []

    def section(sec: dict, path: str, context: tuple, part_types: tuple):
        context = (*context, sec.get("source_title"))
        for i, obs in enumerate(sec.get("observations", [])):
            output.append({"obs": obs, "path": f"{path}/observations/{i}",
                           "context": context, "part_types": part_types})
        for i, sub in enumerate(sec.get("subsections", [])):
            section(sub, f"{path}/subsections/{i}", context, part_types)

    def part(p: dict, path: str, types: tuple):
        types = (*types, (p.get("type"), p.get("subtype")))
        for i, sec in enumerate(p.get("sections", [])):
            section(sec, f"{path}/sections/{i}", (), types)
        for i, sub in enumerate(p.get("subparts", [])):
            part(sub, f"{path}/subparts/{i}", types)

    for i, p in enumerate(document.get("parts", [])):
        part(p, f"/parts/{i}", ())
    return output


def validate_reference(reference: dict) -> None:
    if reference.get("reference_schema_version") != "1.0":
        raise InputError("Unsupported reference schema version")
    if reference.get("status") not in ("candidate", "validated"):
        raise InputError("Reference status must be candidate or validated")
    if reference.get("status") == "validated":
        approval = reference.get("validation", {})
        if not approval.get("reviewer") or not approval.get("validated_at"):
            raise InputError("Validated references require reviewer and timestamp")
        if approval.get("reference_payload_sha256") != reference_payload_sha256(reference):
            raise InputError("Reference approval does not match content, source or annotations")
    source = reference.get("source", {})
    if not re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")):
        raise InputError("A source SHA-256 is required")
    if not isinstance(source.get("size_bytes"), int) or source["size_bytes"] <= 0:
        raise InputError("A positive source byte count is required")
    pages = source.get("pages", [])
    if not pages or source.get("page_count") != len(pages):
        raise InputError("Source page geometry must cover the complete PDF")
    doc = reference.get("documentary_json", {})
    if doc.get("schema_version") != "1.0" or not isinstance(doc.get("parts"), list):
        raise InputError("Reference must contain Module 1 schema 1.0 documentary JSON")
    if not isinstance(reference.get("annotations"), dict):
        raise InputError("Explicit reference annotations are required")
    for path, mark in reference["annotations"].items():
        if mark.get("status") not in ("verified", "unannotated", "ambiguous"):
            raise InputError(f"Invalid annotation status at {path}")
        pointer_get(doc, path)
        if mark["status"] == "ambiguous" and not mark.get("note"):
            raise InputError(f"An ambiguity needs an explanation at {path}")
    if reference.get("observation_inventory") not in ("complete", "incomplete"):
        raise InputError("Declare observation inventory completeness")
    ids = []
    for item in observations(doc):
        obs = item["obs"]
        if not obs.get("id") or not isinstance(obs.get("source_label"), str):
            raise InputError("Reference observations require IDs and source labels")
        ids.append(obs["id"])
        _validate_zone(obs.get("source_zone"), pages, item["path"])
    if len(ids) != len(set(ids)):
        raise InputError("Duplicate reference observation IDs")


def validate_run(reference: dict, produced: dict, run: dict) -> None:
    for field in ("reader_commit", "schema_version", "provider", "model", "parameters",
                  "prompt_version", "prompt_sha256", "source", "run_date", "duration_ms", "tokens"):
        if field not in run:
            raise InputError(f"Missing run identity field: {field}")
    if not re.fullmatch(r"[0-9a-f]{40}", run["reader_commit"]):
        raise InputError("Reader commit must be a full SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", run["prompt_sha256"]):
        raise InputError("Record the actual prompt fingerprint, not only its label")
    if not all(isinstance(run[x], str) and run[x] for x in ("provider", "model", "prompt_version", "run_date")):
        raise InputError("Run profile fields must be nonempty")
    if not isinstance(run["parameters"], dict) or not isinstance(run["duration_ms"], (float, int)) or run["duration_ms"] < 0:
        raise InputError("Invalid run parameters or duration")
    for key in ("sha256", "size_bytes", "page_count"):
        if run["source"].get(key) != reference["source"].get(key):
            raise InputError(f"PDF identity mismatch: {key}")
    if run["schema_version"] != produced.get("schema_version") or produced.get("schema_version") != reference["documentary_json"]["schema_version"]:
        raise InputError("Content schema versions differ")
    if produced.get("status") not in ("success", "partial", "error"):
        raise InputError("Unknown Reader status")
    meta = produced.get("extraction_metadata", {})
    for rk, mk in (("reader_commit", "module_commit"), ("model", "model"), ("provider", "provider"), ("prompt_version", "prompt_version")):
        if meta.get(mk) is not None and meta[mk] != run[rk]:
            raise InputError(f"Run manifest contradicts output metadata: {rk}")
    if run["tokens"] is not None:
        for k in ("input_tokens", "output_tokens", "total_tokens"):
            if not isinstance(run["tokens"].get(k), int) or run["tokens"][k] < 0:
                raise InputError("Invalid token usage")
        if run["tokens"]["input_tokens"] + run["tokens"]["output_tokens"] != run["tokens"]["total_tokens"]:
            raise InputError("Inconsistent token total")
    elif not run.get("tokens_unavailable_reason"):
        raise InputError("Explain missing token usage")


def _crops(obs: dict) -> list[dict]:
    return (obs.get("source_zone") or {}).get("crops", [])


def _overlap(a: dict, b: dict) -> float:
    if a.get("page") != b.get("page"):
        return 0.0
    intersection = max(0, min(a["x2"],b["x2"])-max(a["x1"],b["x1"])) * max(0,min(a["y2"],b["y2"])-max(a["y1"],b["y1"]))
    aa = max(0,(a["x2"]-a["x1"])*(a["y2"]-a["y1"]))
    bb = max(0,(b["x2"]-b["x1"])*(b["y2"]-b["y1"]))
    return intersection / (aa+bb-intersection) if aa+bb-intersection else 0


def matching_score(a: dict, b: dict) -> float:
    # Never use values, units, reference ranges or histories for identity matching.
    la, lb = (normalized_label(x["obs"].get("source_label", "")) for x in (a,b))
    ac, bc = _crops(a["obs"]), _crops(b["obs"])
    overlap = max((_overlap(x,y) for x in ac for y in bc), default=0)
    exact = bool(la) and la == lb
    similarity = SequenceMatcher(None,la,lb).ratio()
    if not exact and not (overlap >= .25 and similarity >= .35):
        return 0
    same_page = bool({c["page"] for c in ac} & {c["page"] for c in bc})
    context = a["context"] == b["context"]
    return (8 if exact else 2*similarity) + 2*same_page + overlap + context


def match_observations(expected: list[dict], actual: list[dict]) -> tuple[dict, set, set]:
    # Only mutual, unique maxima are accepted. Ties remain explicit, not greedy matches.
    scores = {(i,j):matching_score(a,b) for i,a in enumerate(expected) for j,b in enumerate(actual)}
    ei, aj = set(range(len(expected))), set(range(len(actual)))
    matches = {}
    while True:
        def best(index, candidates, reverse=False):
            ranked = sorted(((scores[(j,index)] if reverse else scores[(index,j)],j) for j in candidates), reverse=True)
            if not ranked or ranked[0][0] <= 0 or (len(ranked)>1 and abs(ranked[0][0]-ranked[1][0])<.15):
                return None
            return ranked[0][1]
        pairs=[]
        for i in ei:
            j=best(i,aj)
            if j is not None and best(j,ei,True)==i:
                pairs.append((i,j))
        if not pairs:
            break
        for i,j in pairs:
            matches[i]=j;ei.remove(i);aj.remove(j)
    ambiguous_expected={i for i in ei if any(scores[(i,j)]>0 for j in aj)}
    ambiguous_actual={j for j in aj if any(scores[(i,j)]>0 for i in ei)}
    return matches, ambiguous_expected, ambiguous_actual


def _representations(obs: dict, field: str | None = None) -> list:
    reps=(obs.get("current_result") or {}).get("source_representations",[])
    values=[r.get(field) if field else {k:r.get(k) for k in ("source_value","comparator","source_unit")} for r in reps]
    return sorted(values,key=canonical)


def _source_tree(value: Any) -> Any:
    if isinstance(value,list):
        return sorted((_source_tree(v) for v in value),key=canonical)
    if isinstance(value,dict):
        return {k:_source_tree(v) for k,v in value.items() if k not in ("id","source_zone","provenance")}
    return value


def _structure(doc: dict) -> list:
    result=[]
    def sections(ss,parent):
        for sec in ss:
            here=(*parent,sec.get("source_title"));result.append(("section",here))
            sections(sec.get("subsections",[]),here)
    def parts(ps,parent):
        for p in ps:
            here=(*parent,(p.get("type"),p.get("subtype")));result.append(("part",here))
            sections(p.get("sections",[]),here)
            parts(p.get("subparts",[]),here)
    parts(doc.get("parts",[]),())
    return sorted(result,key=canonical)


def compare(reference: dict, produced: dict, run: dict) -> dict:
    validate_reference(reference)
    validate_run(reference,produced,run)
    checks=[]
    def add(dimension, severity, path, expected=None, actual=None, detail=None):
        checks.append({"dimension":dimension,"classification":severity,"reference_path":path,
                       "expected":expected,"actual":actual,"detail":detail})
    def check(dimension,path,expected,actual,critical=True,equal=None,annotation_paths=None):
        paths=annotation_paths or [path]
        states=[annotation(reference,p) for p in paths]
        # A narrower uncertainty must not be hidden by a verified parent.
        if dimension!="presence":
            for p in paths:
                states.extend(m["status"] for q,m in reference["annotations"].items() if q.startswith(p+"/"))
        state="ambiguous" if "ambiguous" in states else "unannotated" if "unannotated" in states else "verified"
        if state!="verified":
            add(dimension,"ambiguity" if state=="ambiguous" else "unannotated",path,detail="Reference field not scored")
            return
        same=canonical(expected)==canonical(actual) if equal is None else equal
        add(dimension,"match" if same else ("critical_error" if critical else "noncritical_error"),path,expected,actual)
    expected=observations(reference["documentary_json"])
    actual=observations(produced)
    invalid_actual=set()
    for j,item in enumerate(actual):
        try:_validate_zone(item["obs"].get("source_zone"),reference["source"]["pages"],item["path"])
        except InputError as exc:
            invalid_actual.add(j)
            add("provenance","critical_error",item["path"],detail=str(exc))
            # Exclude invalid geometry from the matcher, but retain label identity.
            item["obs"]={**item["obs"],"source_zone":{"crops":[]}}
    matches,amb_e,amb_a=match_observations(expected,actual)
    for i,item in enumerate(expected):
        path=item["path"];a=item["obs"]
        if i in amb_e:
            add("presence","ambiguity",path,detail="Observation identity cannot be matched uniquely")
            continue
        if i not in matches:
            check("presence",path,True,False)
            continue
        bitem=actual[matches[i]];b=bitem["obs"]
        check("presence",path,True,True)
        check("source_label",path+"/source_label",a.get("source_label"),b.get("source_label"),False)
        for dim,field in (("source_value","source_value"),("comparator","comparator"),("unit","source_unit")):
            field_paths=[f"{path}/current_result/source_representations/{k}/{field}" for k,_ in enumerate(a.get("current_result",{}).get("source_representations",[]))]
            check(dim,path+"/current_result",_representations(a,field),_representations(b,field),annotation_paths=field_paths)
        check("current_vs_history",path+"/previous_results",_source_tree(a.get("previous_results",[])),_source_tree(b.get("previous_results",[])))
        check("reference_range",path+"/reference_ranges",_source_tree(a.get("reference_ranges",[])),_source_tree(b.get("reference_ranges",[])))
        # Coupled comparisons detect swaps hidden by identical per-field multisets.
        check("association",path+"/current_result",_representations(a),_representations(b))
        check("association",path+"/current_result/type",a.get("current_result",{}).get("type"),b.get("current_result",{}).get("type"))
        check("structure",path,{"sections":item["context"],"parts":item["part_types"]},
              {"sections":bitem["context"],"parts":bitem["part_types"]},False)
        ac,bc=_crops(a),_crops(b)
        ok=(matches[i] not in invalid_actual and len(ac)==len(bc) and all(
            x.get("page")==y.get("page") and _overlap(x,y)>=.25 for x,y in zip(ac,bc)))
        check("provenance",path+"/source_zone",ac,bc,equal=ok)
        # Evaluate explicitly annotated supplementary fields, keeping medical flags strict.
        for field in ("method","comment","lab_interpretation","ambiguity"):
            check("association",path+"/"+field,_source_tree(a.get(field)),_source_tree(b.get(field)),field=="lab_interpretation")
    used=set(matches.values())
    for j,item in enumerate(actual):
        if j in used:continue
        if j in amb_a:
            add("extra_elements","ambiguity",item["path"],detail="Unresolved identity; not counted as a proven extra")
        else:
            complete=reference["observation_inventory"]=="complete"
            add("extra_elements","critical_error" if complete else "unannotated",item["path"],actual=item["obs"].get("source_label"),detail="Unexpected observation" if complete else "Inventory is incomplete")
    doc=reference["documentary_json"]
    check("structure","/document",_source_tree(doc.get("document")),_source_tree(produced.get("document")),False)
    check("structure","/parts",_structure(doc),_structure(produced),False)
    check("unclassified","/unclassified_elements",_source_tree(doc.get("unclassified_elements",[])),_source_tree(produced.get("unclassified_elements",[])),False)
    counts=Counter(c["classification"] for c in checks)
    by_dim={d:dict(Counter(c["classification"] for c in checks if c["dimension"]==d)) for d in DIMENSIONS}
    if reference["status"]!="validated":verdict="CANDIDATE_REFERENCE"
    elif produced["status"]!="success":verdict=produced["status"].upper()
    elif counts["critical_error"] or counts["noncritical_error"]:verdict="FAIL"
    elif counts["ambiguity"] or counts["unannotated"] or reference["observation_inventory"]!="complete":verdict="INCOMPLETE"
    else:verdict="PASS"
    return {"benchmark_schema_version":"1.0","case_id":reference["case_id"],"reference_version":reference["reference_version"],
            "reference_status":reference["status"],"reader_status":produced["status"],"functional_verdict":verdict,
            "reference_sha256":fingerprint(canonical(reference).encode()),"output_sha256":fingerprint(canonical(produced).encode()),
            "run":run,"observations":{"expected":len(expected),"produced":len(actual),"matched":len(matches),
              "missing":len(expected)-len(matches)-len(amb_e),"ambiguous":len(amb_e),
              "unexpected":len(actual)-len(used)-len(amb_a)},
            "counts":dict(counts),"dimensions":by_dim,"checks":checks,
            "policy":{"matching":"label + section context + page + geometry; no values or units",
                      "source_text":"literal; whitespace normalization for matching only",
                      "geometry":"same ordered pages and IoU >= 0.25; does not prove visual truth",
                      "aggregate_score":None,"gate1_validated":False}}
