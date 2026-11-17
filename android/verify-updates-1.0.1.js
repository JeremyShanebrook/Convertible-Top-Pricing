/* Verification harness for the Android updater logic, v1.0.1 edition.
 * Adapted from verify-updates.js (v1.0.0). Differences from the 1.0.0 run:
 * - installed version is now 1.0.1; stubs use 1.0.2 as the "next" version
 * - live version.json is still 1.0.0 (with the v1.0.0 android_apk) -> the
 *   "up to date" direction is checked against it
 * - releases/latest now EXISTS (v1.0.0) -> the no-android_apk fallback is
 *   checked against the real v1.0.0 .apk asset instead of a 404
 * - pricing-only stub also runs the page's REAL applyPendingPriceEntries
 *   against the decoded bundled catalog (Robbins +2.0%)
 * 1) Runs the EXACT showUpdatePrompt shipped in the bundled assets/index.html
 *    with a mocked AndroidBridge and mocked DOM helpers, with and without
 *    the bridge present.
 * 2) Runs the EXACT compareVersions shipped in the bundled page.
 * 3) Replays the native (Kotlin) update decision tree — ported 1:1 from
 *    MainActivity.kt — against the live version.json and stub payloads.
 * 4) Static checks on the bundled page (APP_VERSION, storage key, tweak).
 */
const fs = require("fs");
const vm = require("vm");

const BUNDLED = "/home/hatch/workspace/projects/convertible-top-app/android/app/src/main/assets/index.html";
const DESKTOP = "/home/hatch/workspace/projects/convertible-top-app/github-pages/ConvertibleTopPricing-Desktop.html";
const CURRENT = "1.0.1";
const html = fs.readFileSync(BUNDLED, "utf8");
let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("PASS", name); }
  else { fail++; console.log("FAIL", name, extra || ""); }
}

function extractFunction(src, name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error("function not found: " + name);
  let i = src.indexOf("{", start);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("unbalanced braces in " + name);
}

// ---------- decode the bundled catalog (for the price-apply test) ----------
function decodeRows() {
  const start = html.indexOf("window.CTP = {");
  const end = html.indexOf("</script>", start);
  const sb = { window: {} };
  vm.createContext(sb);
  vm.runInContext(html.slice(start, end), sb);
  const CTP = sb.window.CTP, D = CTP.dicts;
  const SUP = ["Robbins", "GAHH", "EZON"];
  const ds = (f, i) => (i == null ? null : D[f][i]);
  return CTP.rows.map((r, idx) => ({
    id: idx + 1, supplier: SUP[r[0]], yearStart: r[1], yearEnd: r[2],
    make: ds("make", r[3]), model: ds("model", r[4]),
    sku: r[6], coreNumber: r[7], priceMsrpCents: r[8], laborHours: r[9],
    material: ds("material", r[13]),
  }));
}

// ---------- 1) showUpdatePrompt handoff ----------
const showSrc = extractFunction(html, "showUpdatePrompt");
check("tweak present in bundled showUpdatePrompt", showSrc.includes("AndroidBridge.onAppUpdateAvailable"));

function runShow2(info, force, withBridge) {
  const calls = [];
  const banner = { html: null };
  const status = { text: null };
  const sandbox = {
    dismissedUpdateVersion: null,
    __info: info,
    __force: force,
    document: { getElementById: () => null },
    esc: (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    showUpdateBanner: (h) => { banner.html = h; },
    setUpdateStatus: (t) => { status.text = t; },
    updateFileUrl: () => "https://example.invalid/file.html",
    updateFileName: () => "file.html",
    console,
  };
  if (withBridge) {
    sandbox.AndroidBridge = {
      onAppUpdateAvailable: (v, n, f) => calls.push({ version: v, notes: n, force: f }),
    };
  }
  vm.createContext(sandbox);
  vm.runInContext(showSrc + "\nshowUpdatePrompt(__info, __force);", sandbox);
  return { calls, banner, status };
}

const info102 = { version: "1.0.2", release_notes: "Test notes", app_changed: true };
let r = runShow2(info102, false, true);
check("with bridge: native handoff called once", r.calls.length === 1, JSON.stringify(r.calls));
check("with bridge: version passed through", r.calls[0] && r.calls[0].version === "1.0.2");
check("with bridge: notes passed through", r.calls[0] && r.calls[0].notes === "Test notes");
check("with bridge: force=false on silent check", r.calls[0] && r.calls[0].force === false);
check("with bridge: NO desktop banner rendered", r.banner.html === null);
r = runShow2(info102, true, true);
check("with bridge manual: force=true passed", r.calls[0] && r.calls[0].force === true);
check("with bridge manual: status text is Android wording",
  r.status.text === "Update available: version 1.0.2 — use the update prompt to download & install.", r.status.text);
r = runShow2(info102, false, false);
check("without bridge: no native call", r.calls.length === 0);
check("without bridge: desktop banner HAS Download update link",
  typeof r.banner.html === "string" && r.banner.html.includes("Download update"));

// ---------- 2) compareVersions from the bundled page ----------
const cmpSrc = extractFunction(html, "compareVersions");
const cs = { console };
vm.createContext(cs);
vm.runInContext(cmpSrc, cs);
check("semver 1.0.10 > 1.0.9", cs.compareVersions("1.0.10", "1.0.9") === 1);
check("semver 1.0.1 == 1.0.1", cs.compareVersions("1.0.1", "1.0.1") === 0);
check("semver 1.0.2 > 1.0.1", cs.compareVersions("1.0.2", "1.0.1") === 1);
check("semver 1.0.1 < 1.0.2", cs.compareVersions("1.0.1", "1.0.2") === -1);
check("semver 2.0.0 > 1.9.9", cs.compareVersions("2.0.0", "1.9.9") === 1);

// ---------- 3) native decision tree (1:1 port of MainActivity.kt) ----------
function compareVersions(a, b) {
  const pa = String(a).split("."), pb = String(b).split(".");
  for (let i = 0; i < 3; i++) {
    const x = parseInt(pa[i], 10) || 0, y = parseInt(pb[i], 10) || 0;
    if (x > y) return 1;
    if (x < y) return -1;
  }
  return 0;
}
function nativeDecision(info, current, fetchLatestRelease) {
  const remote = info && typeof info.version === "string" ? info.version : "";
  if (!remote || compareVersions(remote, current) <= 0) return { action: "up-to-date" };
  if (info.app_changed === false) return { action: "native-noop-pricing-only" };
  const fromManifest = typeof info.android_apk === "string" && info.android_apk ? info.android_apk : null;
  if (fromManifest) return { action: "prompt-install", apkUrl: fromManifest };
  const rel = fetchLatestRelease();
  const apk = (rel && rel.assets || []).find((a) => /\.apk$/i.test(a.name || ""));
  if (apk) return { action: "prompt-install", apkUrl: apk.browser_download_url };
  return { action: "no-apk-found" };
}

async function main() {
  // Live version.json (still 1.0.0; the 1.0.1 push lands later)
  const live = await (await fetch("https://raw.githubusercontent.com/JeremyShanebrook/Convertible-Top-Pricing/main/version.json")).json();
  check("live version.json is 1.0.0", live.version === "1.0.0", live.version);
  console.log("  live version.json android_apk:", live.android_apk || "(none)");
  let d = nativeDecision(live, CURRENT, () => null);
  check("live 1.0.0 vs installed 1.0.1: up to date, no prompt", d.action === "up-to-date", d.action);

  // Stub: pricing-only 1.0.2 (Robbins +2.0%)
  const priceStub = { version: "1.0.2", app_changed: false,
    changes: { robbins: 0.02 } };
  d = nativeDecision(priceStub, CURRENT, () => null);
  check("stub 1.0.2 app_changed=false: native does nothing (page applies prices)", d.action === "native-noop-pricing-only", d.action);

  // Page-side: run the EXACT applyPendingPriceEntries from the bundled page
  // against the decoded bundled catalog.
  const rows = decodeRows();
  check("decoded catalog for price test == 19450 rows", rows.length === 19450, "got " + rows.length);
  const beforeRobbins = rows.find((x) => x.supplier === "Robbins").priceMsrpCents;
  const beforeGahh = rows.find((x) => x.supplier === "GAHH").priceMsrpCents;
  const beforeEzon = rows.find((x) => x.supplier === "EZON").priceMsrpCents;
  const priceSandbox = {
    console,
    APP_VERSION: CURRENT,
    ROWS: rows,
    appliedPriceVersion: CURRENT,
    appliedPriceEntries: [],
    localStorage: { _s: {}, getItem(k) { return this._s[k] || null; },
      setItem(k, v) { this._s[k] = String(v); }, removeItem(k) { delete this._s[k]; } },
  };
  vm.createContext(priceSandbox);
  vm.runInContext(cmpSrc + "\n" + extractFunction(html, "savePriceState") + "\n" +
    extractFunction(html, "applyPriceEntry") + "\n" +
    extractFunction(html, "priceChangeSummary") + "\n" +
    extractFunction(html, "applyPendingPriceEntries"), priceSandbox);
  const applied = vm.runInContext(
    'applyPendingPriceEntries([{version:"1.0.2", changes:{robbins:0.02}}], "1.0.2")', priceSandbox);
  check("page applies pricing-only entry (1 applied)", applied.length === 1, JSON.stringify(applied));
  check("pricing summary reads 'Robbins +2%'",
    applied[0] && applied[0].summary === "Robbins +2%", applied[0] && applied[0].summary);
  check("Robbins row price rose exactly 2%",
    rows.find((x) => x.supplier === "Robbins").priceMsrpCents === Math.round(beforeRobbins * 1.02),
    "before " + beforeRobbins + " after " + rows.find((x) => x.supplier === "Robbins").priceMsrpCents);
  check("GAHH row price unchanged by Robbins-only entry",
    rows.find((x) => x.supplier === "GAHH").priceMsrpCents === beforeGahh);
  check("EZON row price unchanged by Robbins-only entry",
    rows.find((x) => x.supplier === "EZON").priceMsrpCents === beforeEzon);

  // Stub: app update 1.0.2 with android_apk pointing at the v1.0.1 code2 release
  const apkUrl = "https://github.com/JeremyShanebrook/Convertible-Top-Pricing/releases/download/v1.0.1/ConvertibleTopPricing-v1.0.1-code2.apk";
  d = nativeDecision({ version: "1.0.2", app_changed: true, android_apk: apkUrl, release_notes: "n" }, CURRENT, () => null);
  check("stub 1.0.2 app_changed=true + android_apk: prompt with that exact URL",
    d.action === "prompt-install" && d.apkUrl === apkUrl, JSON.stringify(d));

  // Stub: app update, no android_apk -> fallback to live latest release (v1.0.0 now exists)
  const latestRes = await fetch("https://api.github.com/repos/JeremyShanebrook/Convertible-Top-Pricing/releases/latest");
  check("live releases/latest is 200 (v1.0.0 released)", latestRes.status === 200, "status " + latestRes.status);
  const latest = await latestRes.json();
  check("live latest release tag is v1.0.0", latest.tag_name === "v1.0.0", latest.tag_name);
  const liveApk = (latest.assets || []).find((a) => /\.apk$/i.test(a.name || ""));
  check("live latest release has a .apk asset (v1.0.0 code1)",
    !!liveApk && liveApk.name === "ConvertibleTopPricing-v1.0.0-code1.apk",
    liveApk ? liveApk.name : "none");
  d = nativeDecision({ version: "1.0.2", app_changed: true }, CURRENT, () => latest);
  check("fallback: first .apk asset of latest release is used",
    d.action === "prompt-install" && liveApk && d.apkUrl === liveApk.browser_download_url, JSON.stringify(d));

  // ---------- 4) static checks on the bundled page ----------
  check("bundled page contains APP_VERSION 1.0.1", html.includes('APP_VERSION = "1.0.1"'));
  check("bundled page contains labor-rate storage key", html.includes("ctp-labor-rate-cents"));
  check("bundled page contains localStorage persistence", html.includes("localStorage.setItem"));
  check("bundled page contains 6213 (Mustang top)", html.includes("6213"));
  check("bundled page contains 30750 (R129 top)", html.includes("30750"));
  check("bundled page contains Miata + S2000 style labels", html.includes("Original style"));
  check("bundled page contains cascade dropdowns", html.includes("leave-one-out") || html.includes("cascade"));
  check("bundled page differs from desktop file ONLY by the tweak",
    (() => {
      const desk = fs.readFileSync(DESKTOP, "utf8");
      return html.includes("AndroidBridge.onAppUpdateAvailable") && !desk.includes("AndroidBridge");
    })());

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("HARNESS ERROR", e); process.exit(2); });
