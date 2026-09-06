import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from reader_benchmark.campaign_delta import (
    CampaignDeltaError,
    compare_campaigns,
    load_campaign,
    render_campaign_delta_markdown,
)


def comparison(case_id, checks):
    dimensions = {}
    counts = {}
    for check in checks:
        dimension = check["dimension"]
        classification = check["classification"]
        dimensions.setdefault(dimension, {})
        dimensions[dimension][classification] = (
            dimensions[dimension].get(classification, 0) + 1
        )
        counts[classification] = counts.get(classification, 0) + 1
    return {
        "case_id": case_id,
        "checks": checks,
        "dimensions": dimensions,
        "counts": counts,
    }


def write_campaign(root, *, reader, benchmark, verdict, checks, zip_name=None):
    case_id = "case_001"
    summary = {
        "campaign_id": f"campaign-{reader[:4]}",
        "reader_commit": reader,
        "benchmark_commit": benchmark,
        "gate1_validated": verdict == "PASS",
        "cases": [
            {
                "case_id": case_id,
                "extraction_status": "success",
                "functional_verdict": verdict,
                "counts": comparison(case_id, checks)["counts"],
            }
        ],
    }
    campaign_root = root / "campaign"
    (campaign_root / case_id).mkdir(parents=True)
    (campaign_root / "campaign-summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    (campaign_root / case_id / "comparison.json").write_text(
        json.dumps(comparison(case_id, checks)),
        encoding="utf-8",
    )
    if zip_name is None:
        return campaign_root
    archive = root / zip_name
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in campaign_root.rglob("*"):
            if path.is_file():
                bundle.write(path, Path("nested-results") / path.relative_to(campaign_root))
    return archive


class CampaignDeltaTests(unittest.TestCase):
    def test_compares_zip_campaigns_and_classifies_transitions(self):
        baseline_checks = [
            {
                "dimension": "presence",
                "reference_path": "/obs/1",
                "classification": "critical_error",
            },
            {
                "dimension": "unit",
                "reference_path": "/obs/2/unit",
                "classification": "match",
            },
            {
                "dimension": "structure",
                "reference_path": "/document",
                "classification": "ambiguity",
            },
        ]
        candidate_checks = [
            {
                "dimension": "presence",
                "reference_path": "/obs/1",
                "classification": "match",
            },
            {
                "dimension": "unit",
                "reference_path": "/obs/2/unit",
                "classification": "critical_error",
            },
            {
                "dimension": "structure",
                "reference_path": "/document",
                "classification": "match",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = write_campaign(
                root / "before",
                reader="a" * 40,
                benchmark="b" * 40,
                verdict="FAIL",
                checks=baseline_checks,
                zip_name="before.zip",
            )
            candidate = write_campaign(
                root / "after",
                reader="c" * 40,
                benchmark="d" * 40,
                verdict="FAIL",
                checks=candidate_checks,
                zip_name="after.zip",
            )

            report = compare_campaigns(
                load_campaign(baseline),
                load_campaign(candidate),
            )

        self.assertEqual(report["transition_totals"]["error_resolved"], 1)
        self.assertEqual(report["transition_totals"]["new_error"], 1)
        self.assertEqual(report["transition_totals"]["ambiguity_transition"], 1)
        case = report["cases"][0]
        self.assertEqual(case["count_delta"]["critical_error"], 0)
        self.assertEqual(case["count_delta"]["match"], 1)
        self.assertEqual(case["count_delta"]["ambiguity"], -1)
        self.assertFalse(report["policy"]["aggregate_quality_score"])

    def test_directory_campaign_is_supported(self):
        checks = [
            {
                "dimension": "presence",
                "reference_path": "/obs/1",
                "classification": "match",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = write_campaign(
                root,
                reader="a" * 40,
                benchmark="b" * 40,
                verdict="PASS",
                checks=checks,
            )
            evidence = load_campaign(campaign)

        self.assertEqual(evidence.summary["reader_commit"], "a" * 40)
        self.assertIn("case_001", evidence.comparisons)

    def test_missing_case_comparison_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "campaign-summary.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "missing",
                                "counts": {},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(CampaignDeltaError):
                load_campaign(root)

    def test_markdown_does_not_claim_aggregate_validation(self):
        checks = [
            {
                "dimension": "presence",
                "reference_path": "/obs/1",
                "classification": "critical_error",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = write_campaign(
                root / "before",
                reader="a" * 40,
                benchmark="b" * 40,
                verdict="FAIL",
                checks=checks,
            )
            after = write_campaign(
                root / "after",
                reader="c" * 40,
                benchmark="d" * 40,
                verdict="FAIL",
                checks=checks,
            )
            report = compare_campaigns(load_campaign(before), load_campaign(after))
            markdown = render_campaign_delta_markdown(report)

        self.assertIn("No aggregate quality score", markdown)
        self.assertNotIn("Gate 1 passed", markdown)


if __name__ == "__main__":
    unittest.main()
