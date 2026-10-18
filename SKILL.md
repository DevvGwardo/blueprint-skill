---
name: blueprint
description: Build reproducible product and platform evidence reports.
version: 1.3.0
triggers:
  - blueprint
  - run it through the blueprint
  - run this through the blueprint
  - make a blueprint
  - update the blueprint
  - refresh the blueprint
  - blueprint pass
author: devgwardo
license: MIT
metadata:
  hermes:
    tags: [testing, evidence, screenshots, desktop]
    category: software-development
    related_skills: [cua-driver]
---

# Blueprint

A blueprint is two things that ship together:

1. **The harness** (in the repo, `tools/blueprint/`): scripts that drive the real thing and write raw
   evidence (screenshots, recordings, exported files, JSON reports of pass/fail checks and measurements)
   to a gitignored `blueprint-out/`.
2. **The report** (`docs/blueprint/<project>-blueprint.html` + `docs/blueprint/media/`), viewable locally
   and optionally published at a stable URL when the user requests publishing and a publisher is
   available. Every number, image and claim in it comes from the latest harness run. Nothing is
   estimated or copied from memory.

The point is trust: someone reading the page can see what the project does, how it's built, what was
tested and what failed, what got fixed, and what to do next. The repo can regenerate all of it.

If the user has earlier blueprints (other repos with `docs/blueprint/`), read one before writing a
new page and match its depth. The two flavours below describe what each kind contains.

## Agent compatibility and prerequisites

This skill works in Claude Code and Hermes Agent. Hermes loads it with `skill_view("blueprint")`;
use `terminal` for harness commands, `read_file` / `search_files` for repo evidence, and
`vision_analyze` for screenshot review when available. Other agents use their equivalent tools.
Resolve `scripts/`, `templates/`, and `references/` relative to this skill's installed directory.
Never assume Claude-only tools, a publisher, or another skill exists.

- Browser harness: the repo's Playwright dependency, Chrome, and an isolated app/test profile.
- Media helpers: Python + Pillow; ffmpeg for video helpers.
- Visual review: read [references/visual-improvement-loop.md](references/visual-improvement-loop.md).
  `scripts/visual_evidence.py` turns a capture report's PNGs into contact sheets, inspection
  crops, sampled animation GIFs, and matched before/after comparisons.
  `scripts/visual_blueprint.py` runs capture→gallery→opt-in review→finding history in one command.
  Manual review stays pending and exits 2; it never silently becomes a visual pass.
- Native desktop windows (optional): any screenshot driver that can target an exact
  `(pid, window_id)`, such as `cua-driver`. Run it on the host
  machine, not inside a VM/container.

Do not clear a user's localStorage, pair accounts, send messages, upload screenshots, publish, or
take over their mouse/keyboard as part of a capture-only request. Use explicit, non-sensitive
fixtures. Model-based screenshot review sends pixels to that model's provider; review only
approved, non-sensitive images. Report unavailable capabilities as blocked, not passed.

## Visual improvement loop (required for anything with a UI or visual output)

**A source audit, green tests, preflight JSON, or "screenshots saved" is not a completed visual
Blueprint. Take images, open their pixels, use what they show, then re-capture.**

1. **Capture before changing the product.** Run the existing capture harness or build one. Capture
   meaningful states, errors/empty states, real-use sizes, themes, and context. For motion, sample
   its beginning, anticipation, peak, handoff, end, and settle, not just one attractive frame.
2. **Validate and index images.** Save fresh PNGs plus stable image IDs, source/fixture type,
   dimensions, input state, sample time, seed, and hashes. Decode images, reject empty/tampered
   evidence, and measure subject-specific checks. Missing screenshots are a failed capture,
   not a reason to ship a report without them. Start an isolated lab when one is available.
3. **Actually look.** Open every contact sheet and inspect the raw crop for anything suspicious.
   Use your own image reading, `vision_analyze`, or a bounded image-only model review (`agy`). Track which sheets/image IDs were
   reviewed; file metadata or model prose without image access never counts as visual review.
4. **Write actionable findings.** Each finding needs an image ID/time and hash, visible issue,
   impact, concrete proposed fix, and a re-capture/test that would verify it. Rank the top few.
   Distinguish subjective taste from measured bugs and label uncertain observations as candidates.
5. **Improve when authorized.** Choose one evidence-backed issue, make a scoped product change,
   run its tests, re-capture with identical inputs, and show BEFORE / AFTER / DIFF. A nonzero
   pixel diff means "changed", not "better". Read the images again before accepting the fix.
6. **Close the loop.** Record resolved/persistent/new findings and links to the actual image
   evidence. A text-only pass, partial review, or unverified after-state stays incomplete.

When the request is only to improve this skill, implement and validate the capture/review workflow
and report its findings; do not silently redesign the user's product. If capture genuinely cannot
run, report exactly what was tried and blocked. Never replace real images with generated artwork.

## Pick the mode

| The user says | Mode | What you do |
|---|---|---|
| "make a blueprint for X" (none exists) | **Bootstrap** | Inventory → build the harness → full run → write + publish the report |
| "run <feature> through the blueprint" / "tackle it … run it through the blueprint" | **Feature pass** | Add a harness script for the feature → run it *and* the existing sweeps (regressions) → fix what it finds → add a section to the report → republish at the same URL |
| "update / refresh the blueprint" | **Refresh** | Re-run every script, re-measure every number, drop stale claims, republish |

Always check first whether a blueprint exists: inspect `tools/blueprint/`, `docs/blueprint/`, and
their README for a saved URL. If Artifact tools are available, also list titles containing
"Blueprint". If one exists, you're in feature-pass or refresh mode. A repo can have separate
mobile, desktop, or subsystem reports; update the report owning this feature, not a duplicate.

## Pick the flavour (or mix them)

- **Product** (anything with a UI or an output: web apps, editors, games, generators). Evidence comes
  from driving the real app with Playwright in real Chrome: UI states, a render/output matrix, exports
  checked by an independent tool (ffprobe, file parsers), perf, edge cases, phone width, a recorded walkthrough.
- **Platform audit** (services, monorepos, infra). Evidence comes from the repo and its history: LOC by
  area (excluding generated code), routes, tests, git growth, hot paths traced to file:line, security
  sweeps, flags. The core is a **findings ledger**: id, severity, effort, evidence anchor, concrete fix.
  Re-verify the highest-severity claims by hand before publishing.

## Repo layout (create it if missing)

```
tools/blueprint/
  README.md          # what each script does + how to run (template: templates/tools-README.md)
  sweep.mjs          # UI states, output matrix, perf, edge cases   (template: templates/sweep.mjs)
  <feature>.mjs      # one script per feature pass                   (template: templates/feature.mjs)
  exports.mjs        # real outputs through the real UI, verified by an external tool
  mobile.mjs, walk.mjs (optional: phone layout, walkthrough recording)
  # Native desktop evidence may use Python + cua-driver instead of a browser script.
blueprint-out/       # GITIGNORED raw evidence: ui/ render/ mp4/ data/ walk/
docs/blueprint/
  <project>-blueprint.html   # the report source (template: templates/blueprint.html)
  media/                     # curated, compressed evidence the page references (jpg, 540-wide mp4)
```

Add `blueprint-out` to `.gitignore`. The app needs a small **test hook** so scripts can read state and
set up fixtures without clicking through everything, e.g. `window.__app = { store, getEngine, makeFixture }`.
Say in a comment that it's for automation.

## Harness rules (these come from bugs we actually hit)

- **One `check(name, ok, detail)` per promise**, pushed into a report object that's written to
  `blueprint-out/data/report-<script>-<run>.json`. Preserve each run's report/images and print its
  exact fresh report path; never overwrite before-evidence during recapture.
  Word the name as the behaviour a user relies on ("One drag =
  one undo step"). The detail holds the measured value. Exit non-zero if any check fails.
- **Real browser, clean isolated state**: `chromium.launch({ channel: "chrome" })`, clear localStorage only
  in a disposable browser context/test profile, reload, then
  wait for an app-ready condition (never a bare sleep). Collect `console.error` and `pageerror`, and add
  a final "No console errors" check.
- **Load explicit fixtures.** Don't depend on the app's default state. When one app's default template
  changed, a sweep that clicked `.block.move.nth(2)` broke silently for weeks.
- **Don't shadow globals in the scripts.** `const URL = "http://…"` after `new URL(..., import.meta.url)`
  is a TDZ crash. Use `APP_URL` / `BP_OUT` env overrides.
- **Run the scripts one after another, never overlapping** (a background chain: `a && b && c`). Two
  browsers at once skew the perf numbers and clobber logs.
- **Verify outputs independently.** Probe exported files (ffprobe: codec, size, exact frame count) and
  compare a decoded frame against the app's own render (mean abs diff under a small threshold). Exclude
  layers the raw render doesn't draw (captions, overlays) from the comparison, or composite them first;
  when a diff fails, map *where* it differs before touching the threshold.
- **Measure what the feature promises, geometrically when you can.** "The can is at the mouth" became a check
  comparing the can's top and bottom distances to the mouth; it caught a pose that looked plausible in
  thumbnails but was side-on. Same for "stays in the paw" (distance to the bone every frame).
- **Visual matrix for anything that renders.** Screenshots prove nothing on their own; render the product
  across every axis a user can combine (content × camera/viewport × size × theme/look) and *measure* each
  frame: is the subject framed (project keypoints), unblocked (raycast from the camera), a sensible size,
  are important props visible, is the image blank/flat/crushed, does the camera see past the edge of the
  set (rays through a screen grid that hit nothing). Calibrate thresholds from the data, exempt what's
  intentional (a close-up crops arms by design) and say so. One reference harness renders
  176 move × angle frames in ~4 s.
- **Golden frames need deterministic inputs.** Keep ~30 reference frames in the repo and diff every run;
  normalise anything random (seed particle effects from stable ids, not ones templates regenerate) or
  the goldens drift on their own. Prove determinism by running twice: the second run must be 0/255.
- **Canvas / 3D apps**: get screen coordinates from the engine's own projection, and confirm by picking
  at that point before you click. Refresh the camera matrices before projecting, because the first frames
  after a mode switch can be stale.
- **Measure perf where users feel it**: fps while playing or interacting, cost of per-frame hot paths
  (e.g. pick on hover), time to first render, export speed. Put each number next to how it was measured.
- **Screenshots**: take them at deviceScaleFactor 2 into `blueprint-out/ui|render`, then downscale and
  compress them into `docs/blueprint/media` with `scripts/media.py` (contact sheets, before/after pairs,
  frame strips, 540-wide mp4s). For native windows, record the actual pixel dimensions and driver
  scale instead of claiming a forced 2× scale. Floating Electron windows require an exact native
  `(pid, window_id)` capture; a main-window/browser screenshot cannot prove they rendered.
- **Look at every screenshot yourself** before it goes in the report. The harness proves behaviour; your
  eyes catch layout bugs, clipped UI and ugly states. Use an image-capable tool/model, not a claim
  based on a file path or an agent's prose. Keep capture validity, visual review, and behavioural
  checks separate. That's how an edge-on wall drag bug was found that every check had passed.

## Feature pass, step by step

1. Read the feature's code and list every promise it makes: behaviours, limits, guard rails, persistence,
   undo, export/output, phone layout, perf.
2. Write `tools/blueprint/<feature>.mjs` from `templates/feature.mjs`, with one check per promise. Include
   the unhappy paths: clamping, refusals, locked items, junk in saved files, cancel/undo.
3. Run it. **A failing check is a finding, not a test to delete.** Decide whether the bug is in the product
   or the test, fix it, and log it for "Fixed in this pass" (issue / cause / fix). Keep going until it's green.
4. Run the existing sweeps too (`sweep`, `exports`, `mobile`) to catch regressions. Fix stale scripts, and
   say in the report that you fixed them.
5. Run the repo's own unit and e2e tests and the build. Their counts go on the status tiles.
6. Build media, then update the report (see below), then republish at the same URL.

## The report

**Before writing HTML, load `artifact-design` if available**, then start from `templates/blueprint.html`
(tokens, light/dark, TOC, KPI tiles, tables, roadmap cards, video grid). Give each project its own
identity from its own UI or brand (e.g. LED-counter KPI tiles for a playful app, the product's palette
for a platform audit).

Sections for the product flavour, in order (drop any that don't apply):
1. **Status**: eyebrow with project · blueprint · date (and commit), a one-line headline, a lede, and
   KPI tiles (checks passed, unit/e2e counts, outputs verified, console errors, key perf numbers).
2. **Watch it**: the hero output plus a recorded walkthrough.
3. **New in this pass** (feature pass): what shipped, a demo video, before/after, a UI tour, "how it
   works" bullets, and **honest limits**.
4. Target/reference gap table (match · close · gap), if there is a reference.
5. **Architecture**: a mermaid flowchart plus module cards (file path + one paragraph each).
6. Product tour: screenshots of every major state, each with a caption that says what to notice.
7. Library / output matrix (grids of everything the product can produce).
8. **Outputs**: a video grid plus a table of every exported file with the external probe's numbers.
9. **Test results**: a table of area · check · measured · result (all checks from all reports), then a
   perf table of measure · value · how it was measured.
10. **Fixed in this pass**: issue · cause · fix.
11. **Roadmap**: tiers P1/P2/P3, each item with evidence (point at a screenshot or check) · approach ·
    size (S/M/L). Mark shipped items `done`. End with a **"Not yet tested"** callout.
12. **Run & reproduce**: exact commands, including every harness script.

For the platform-audit flavour, use: at a glance (KPIs + severity bar + fix-first list), priority matrix
(severity × effort), system map (SVG), growth, codebase shape, one section per risky subsystem with
hot-path flows, security ledger, flags to decide, roadmap lanes (Now / Next / Later), a filterable
findings explorer, and corrections to older blueprints.

**Content rules**
- Every number is from this run. Update every count you touch (tile, table, run commands) so they agree.
- Show failures and limits plainly. A blueprint that only shows green is an advert.
- Remove or fix stale claims (e.g. a roadmap item that just shipped gets a `done` pill).
- Captions say what the reader should notice, not what the image is.
- Name files and functions in `code`, so a developer can jump from the page to the repo.

## Publishing

Publishing is optional and requires the user's permission. Without Artifact tools, deliver the
local HTML + media and exact viewing commands. Never fabricate an Artifact URL or substitute an
unrequested deployment. If the existing published source cannot be read, preserve the repo source
and flag the possible sync gap before a future publish.

- **First publish**: `Artifact` publish with `file_path` = the HTML, `files` = every media file
  (`{"media/x.jpg": "docs/blueprint/media/x.jpg", …}`), an `icon` (e.g. `blueprint`) and a one-sentence
  `description`. Write the returned URL into `tools/blueprint/README.md`.
- **Updating**: `Artifact read` the URL first. The published page can be newer than the repo copy.
  Build from the saved file it returns: strip the service's injected head wrapper and runtime scripts
  (mermaid runtime) so you're editing the source, and sync that source back into
  `docs/blueprint/<project>-blueprint.html`. Then publish with `url` = the same link and only the **new
  or changed** media in `files`. Files you leave out are kept.
- Give the user the link, the checks passed/total, and what the pass found and fixed.

## Helpers in this skill

- `templates/sweep.mjs`: a product sweep skeleton (ready check, UI states, output matrix, perf, edge
  cases, phone width, JSON report).
- `templates/feature.mjs`: a feature-pass skeleton (promise-per-check, unhappy paths, export compare).
- `templates/blueprint.html`: the report skeleton with every section above and themeable tokens.
- `templates/tools-README.md`: the README for `tools/blueprint/`.
- `scripts/media.py`: `sheet` (grid/contact sheet with labels), `pair` (before/after), `strip` (frames of
  a video at given times), `web` (screenshot → compressed jpg), `mp4` (re-encode to 540 wide with faststart).
- `scripts/visual_evidence.py`: validates image hashes/decoding, builds an inspection gallery,
  contact sheets, sampled GIFs, and matched baseline comparisons; emits an image-only agy prompt.
- `scripts/visual_blueprint.py`: one-command capture (via your own `--capture` script) or analysis of an existing report;
  explicit provider-review opt-in, matched comparisons, and source-bound finding history.
- `references/visual-improvement-loop.md`: the screenshot → review → findings → fix → re-capture
  workflow, with reproducible commands and clear completion gates.
