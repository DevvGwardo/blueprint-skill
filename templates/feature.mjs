// Blueprint feature pass: <FEATURE>. One check per promise the feature makes, including the
// unhappy paths. Copy to tools/blueprint/<feature>.mjs.
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BP = resolve(process.env.BP_OUT ?? fileURLToPath(new URL("../../blueprint-out", import.meta.url)));
const APP_URL = process.env.APP_URL ?? "http://localhost:5173/"; // TODO
const NAME = "feature"; // TODO: report-<NAME>.json
for (const d of ["ui", "render", "mp4", "data"]) fs.mkdirSync(`${BP}/${d}`, { recursive: true });
const report = { run: `${NAME}-${randomUUID()}`, checks: [], perf: {}, errors: [], screenshots: [], visualReview: "pending" };
fs.mkdirSync(`${BP}/ui/${report.run}`, { recursive: true });
const check = (name, ok, detail = "") => { report.checks.push({ name, ok: !!ok, detail: String(detail) }); console.log(ok ? "PASS" : "FAIL", name, detail); };

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2, acceptDownloads: true })).newPage();
page.on("console", (m) => { if (m.type() === "error") report.errors.push(m.text()); });
page.on("pageerror", (e) => report.errors.push(`pageerror: ${e.message}`));
const H = (fn, arg) => page.evaluate(fn, arg);
const settle = (ms = 300) => page.waitForTimeout(ms);
const shot = async (name, loc) => {
  const path = `${BP}/ui/${report.run}/${NAME}-${name}.png`;
  const png = await (loc ?? page).screenshot({ path });
  report.screenshots.push({ id: `${NAME}-${name}`, path, group: NAME, kind: "ui",
    source: "browser-ui", timeMs: 0, width: png.readUInt32BE(16), height: png.readUInt32BE(20),
    sha256: createHash("sha256").update(png).digest("hex") });
};
const state = () => H(() => window.__app.store.getState()); // TODO: return only what checks need

await page.goto(APP_URL);
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForFunction(() => window.__app, null, { timeout: 30000 }); // TODO: real ready condition
await shot("01-entry");

// 1. Entry points: the feature is reachable where it should be, hidden where it shouldn't.
// 2. Happy path, driven with the real mouse/keyboard (page.mouse, page.keyboard), not store calls.
// 3. Limits and refusals: clamping, locked items, invalid input; each refusal explains itself.
// 4. Undo / redo granularity (one gesture = one step), persistence across reload, junk in saved files.
// 5. Output: export/produce through the real UI; probe the file (ffprobe etc.) and compare a decoded
//    frame or value against the app's own render (mean abs diff below a small threshold).
// 6. Perf of the feature's hot path (per-frame work, interaction latency), phone width, console errors.
//
// For canvas/3D targets: get screen coords from the engine's projection and verify with a pick at
// that point before clicking (poll: the first frames after a mode switch can be stale).

check("No console errors", report.errors.length === 0, report.errors.slice(0, 3).join(" | "));
check("Visual evidence includes actual screenshots", report.screenshots.length > 0);
report.captureStatus = report.screenshots.length ? "captured" : "failed";
const reportPath = `${BP}/data/report-${report.run}.json`;
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), { flag: "wx" });
console.log(JSON.stringify({ report: reportPath, run: report.run, screenshots: report.screenshots.length }));
const passed = report.checks.filter((c) => c.ok).length;
console.log(`\n${passed}/${report.checks.length} ${NAME} checks passed`, JSON.stringify(report.perf));
await browser.close();
process.exit(passed === report.checks.length ? 0 : 1);
