# Blueprint harness

Browser sweeps that produce every screenshot, output file and number in the blueprint
(`docs/blueprint/<project>-blueprint.html`, published at <ARTIFACT URL>).
They drive the real app in Chrome (Playwright) against the dev server and write raw evidence to
`blueprint-out/` (gitignored; override with `BP_OUT=/path`, and the app with `APP_URL=...`).

| Script | What it checks and captures |
|---|---|
| `sweep.mjs` | every UI state, the output matrix, performance, edge cases, phone width |
| `exports.mjs` | real outputs through the real UI, verified with an external tool |
| `<feature>.mjs` | one script per feature pass |

Run them one after another (never in parallel; perf numbers skew and logs clobber):

```sh
npm run dev &
for s in sweep <feature> exports; do node tools/blueprint/$s.mjs || echo "$s FAILED"; done
```

Each script prints its fresh `blueprint-out/data/report-<script>-<run>.json` path
({checks, perf, errors, screenshots}) and exits non-zero on any failed check.
Images live under `ui/<run>/`; repeat runs preserve the before report and images.
Read the printed report path instead of guessing or using a stale fixed-name report.

Visual passes are not done after the tests: capture real PNGs, build contact sheets with the
Blueprint skill's `scripts/visual_evidence.py <report.json>`, actually open the images, and
record image-bound findings. Fix only authorized product issues, then capture matched after
states and compare with `--baseline <before-report.json>`. `visualReview: pending` means the
visual review has not happened; it is not a green result.
