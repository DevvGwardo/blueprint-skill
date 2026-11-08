import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
import visual_blueprint
import visual_evidence
from test_visual_evidence import fixture


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.finding = {
            "id": "V1", "key": "clip-first-subject", "severity": "medium",
            "imageIds": ["clip-test-0"], "observation": "Synthetic visible clipping",
            "proposedFix": "Adjust bounds", "verification": "Recapture first frame",
        }

    def response(self, name, summary, findings=None, status="reviewed", rechecks=None):
        path = self.root / f"{name}-response.json"
        path.write_text(json.dumps({
            "visualReview": status, "findings": findings or [], "rechecks": rechecks or [],
            "reviewedSheets": [asset["sheet"] for asset in summary["assets"]],
        }))
        return path

    def args(self, **changes):
        values = dict(repo=None, report=None, review_dir=None, reviewer="manual",
                      review_json=None, baseline=None, previous_review=None, label="test")
        return SimpleNamespace(**{**values, **changes})

    def replace_source(self, report, update_report=True):
        data = json.loads(report.read_text())
        entry = data["screenshots"][0]
        image = Image.new("RGB", (80, 60), "navy")
        ImageDraw.Draw(image).rectangle((5, 5, 30, 30), fill="red")
        image.save(entry["path"])
        if update_report:
            entry["sha256"] = hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
            report.write_text(json.dumps(data))

    def test_replaced_source_and_rewritten_manifest_cannot_rebind_review(self):
        report = fixture(self.root, "binding")
        summary, out = visual_evidence.build(report)
        self.replace_source(report)
        response = self.response("binding", summary, [self.finding])
        with self.assertRaises(ValueError):
            visual_evidence.import_review(response, out)
        with self.assertRaises(ValueError):
            visual_blueprint.workflow(self.args(review_dir=out))
        self.assertFalse((out / "visual-review.json").exists())

    def test_source_only_and_report_only_changes_are_rejected(self):
        for source_only in (True, False):
            with self.subTest(source_only=source_only):
                report = fixture(self.root, f"mutation-{source_only}")
                summary, out = visual_evidence.build(report)
                if source_only:
                    self.replace_source(report, update_report=False)
                else:
                    report.write_text(report.read_text() + "\n")
                with self.assertRaises(ValueError):
                    visual_evidence.import_review(self.response(str(source_only), summary), out)

    def test_rewritten_baseline_is_rejected(self):
        before = fixture(self.root, "baseline")
        after = fixture(self.root, "after", changed=True)
        summary, out = visual_evidence.build(after, before)
        self.replace_source(before)
        with self.assertRaises(ValueError):
            visual_evidence.import_review(self.response("after", summary), out)

    def test_legacy_unbound_evidence_blocks_import_and_provider_review(self):
        report = fixture(self.root, "legacy")
        summary, out = visual_evidence.build(report)
        summary.pop("captureBinding", None)
        (out / "evidence.json").write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "binding"):
            visual_evidence.import_review(self.response("legacy", summary), out)
        with patch("visual_blueprint.shutil.which", return_value="/safe/agy"), \
             patch("visual_blueprint.run") as provider:
            with self.assertRaisesRegex(ValueError, "binding"):
                visual_blueprint.workflow(self.args(review_dir=out, reviewer="agy"))
            provider.assert_not_called()

    def test_partial_and_blocked_attempts_resume_to_immutable_complete_review(self):
        report = fixture(self.root, "resumable")
        initial = visual_blueprint.workflow(self.args(report=report))
        out = Path(initial["reviewDir"])
        summary = json.loads((out / "evidence.json").read_text())
        attempts = []
        for status in ("partial", "blocked"):
            result = visual_blueprint.workflow(self.args(
                review_dir=out, review_json=self.response(status, summary, status=status)))
            self.assertEqual(result["status"], "review_incomplete")
            attempts.append(Path(result["review"]))
            self.assertTrue(attempts[-1].exists())
            self.assertFalse((out / "visual-review.json").exists())
        self.assertNotEqual(*attempts)
        preserved = {path: path.read_bytes() for path in attempts}
        complete = self.response("complete", summary)
        result = visual_blueprint.workflow(self.args(review_dir=out, review_json=complete))
        self.assertEqual(result["status"], "reviewed")
        final = out / "visual-review.json"
        self.assertEqual(Path(result["review"]), final)
        self.assertIn('href="visual-review.html"', (out / "index.html").read_text())
        final_bytes = final.read_bytes()
        with self.assertRaises(FileExistsError):
            visual_evidence.import_review(complete, out)
        self.assertEqual(final.read_bytes(), final_bytes)
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content)

    def test_full_unverified_records_survive_generations_until_explicit_resolution(self):
        previous_report = previous_review = None
        for index in range(4):
            report = fixture(self.root, f"history-{index}", changed=index > 0)
            summary, out = visual_evidence.build(report, previous_report)
            findings = [self.finding] if index == 0 else []
            rechecks = [{"key": self.finding["key"], "status": "resolved",
                         "imageIds": ["clip-test-0"], "reason": "Explicit image recheck"}] if index == 3 else []
            if index in (2, 3):
                prompt = visual_evidence.review_prompt(out, previous_review)
                self.assertIn(self.finding["key"], prompt)
                self.assertIn(self.finding["observation"], prompt)
            review, target = visual_evidence.import_review(
                self.response(f"history-{index}", summary, findings, rechecks=rechecks),
                out, previous_review)
            if index in (1, 2):
                issue = review["tracking"][0]
                self.assertEqual(issue["status"], "unverified")
                for key, value in self.finding.items():
                    self.assertEqual(issue[key], value)
                self.assertTrue(issue["imageHashes"])
            if index == 3:
                self.assertEqual(review["tracking"][0]["status"], "resolved")
                next_report = fixture(self.root, "history-closed", changed=True)
                _, next_out = visual_evidence.build(next_report, report)
                self.assertNotIn(self.finding["key"], visual_evidence.review_prompt(next_out, target))
            previous_report, previous_review = report, target

    def test_legacy_tracking_recovers_full_records_from_previous_review_chain(self):
        before = fixture(self.root, "legacy-history-before")
        summary, out = visual_evidence.build(before)
        _, first = visual_evidence.import_review(
            self.response("legacy-history-before", summary, [self.finding]), out)
        after = fixture(self.root, "legacy-history-after", changed=True)
        summary, out = visual_evidence.build(after, before)
        review, second = visual_evidence.import_review(
            self.response("legacy-history-after", summary), out, first)
        review["tracking"] = [{"key": self.finding["key"], "status": "unverified",
                               "previousId": "V1", "reason": "Legacy omitted finding"}]
        second.write_text(json.dumps(review))
        third = fixture(self.root, "legacy-history-third", changed=True)
        summary, out = visual_evidence.build(third, after)
        self.assertIn(self.finding["observation"], visual_evidence.review_prompt(out, second))
        review, _ = visual_evidence.import_review(
            self.response("legacy-history-third", summary), out, second)
        self.assertEqual(review["tracking"][0]["observation"], self.finding["observation"])

    def test_importer_owns_history_metadata_not_the_reviewer(self):
        summary, out = visual_evidence.build(fixture(self.root, "owned-history"))
        response = self.response("owned-history", summary)
        data = json.loads(response.read_text())
        data.update(tracking=[{"key": "invented", "status": "resolved"}],
                    previousReview="/not-an-approved-history.json")
        response.write_text(json.dumps(data))
        review, _ = visual_evidence.import_review(response, out)
        self.assertNotIn("tracking", review)
        self.assertNotIn("previousReview", review)

    def test_rechecks_preserve_full_issue_records_and_closed_issues_leave_active_history(self):
        previous = {"findings": [self.finding]}
        frame = {"id": "clip-test-0", "sha256": "a" * 64}
        for status in ("resolved", "dismissed"):
            response = {"visualReview": "reviewed", "findings": [], "rechecks": [{
                "key": self.finding["key"], "status": status, "imageIds": [frame["id"]],
                "reason": "Explicit recheck", "observation": "Untrusted replacement",
                "id": "Untrusted replacement",
            }]}
            ledger = visual_evidence.track_findings(response, previous, {frame["id"]: frame}, True)
            self.assertEqual(ledger[0]["observation"], self.finding["observation"])
            self.assertEqual(ledger[0]["id"], self.finding["id"])
            self.assertEqual(visual_evidence.active_findings({"findings": [], "tracking": ledger}), {})

    def test_unrecoverable_or_cyclic_legacy_history_is_blocked(self):
        previous = {"findings": [], "tracking": [
            {"key": self.finding["key"], "status": "unverified"}]}
        with self.assertRaisesRegex(ValueError, "legacy finding history"):
            visual_evidence.active_findings(previous)
        path = self.root / "cycle.json"
        previous["previousReview"] = str(path)
        path.write_text(json.dumps(previous))
        with self.assertRaisesRegex(ValueError, "legacy finding history"):
            visual_evidence.active_findings(previous)

    def test_import_lock_prevents_overlap_and_is_released_after_validation_errors(self):
        summary, out = visual_evidence.build(fixture(self.root, "locked"))
        response = self.response("locked", summary)
        lock = out / ".review-import.lock"
        lock.write_text("another import")
        with self.assertRaises(FileExistsError):
            visual_evidence.import_review(response, out)
        self.assertEqual(lock.read_text(), "another import")
        lock.unlink()
        response.write_text("not JSON")
        with self.assertRaises(ValueError):
            visual_evidence.import_review(response, out)
        self.assertFalse(lock.exists())
        visual_evidence.import_review(self.response("locked", summary), out)


if __name__ == "__main__":
    unittest.main()
