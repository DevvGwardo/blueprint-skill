#!/usr/bin/env python3
"""Capture/validate → gallery/compare → explicitly opted-in review → finding history."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import visual_evidence


def run(args, cwd, timeout):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed ({result.returncode}): {result.stderr[-2000:]} {result.stdout[-2000:]}")
    return result.stdout


def captured_report(output, repo):
    repo = repo.resolve()
    for line in reversed(output.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and result.get("report"):
            target = Path(result["report"]).resolve()
            if result.get("status") != "captured" or not target.is_relative_to(repo / "blueprint-out" / "data"):
                raise ValueError("Capture did not produce successful repo-local evidence")
            return target
    raise ValueError("Capture produced no structured result")


def workflow(args):
    repo = args.repo.resolve() if args.repo else None
    # Check prerequisites before running a expensive capture.
    if args.reviewer == "agy" and not shutil.which("agy"):
        raise ValueError("agy unavailable; use --reviewer manual")
    if args.previous_review and not args.baseline:
        raise ValueError("--previous-review requires its matched --baseline capture report")
    if getattr(args, "review_dir", None):
        out = args.review_dir.resolve()
        summary = json.loads((out / "evidence.json").read_text())
        report_path = Path(summary["captureReport"])
        visual_evidence.load_frames(report_path)
    elif args.report:
        report_path = args.report.resolve()
    else:
        if not shutil.which("node"):
            raise ValueError("Node unavailable")
        output = run(["node", str(args.capture.resolve()), "--repo", str(repo), "--label", args.label],
                     repo, 300)
        report_path = captured_report(output, repo)
    if not getattr(args, "review_dir", None):
        summary, out = visual_evidence.build(report_path, args.baseline.resolve() if args.baseline else None)
    elif args.baseline and summary.get("baselineCaptureReport") != str(args.baseline.resolve()):
        raise ValueError("Resume baseline differs from the existing comparison")
    if (out / "visual-review.json").exists():
        raise ValueError("This capture already has an imported review; preserve it instead of overwriting or spending another model call")
    previous = args.previous_review.resolve() if args.previous_review else None
    prompt = visual_evidence.review_prompt(out, previous)
    (out / "review-prompt.txt").write_text(prompt)
    result = {"status": "review_pending", "captureReport": str(report_path), "reviewDir": str(out),
              "gallery": str(out / "index.html"), "images": summary["imageCount"],
              "sheets": len(summary["assets"]), "visualReview": "pending"}
    try:
        response_path = args.review_json.resolve() if args.review_json else None
        if args.reviewer == "agy":
            # This flag is the explicit opt-in to provider-backed image review, never capture.
            attempt = out / f"review-attempt-{uuid4()}"
            attempt.mkdir()
            (attempt / "review-prompt.txt").write_text(prompt)
            responses = []
            for index in range(0, len(summary["assets"]), 10):
                assets = summary["assets"][index:index + 10]
                batch_prompt = visual_evidence.review_prompt(out, previous, assets)
                raw = run(["agy", "--model", args.model, "--add-dir", str(out),
                           "--print-timeout", "240s", "--output-format", "json", "-p", batch_prompt],
                          repo or report_path.parent, 270)
                batch_path = attempt / f"agy-response-{index // 10:02d}.json"
                batch_path.write_text(raw)
                response = visual_evidence.parse_response(json.loads(raw))
                if set(response.get("reviewedSheets", [])) != {asset["sheet"] for asset in assets}:
                    raise ValueError(f"Batch {index // 10} did not review its exact assigned sheets")
                responses.append(response)
            response_path = attempt / "agy-response-merged.json"
            response_path.write_text(json.dumps(visual_evidence.merge_reviews(
                responses, {asset["sheet"] for asset in summary["assets"]}), indent=2))
        if response_path:
            review, target = visual_evidence.import_review(response_path, out, previous)
            result.update(visualReview=review["visualReview"], review=str(target),
                          findings=len(review["findings"]), tracking=review.get("tracking", []))
            result["status"] = "reviewed" if review["visualReview"] == "reviewed" else "review_incomplete"
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        result.update(status="review_blocked", visualReview="blocked", error=str(error))
    (out / "workflow.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    capture = parser.add_mutually_exclusive_group(required=True)
    capture.add_argument("--repo", type=Path, help="Absolute repo path; runs --capture against it")
    capture.add_argument("--report", type=Path, help="Existing fresh capture report, including general browser UI")
    capture.add_argument("--review-dir", type=Path, help="Resume a blocked/pending review without recapturing or replacing images")
    parser.add_argument("--capture", type=Path, help="Node capture script called as `node SCRIPT --repo REPO --label LABEL`; "
                        "its last stdout line must be JSON {status: captured, report: <repo>/blueprint-out/data/...}")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--previous-review", type=Path)
    review = parser.add_mutually_exclusive_group()
    review.add_argument("--reviewer", choices=["manual", "agy"], default="manual",
                        help="agy explicitly sends approved fixture images to its model provider")
    review.add_argument("--review-json", type=Path, help="Import an already completed image review")
    parser.add_argument("--model", default="gemini-3.8-flash-medium")
    args = parser.parse_args()
    if args.repo and not args.repo.is_absolute():
        parser.error("--repo must be absolute")
    if args.repo and not args.capture:
        parser.error("--repo requires --capture")
    try:
        result = workflow(args)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}))
        return 1
    print(json.dumps(result))
    return 0 if result["status"] == "reviewed" else 2


if __name__ == "__main__":
    sys.exit(main())
