// Blueprint sweep: UI states, output matrix, performance, edge cases, phone width.
// Copy to tools/blueprint/sweep.mjs and fill in the TODOs. Run with the dev server up:
//   node tools/blueprint/sweep.mjs            (APP_URL, BP_OUT override the defaults)
import { chromium } from "playwright";
import fs from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

// NOTE: don't name anything `URL` here: `new URL(...)` below needs the global.
const BP = resolve(process.env.BP_OUT ?? fileURLToPath(new URL("../../blueprint-out", import.meta.url)));
const APP_URL = process.env.APP_URL ?? "http://localhost:5173/"; // TODO: your dev server
for (const d of ["ui", "render", "mp4", "data"]) fs.mkdirSync(`${BP}/${d}`, { recursive: true });

const report = { run: `sweep-${randomUUID()}`, checks: [], perf: {}, timings: {}, errors: [], warnings: [], screenshots: [], visualReview: "pending" };
fs.mkdirSync(`${BP}/ui/${report.run}`, { recursive: true });
const check = (name, ok, detail = "") => { report.checks.push({ name, ok: !!ok, detail: String(detail) }); console.log(ok ? "PASS" : "FAIL", name, detail); };

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2, acceptDownloads: true });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") report.errors.push(m.text()); if (m.type() === "warning") report.warnings.push(m.text()); });
page.on("pageerror", (e) => report.errors.push(`pageerror: ${e.message}`));
const H = (fn, arg) => page.evaluate(fn, arg);
const settle = (ms = 300) => page.waitForTimeout(ms);
const shot = async (name, loc) => {
  const path = `${BP}/ui/${report.run}/${name}.png`;
  const png = await (loc ?? page).screenshot({ path });
  report.screenshots.push({ id: name, path, group: "ui-states", kind: "ui",
    source: "browser-ui", timeMs: 0, width: png.readUInt32BE(16), height: png.readUInt32BE(20),
    sha256: createHash("sha256").update(png).digest("hex") });
};

// ---------------------------------------------------------------- load, clean
const t0 = Date.now();
await page.goto(APP_URL);
await page.evaluate(() => localStorage.clear());
await page.reload();
// TODO: an app-ready condition, never a bare sleep. Expose a test hook (window.__app) in the app.
await page.waitForFunction(() => window.__app && !document.querySelector(".loading"), null, { timeout: 30000 });
report.timings.firstRenderMs = Date.now() - t0;

// ---------------------------------------------------------------- UI states
// TODO: one screenshot per meaningful state: default, each tab/panel, each selection, dialogs, empty/error states.
await shot("01-default");

// ---------------------------------------------------------------- output matrix
// TODO: load explicit fixtures through the hook (never rely on the default project), render or
// capture every variant the product can produce (looks, sizes, templates...) into render/.

// ---------------------------------------------------------------- performance
// TODO: fps while playing/interacting, cost of hot paths (measure in-page with performance.now()),
// memory after the sweep. Put each number in report.perf with a stable key.
report.perf.jsHeapMB = await H(() => performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null);

// ---------------------------------------------------------------- edge cases
// TODO: round-trip saves, bad input files, limits (undo cap, max sizes), destructive guards,
// keyboard paths. One check per promise, e.g.:
// check("One drag = one undo step", after === before + 1, `${before} -> ${after}`);

// ---------------------------------------------------------------- phone width
await page.setViewportSize({ width: 390, height: 844 });
await settle(600);
await shot("09-mobile-390");
check("No sideways scroll at 390px", !(await H(() => document.documentElement.scrollWidth > window.innerWidth + 1)));

check("No console errors", report.errors.length === 0, report.errors.slice(0, 3).join(" | "));
check("Visual evidence includes actual screenshots", report.screenshots.length > 0);
report.captureStatus = report.screenshots.length ? "captured" : "failed";
const reportPath = `${BP}/data/report-${report.run}.json`;
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), { flag: "wx" });
console.log(JSON.stringify({ report: reportPath, run: report.run, screenshots: report.screenshots.length }));
const passed = report.checks.filter((c) => c.ok).length;
console.log(`\n${passed}/${report.checks.length} checks passed`, JSON.stringify(report.perf));
await browser.close();
process.exit(passed === report.checks.length ? 0 : 1);
