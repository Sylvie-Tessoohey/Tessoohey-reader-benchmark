"""Deterministic before/after comparison of private benchmark campaign evidence.

This module compares benchmark reports only. It never reads the medical source PDF or changes
reference truth, and it never turns count deltas into an aggregate quality score.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ERROR_CLASSIFICATIONS = {"critical_error", "noncritical_error"}


class CampaignDeltaError(ValueError):
    """Raised when campaign evidence is missing or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class CampaignEvidence:
    """Loaded campaign summary plus per-case comparison reports."""

    summary: dict[str, Any]
    comparisons: dict[str, dict[str, Any]]


def _json_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignDeltaError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CampaignDeltaError(f"{label} must contain a JSON object")
    return value


def _case_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        raise CampaignDeltaError("campaign-summary.json must contain a cases list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise CampaignDeltaError("campaign case entries must be JSON objects")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise CampaignDeltaError("every campaign case must have a case_id")
        if case_id in seen:
            raise CampaignDeltaError(f"duplicate campaign case_id {case_id!r}")
        seen.add(case_id)
        result.append(item)
    return result


def _directory_campaign(path: Path) -> CampaignEvidence:
    summary_path = path / "campaign-summary.json"
    if not summary_path.is_file():
        candidates = list(path.rglob("campaign-summary.json"))
        if len(candidates) != 1:
            raise CampaignDeltaError(
                f"{path} must contain exactly one campaign-summary.json"
            )
        summary_path = candidates[0]
    root = summary_path.parent
    summary = _json_object(summary_path.read_bytes(), str(summary_path))
    comparisons: dict[str, dict[str, Any]] = {}
    for item in _case_entries(summary):
        case_id = item["case_id"]
        comparison_path = root / case_id / "comparison.json"
        if not comparison_path.is_file():
            raise CampaignDeltaError(
                f"campaign case {case_id!r} is missing comparison.json"
            )
        comparisons[case_id] = _json_object(
            comparison_path.read_bytes(),
            str(comparison_path),
        )
    return CampaignEvidence(summary=summary, comparisons=comparisons)


def _zip_campaign(path: Path) -> CampaignEvidence:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CampaignDeltaError(f"{path} is not a readable ZIP archive") from exc
    with archive:
        summary_names = [
            name for name in archive.namelist() if name.endswith("campaign-summary.json")
        ]
        if len(summary_names) != 1:
            raise CampaignDeltaError(
                f"{path} must contain exactly one campaign-summary.json"
            )
        summary_name = summary_names[0]
        root = summary_name[: -len("campaign-summary.json")]
        summary = _json_object(archive.read(summary_name), summary_name)
        comparisons: dict[str, dict[str, Any]] = {}
        for item in _case_entries(summary):
            case_id = item["case_id"]
            name = f"{root}{case_id}/comparison.json"
            try:
                payload = archive.read(name)
            except KeyError as exc:
                raise CampaignDeltaError(
                    f"campaign case {case_id!r} is missing comparison.json"
                ) from exc
            comparisons[case_id] = _json_object(payload, name)
    return CampaignEvidence(summary=summary, comparisons=comparisons)


def load_campaign(path: Path) -> CampaignEvidence:
    """Load private campaign evidence from a result directory or ZIP archive."""

    if path.is_dir():
        return _directory_campaign(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return _zip_campaign(path)
    raise CampaignDeltaError(
        f"{path} must be a campaign result directory or ZIP archive"
    )


def _counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, number in value.items():
        if isinstance(key, str) and isinstance(number, int) and not isinstance(number, bool):
            result[key] = number
    return result


def _count_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = sorted(set(before) | set(after))
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def _check_index(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise CampaignDeltaError("comparison.json must contain a checks list")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for check in checks:
        if not isinstance(check, dict):
            raise CampaignDeltaError("comparison checks must be JSON objects")
        dimension = check.get("dimension")
        path = check.get("reference_path")
        classification = check.get("classification")
        if not all(isinstance(value, str) for value in (dimension, path, classification)):
            raise CampaignDeltaError(
                "comparison check needs dimension, reference_path and classification"
            )
        key = (dimension, path)
        if key in result:
            raise CampaignDeltaError(
                f"comparison contains duplicate check identity {dimension}:{path}"
            )
        result[key] = check
    return result


def _transitions(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
) -> list[dict[str, Any]]:
    before = _check_index(baseline_report)
    after = _check_index(candidate_report)
    transitions: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        previous = before.get(key)
        current = after.get(key)
        previous_class = previous.get("classification") if previous else "missing"
        current_class = current.get("classification") if current else "missing"
        if previous_class == current_class:
            continue

        if previous_class in ERROR_CLASSIFICATIONS and current_class == "match":
            change = "error_resolved"
        elif previous_class == "match" and current_class in ERROR_CLASSIFICATIONS:
            change = "new_error"
        elif previous_class == "ambiguity" or current_class == "ambiguity":
            change = "ambiguity_transition"
        elif previous is None:
            change = "new_check"
        elif current is None:
            change = "removed_check"
        else:
            change = "classification_changed"

        dimension, reference_path = key
        transitions.append(
            {
                "change": change,
                "dimension": dimension,
                "reference_path": reference_path,
                "baseline_classification": previous_class,
                "candidate_classification": current_class,
            }
        )
    return transitions


def _dimension_delta(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    before = baseline_report.get("dimensions")
    after = candidate_report.get("dimensions")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise CampaignDeltaError("comparison reports must contain dimensions objects")
    result: dict[str, dict[str, Any]] = {}
    for dimension in sorted(set(before) | set(after)):
        before_counts = _counts(before.get(dimension))
        after_counts = _counts(after.get(dimension))
        result[dimension] = {
            "baseline": before_counts,
            "candidate": after_counts,
            "delta": _count_delta(before_counts, after_counts),
        }
    return result


def _summary_identity(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: summary.get(key)
        for key in ("campaign_id", "benchmark_commit", "reader_commit", "gate1_validated")
    }


def compare_campaigns(
    baseline: CampaignEvidence,
    candidate: CampaignEvidence,
) -> dict[str, Any]:
    """Compare two campaigns without producing an aggregate score."""

    baseline_cases = {item["case_id"]: item for item in _case_entries(baseline.summary)}
    candidate_cases = {item["case_id"]: item for item in _case_entries(candidate.summary)}
    case_ids = sorted(set(baseline_cases) | set(candidate_cases))

    cases: list[dict[str, Any]] = []
    totals = {
        "error_resolved": 0,
        "new_error": 0,
        "ambiguity_transition": 0,
        "classification_changed": 0,
        "new_check": 0,
        "removed_check": 0,
    }

    for case_id in case_ids:
        before_case = baseline_cases.get(case_id)
        after_case = candidate_cases.get(case_id)
        if before_case is None or after_case is None:
            cases.append(
                {
                    "case_id": case_id,
                    "status": "added" if before_case is None else "removed",
                }
            )
            continue

        before_report = baseline.comparisons.get(case_id)
        after_report = candidate.comparisons.get(case_id)
        if before_report is None or after_report is None:
            raise CampaignDeltaError(
                f"case {case_id!r} is missing a loaded comparison report"
            )

        transitions = _transitions(before_report, after_report)
        for item in transitions:
            change = item["change"]
            if change in totals:
                totals[change] += 1

        before_counts = _counts(before_case.get("counts"))
        after_counts = _counts(after_case.get("counts"))
        cases.append(
            {
                "case_id": case_id,
                "status": "compared",
                "baseline": {
                    "extraction_status": before_case.get("extraction_status"),
                    "functional_verdict": before_case.get("functional_verdict"),
                    "counts": before_counts,
                },
                "candidate": {
                    "extraction_status": after_case.get("extraction_status"),
                    "functional_verdict": after_case.get("functional_verdict"),
                    "counts": after_counts,
                },
                "count_delta": _count_delta(before_counts, after_counts),
                "dimensions": _dimension_delta(before_report, after_report),
                "classification_transitions": transitions,
            }
        )

    return {
        "campaign_delta_schema_version": "1.0",
        "baseline": _summary_identity(baseline.summary),
        "candidate": _summary_identity(candidate.summary),
        "transition_totals": totals,
        "cases": cases,
        "policy": {
            "aggregate_quality_score": False,
            "error_resolution": (
                "critical_error/noncritical_error -> match only; ambiguity transitions "
                "remain explicit and are not called resolutions"
            ),
        },
    }


def render_campaign_delta_markdown(report: dict[str, Any]) -> str:
    """Render a concise human-readable before/after report."""

    lines = [
        "# Reader benchmark campaign delta",
        "",
        "No aggregate quality score. Count changes never validate Gate 1 by themselves.",
        "",
        f"Baseline Reader: `{report['baseline'].get('reader_commit')}`",
        f"Candidate Reader: `{report['candidate'].get('reader_commit')}`",
        f"Baseline benchmark: `{report['baseline'].get('benchmark_commit')}`",
        f"Candidate benchmark: `{report['candidate'].get('benchmark_commit')}`",
        "",
        "## Classification transitions",
        "",
    ]
    totals = report["transition_totals"]
    for key in (
        "error_resolved",
        "new_error",
        "ambiguity_transition",
        "classification_changed",
        "new_check",
        "removed_check",
    ):
        lines.append(f"- {key}: {totals.get(key, 0)}")

    for case in report["cases"]:
        lines.extend(["", f"## {case['case_id']}", ""])
        if case.get("status") != "compared":
            lines.append(f"Case status: **{case.get('status')}**")
            continue
        lines.append(
            "Verdict: "
            f"**{case['baseline'].get('functional_verdict')}** -> "
            f"**{case['candidate'].get('functional_verdict')}**"
        )
        lines.append(
            "Extraction: "
            f"**{case['baseline'].get('extraction_status')}** -> "
            f"**{case['candidate'].get('extraction_status')}**"
        )
        lines.extend(
            [
                "",
                "| Classification | Baseline | Candidate | Delta |",
                "|---|---:|---:|---:|",
            ]
        )
        before = case["baseline"]["counts"]
        after = case["candidate"]["counts"]
        delta = case["count_delta"]
        for key in sorted(set(before) | set(after)):
            lines.append(
                f"| {key} | {before.get(key, 0)} | {after.get(key, 0)} | "
                f"{delta.get(key, 0):+d} |"
            )
        transitions = case["classification_transitions"]
        if transitions:
            lines.extend(["", "### Changed checks", ""])
            for item in transitions:
                lines.append(
                    f"- {item['change']} — {item['dimension']} — "
                    f"`{item['reference_path']}`: "
                    f"{item['baseline_classification']} -> "
                    f"{item['candidate_classification']}"
                )
    return "\n".join(lines) + "\n"
