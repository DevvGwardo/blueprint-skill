import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
import visual_evidence


def fixture(root, name, changed=False):
    report = {"run": name, "status": "captured", "character": "fixture",
              "method": {"clock": "manual"}, "screenshots": []}
    for index in range(2):
        path = root / f"{name}-{index}.png"
        image = Image.new("RGB", (80, 60), "black")
        ImageDraw.Draw(image).rectangle((index * 10 + 5, 5, 30, 30),
                                       fill="red" if changed else "white")
        image.save(path)
        report["screenshots"].append({
            "id": f"clip-test-{index}", "group": "clip-test", "kind": "clip",
            "timeMs": index * 200, "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    target = root / "data" / f"{name}.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report))
    return target


class EvidenceTests(unittest.TestCase):
    def test_validated_pixels_build_motion_and_matched_comparisons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = fixture(root, "before")
            after = fixture(root, "after", changed=True)
            summary, out = visual_evidence.build(after, before)
            self.assertEqual(summary["imageCount"], 2)
            self.assertEqual(summary["motion"][0]["uniqueFrames"], 2)
            self.assertEqual(summary["visualReview"], "pending")
            self.assertTrue(all(x["meanAbsoluteDiff255"] > 0 for x in summary["comparisons"]))
            self.assertTrue((out / "index.html").exists())
            gif = Path(summary["assets"][0]["sampledGif"])
            with Image.open(gif) as image:
                self.assertEqual(image.n_frames, 2)
            for asset in summary["assets"]:
                self.assertTrue(Path(asset["sheet"]).exists())
            baseline = json.loads(before.read_text())
            baseline["method"]["clock"] = "different"
            before.write_text(json.dumps(baseline))
            with self.assertRaises(ValueError):
                visual_evidence.build(fixture(root, "mismatch"), before)
            self.assertFalse((root / "review" / "mismatch").exists())

    def test_preflight_tampered_duplicate_and_blank_images_are_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty.json"
            empty.write_text('{"status":"captured","screenshots":[]}')
            with self.assertRaises(ValueError):
                visual_evidence.load_frames(empty)
            path = fixture(root, "test")
            data = json.loads(path.read_text())
            first = Path(data["screenshots"][0]["path"])
            first.write_bytes(b"not a PNG")
            with self.assertRaises(ValueError):
                visual_evidence.load_frames(path)
            Image.new("RGB", (80, 60), "black").save(first)
            data["screenshots"][0]["sha256"] = hashlib.sha256(first.read_bytes()).hexdigest()
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                visual_evidence.load_frames(path)
            path = fixture(root, "duplicate")
            data = json.loads(path.read_text())
            data["screenshots"][1]["id"] = data["screenshots"][0]["id"]
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                visual_evidence.load_frames(path)

    def test_review_requires_known_sheets_and_hash_bound_actionable_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, out = visual_evidence.build(fixture(root, "review"))
            response = {
                "visualReview": "reviewed", "reviewedSheets": [x["sheet"] for x in summary["assets"]],
                "findings": [{"id": "V1", "severity": "low", "imageIds": ["clip-test-0"],
                              "observation": "Visible issue", "proposedFix": "Bounded fix",
                              "verification": "Matched recapture"}],
            }
            raw = root / "agy.json"
            raw.write_text(json.dumps({"status": "SUCCESS", "denied_actions": ["read_file"]}))
            with self.assertRaises(ValueError):
                visual_evidence.import_review(raw, out)
            for key, value in [("reviewedSheets", []), ("reviewedSheets", ["unknown.png"])]:
                invalid = {**response, key: value}
                raw.write_text(json.dumps({"status": "SUCCESS", "response": json.dumps(invalid)}))
                with self.assertRaises(ValueError):
                    visual_evidence.import_review(raw, out)
            invalid = {**response, "findings": [{**response["findings"][0], "imageIds": ["invented"]}]}
            raw.write_text(json.dumps({"status": "SUCCESS", "response": json.dumps(invalid)}))
            with self.assertRaises(ValueError):
                visual_evidence.import_review(raw, out)
            raw.write_text(json.dumps({"status": "SUCCESS", "response": json.dumps(response)}))
            result, path = visual_evidence.import_review(raw, out)
            self.assertEqual(result["visualReview"], "reviewed")
            self.assertEqual(result["findings"][0]["status"], "candidate")
            self.assertEqual(len(result["findings"][0]["imageHashes"]["clip-test-0"]), 64)
            self.assertTrue(path.exists())
            self.assertTrue((out / "visual-review.html").exists())
            self.assertIn("visual-review.html", (out / "index.html").read_text())
            with self.assertRaises(FileExistsError):
                visual_evidence.import_review(raw, out)
            partial_summary, partial_out = visual_evidence.build(fixture(root, "partial"))
            partial = {**response, "visualReview": "partial",
                       "reviewedSheets": [partial_summary["assets"][0]["sheet"]]}
            raw.write_text(json.dumps({"status": "SUCCESS", "response": json.dumps(partial)}))
            result, _ = visual_evidence.import_review(raw, partial_out)
            self.assertEqual(result["visualReview"], "partial")
            self.assertIn("Visual review: partial", (partial_out / "index.html").read_text())

    def test_measurements_validate_crops_dimensions_and_review_sheet_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = fixture(root, "metrics")
            report = json.loads(target.read_text())
            for frame in report["screenshots"]:
                frame.update(kind="pose", theme="dark", subjectRegions=[
                    {"sizeCssPx": 24, "x": 0, "y": 0, "width": 80, "height": 60}])
            target.write_text(json.dumps(report))
            summary, out = visual_evidence.build(target)
            self.assertEqual(len(summary["measurements"]["subjects"]), 2)
            self.assertEqual(len(summary["measurements"]["poseSimilarity"]), 1)
            reviewed = [x["sheet"] for x in summary["assets"]]
            raw = root / "review.json"
            raw.write_text(json.dumps({"visualReview": "reviewed", "reviewedSheets": reviewed, "findings": []}))
            Path(reviewed[0]).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                visual_evidence.import_review(raw, out)
            report["screenshots"][0]["width"] = 999
            target.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                visual_evidence.load_frames(target)


if __name__ == "__main__":
    unittest.main()
