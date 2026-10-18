# Visual Blueprint: capture → inspect → improve → compare

Use this for every UI, mascot, animation, chart, canvas, game, or rendered output. A blueprint
that cannot show what it tested is incomplete. Platform-only audits may omit visuals when the
system genuinely has no visual output.

## Choose the right target

Reuse the project's existing harness and production rendering engine. Don't draw a look-alike.
For general web/app work, extend `templates/sweep.mjs` / `templates/feature.mjs` to capture
the actual state/viewport combinations, index those images, and visually review them.
If something has a headless lab (a component story, an engine test page), capture it there
instead of waiting on a native window or a screen-recording grant.

Run capture jobs one after another. Bind any private lab server to loopback, block nonlocal
browser requests, use a clean headless context, and tear down only your own server/browser.

## The capture report

Every capture script writes a fresh `blueprint-out/data/report-<run>.json` and prints its path
(the last stdout line can be `{"status": "captured", "report": "<path>"}`). The helpers expect:

```json
{
  "run": "ui-before-<uuid>",
  "status": "captured",
  "character": "optional subject label; baselines must match it",
  "method": {"viewport": "1280x800", "dpr": 2},
  "screenshots": [
    {"id": "settings-empty", "group": "settings", "kind": "state",
     "timeMs": 0, "path": "/abs/blueprint-out/ui/<run>/settings-empty.png", "sha256": "…"}
  ]
}
```

A report without screenshots is a preflight, not visual evidence. A failed capture keeps its
partial images but never counts as complete coverage.

## One command (preferred)

```sh
python3 /absolute/blueprint/scripts/visual_blueprint.py \
  --report /absolute/repo/blueprint-out/data/report-<run>.json
```

Or let it run your capture script first (`node SCRIPT --repo REPO --label LABEL`):

```sh
python3 /absolute/blueprint/scripts/visual_blueprint.py \
  --repo /absolute/repo --capture /absolute/repo/tools/blueprint/capture.mjs --label before
```

Without a reviewer, capture and gallery still run, the review prompt is saved, and exit
**2** means **review pending**, not failure of the capture or a completed visual pass.
Exit 0 requires an imported complete review; denial/empty output/partial coverage stays blocked.

`--reviewer agy` is the explicit opt-in to send these approved, non-sensitive images to a
model provider through the `agy` CLI (`--model` picks the model). Model review runs sequential
batches of at most ten sheets, preserves every raw response, and requires exact
assigned-sheet coverage before merging. Conflicting rechecks stay unverified (or persistent
when the issue is still reported), never optimistically resolved.

To resume a pending/blocked review without recapture:

```sh
python3 /absolute/blueprint/scripts/visual_blueprint.py \
  --review-dir /absolute/after-review --reviewer agy \
  --baseline /absolute/before-report.json \
  --previous-review /absolute/before-review/visual-review.json
```

Omit baseline/history flags for a first-pass review. Attempts get unique response directories;
capture manifests and PNGs are never replaced. A malformed response stays blocked, even
when the CLI exits zero. Do not recapture merely because a model returned truncated JSON.

## The gallery

```sh
python3 /absolute/blueprint/scripts/visual_evidence.py /absolute/repo/blueprint-out/data/report-<run>.json
```

This validates every image (decodes it, checks its hash) and prints the fresh review directory.
Open its `index.html` locally, or open the contact sheets with your image tool. It holds
per-group contact sheets, sampled GIFs for timed sequences, nearest-neighbour inspection
zooms (labelled as zooms), raw PNGs, hashes, and coverage checks.

The counts come from the current run's report, not a fixed promise in this document.
Fixture captures are not proof that the native app integration works; test that separately
when a finding touches that boundary.

## Have a model look at the captured images

Capture uses fixed inputs first. Don't ask a model to figure out how to screenshot
before giving it any pixels. Give it a bounded **analysis-only** handoff:

```sh
PROMPT="$(python3 /absolute/blueprint/scripts/visual_evidence.py \
  --print-agy-prompt /absolute/repo/blueprint-out/review/<run>)"
cd /absolute/repo && agy --model <model> \
  --add-dir /absolute/repo/blueprint-out/review/<run> \
  --print-timeout 180s --output-format json -p "$PROMPT"
```

The prompt works with any image-capable agent; `agy` is just the one the helper can drive.
Use only approved non-sensitive captures: the model receives those pixels at its provider.
This needs image/file reading, not shell commands or writes. Do not add blanket permissions
or `--dangerously-skip-permissions`. If image reading is denied or unavailable, mark the
review blocked.

Save the raw response separately from the capture manifest. Read denied actions, empty
output, and `reviewedSheets`, not just exit zero / `status: SUCCESS`. Import it with the
evidence helper to check that returned sheets and finding image IDs belong to this run:

```sh
python3 /absolute/blueprint/scripts/visual_evidence.py \
  --import-agy-review /absolute/response.json \
  --review-dir /absolute/repo/blueprint-out/review/<run>
```

Only mark all sheets reviewed when every expected sheet is explicitly included. Keep raw
capture evidence immutable; write visual-review results separately. The importer creates a
readable `visual-review.html` with the exact cited source frames and links it from the gallery.

## Findings that guide an actual improvement

Each finding records:

```text
id, severity, imageIds + hashes, observed problem, user impact,
proposed fix, verification, status (candidate / confirmed / resolved / persistent)
```

Look for unreadable states and labels, clipping and overlap, outlines swallowed by light/dark
backgrounds, misplaced attachments, broken empty/error/disabled states, layout that fails at
small sizes, start/peak/settle pose jumps, and misleadingly frozen sequences. Frozen-frame
detection is a review cue, not an automatic failure: some motion is intentionally quiet,
and reduced motion may barely move. Don't claim sampled frames prove unsampled timing,
smooth 60fps playback, or frame rate. Cross-check the code/contract before changing the
product: something hidden behind a mask may be hidden by design. Keep model findings as
candidates until verified, and don't let a model invent props from a blurry thumbnail.

### Finding history

Use stable semantic `key` values and pass `--previous-review`. Explicit rechecks cite current
image IDs/hashes and carry `resolved`, `persistent`, `dismissed`, or `unverified`; new findings
carry `new`. A previous finding absent from the next response remains **unverified**, never
automatically resolved. Resolution/dismissal requires a complete review with the actual
matched baseline. "Resolved" is a visual judgment, not proof of native integration or behaviour.
Legacy reviews without keys remain readable using their existing IDs.

## Matched re-capture and comparison

When the user asked for product improvements, pick the highest-impact **confirmed** finding,
fix it, and test that behaviour. Preserve the before report/images. Re-run the same capture
with `--label after` and otherwise identical inputs, then compare:

```sh
python3 /absolute/blueprint/scripts/visual_evidence.py \
  /absolute/repo/blueprint-out/data/report-<after-run>.json \
  --baseline /absolute/repo/blueprint-out/data/report-<before-run>.json
```

The helper rejects changed settings, unmatched IDs/times, dimension mismatches, and tampered
images. It measures pixel differences and writes BEFORE / AFTER / DIFF panels for changed
images. Read these panels and re-review the affected sequence. A changed image does not
automatically mean an improvement. New/removed states need a deliberately updated baseline,
with the coverage change reported, not silently matched by file order.

## Completion gates

1. Capture completed with actual decoded, fresh images and explicit source/coverage.
2. All sheets inspected, with image-bound findings or an explicit "no issues found".
3. Any product fix has matched after-captures, relevant passing tests, and visual re-review.
4. The report includes the images/GIFs, actual findings/fixes, reproducible commands, and limits.

A skill-only request completes at gates 1–2 plus tested capture/comparison plumbing; product
changes require explicit authorization. Never claim something "improved" merely because the
skill now takes screenshots. "We captured and found candidate improvements" is the honest outcome.
