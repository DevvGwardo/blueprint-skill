import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import visual_blueprint
import visual_evidence
from test_visual_evidence import fixture


class WorkflowTests(unittest.TestCase):
    def test_capture_result_requires_fresh_successful_repo_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            report = repo / "blueprint-out/data/fresh.json"
            output = "Vite diagnostic\n" + json.dumps({"status": "captured", "report": str(report)})
            self.assertEqual(visual_blueprint.captured_report(output, repo), report.resolve())
            for status, target in [("failed", report), ("captured", repo / "elsewhere.json")]:
                with self.assertRaises(ValueError):
                    visual_blueprint.captured_report(json.dumps({"status": status, "report": str(target)}), repo)

    def test_manual_workflow_keeps_review_pending_and_preserves_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = fixture(root, "manual")
            before = report.read_bytes()
            args = SimpleNamespace(repo=None, report=report, reviewer="manual", review_json=None,
                                   baseline=None, previous_review=None, label="manual")
            result = visual_blueprint.workflow(args)
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(result["visualReview"], "pending")
            self.assertEqual(report.read_bytes(), before)
            self.assertTrue((Path(result["reviewDir"]) / "review-prompt.txt").exists())
            self.assertTrue((Path(result["reviewDir"]) / "workflow.json").exists())
            args.review_dir = Path(result["reviewDir"])
            resumed = visual_blueprint.workflow(args)
            self.assertEqual(resumed["captureReport"], result["captureReport"])
            self.assertEqual(report.read_bytes(), before)
            (args.review_dir / "visual-review.json").write_text("{}")
            args.reviewer = "agy"
            with patch("visual_blueprint.shutil.which", return_value="/safe/agy"), patch("visual_blueprint.run") as provider:
                with self.assertRaisesRegex(ValueError, "already has an imported review"):
                    visual_blueprint.workflow(args)
                provider.assert_not_called()

    def test_tracking_never_marks_missing_or_unmatched_findings_resolved(self):
        previous = {"findings": [{"id": "V1", "key": "eyes"}, {"id": "V2", "key": "poses"}]}
        frame = {"id": "clip-test-0", "sha256": "a" * 64}
        current = {"visualReview": "reviewed", "findings": [], "rechecks": [
            {"key": "eyes", "status": "resolved", "imageIds": ["clip-test-0"], "reason": "Visible clear eye"}
        ]}
        with self.assertRaises(ValueError):
            visual_evidence.track_findings(current, previous, {frame["id"]: frame}, False)
        ledger = visual_evidence.track_findings(current, previous, {frame["id"]: frame}, True)
        self.assertEqual({x["key"]: x["status"] for x in ledger}, {"eyes": "resolved", "poses": "unverified"})
        current["visualReview"] = "partial"
        with self.assertRaises(ValueError):
            visual_evidence.track_findings(current, previous, {frame["id"]: frame}, True)

    def test_batch_reviews_require_full_coverage_and_keep_conflicts_unverified(self):
        base = {"visualReview": "reviewed", "findings": [], "reviewedSheets": ["a.png"], "rechecks": [
            {"key": "eyes", "status": "resolved", "imageIds": ["frame"], "reason": "Clear eye"}]}
        other = {**base, "reviewedSheets": ["b.png"], "rechecks": [
            {"key": "eyes", "status": "unverified", "imageIds": ["frame"], "reason": "Cannot judge"}]}
        with self.assertRaises(ValueError):
            visual_evidence.merge_reviews([base], {"a.png", "b.png"})
        merged = visual_evidence.merge_reviews([base, other], {"a.png", "b.png"})
        self.assertEqual(merged["rechecks"][0]["status"], "unverified")
        for raw in [{"status": "SUCCESS", "response": ""}, {"status": "SUCCESS", "response": "```json\n{\"visualReview\":"}]:
            with self.assertRaises(ValueError):
                visual_evidence.parse_response(raw)


if __name__ == "__main__":
    unittest.main()
