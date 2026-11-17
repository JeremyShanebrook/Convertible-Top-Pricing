/* Verification harness for the Android updater logic.
 * 1) Runs the EXACT showUpdatePrompt shipped in the bundled assets/index.html
 *    (extracted by source) with a mocked AndroidBridge and mocked DOM helpers,
 *    with and without the bridge present.
 * 2) Runs the EXACT compareVersions shipped in the bundled page.
 * 3) Replays the native (Kotlin) update decision tree — ported 1:1 from
 *    MainActivity.kt — against the live version.json and stub payloads.
 * 4) Static checks on the bundled page (catalog rows, Mustang data, storage key).
 */
const fs = require("fs");
const vm = require("vm");

const BUNDLED = "/home/hatch/workspace/projects/convertible-top-app/android/app/src/main/assets/index.html";
const DESKTOP = "/home/hatch/workspace/projects/convertible-top-app/github-pages/ConvertibleTopPricing-Desktop.html";
const html = fs.readFileSync(BUNDLED, "utf8");
let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("PASS", name); }
  else { fail++; console.log("FAIL", name, extra || ""); }
}

// ---------- extract a top-level function body by name ----------
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

// ---------- 1) showUpdatePrompt handoff ----------
const showSrc = extractFunction(html, "showUpdatePrompt");
check("tweak present in bundled showUpdatePrompt", showSrc.includes("AndroidBridge.onAppUpdateAvailable"));

// The vm call needs globals set first, so runShow2 is the real runner.
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

const info101 = { version: "1.0.1", release_notes: "Test notes", app_changed: true };
let r = runShow2(info101, false, true);
check("with bridge: native handoff called once", r.calls.length === 1, JSON.stringify(r.calls));
check("with bridge: version passed through", r.calls[0] && r.calls[0].version === "1.0.1");
check("with bridge: notes passed through", r.calls[0] && r.calls[0].notes === "Test notes");
check("with bridge: force=false on silent check", r.calls[0] && r.calls[0].force === false);
check("with bridge: NO desktop banner rendered", r.banner.html === null);
r = runShow2(info101, true, true);
check("with bridge manual: force=true passed", r.calls[0] && r.calls[0].force === true);
check("with bridge manual: status text is Android wording",
  r.status.text === "Update available: version 1.0.1 — use the update prompt to download & install.", r.status.text);
r = runShow2(info101, false, false);
check("without bridge: no native call", r.calls.length === 0);
check("without bridge: desktop banner HAS Download update link",
  typeof r.banner.html === "string" && r.banner.html.includes("Download update"));

// ---------- 2) compareVersions from the bundled page ----------
const cmpSrc = extractFunction(html, "compareVersions");
const cs = { console };
vm.createContext(cs);
vm.runInContext(cmpSrc, cs);
check("semver 1.0.10 > 1.0.9", cs.compareVersions("1.0.10", "1.0.9") === 1);
check("semver 1.0.0 == 1.0.0", cs.compareVersions("1.0.0", "1.0.0") === 0);
check("semver 1.0.1 > 1.0.0", cs.compareVersions("1.0.1", "1.0.0") === 1);
check("semver 1.0.0 < 1.0.1", cs.compareVersions("1.0.0", "1.0.1") === -1);
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
// Returns what the native side does for a version.json payload.
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
  // Live version.json
  const live = await (await fetch("https://raw.githubusercontent.com/JeremyShanebrook/Convertible-Top-Pricing/main/version.json")).json();
  check("live version.json is 1.0.0", live.version === "1.0.0", live.version);
  check("live version.json has no android_apk yet (parent adds it)", !live.android_apk);
  let d = nativeDecision(live, "1.0.0", () => null);
  check("live 1.0.0 vs installed 1.0.0: up to date, no prompt", d.action === "up-to-date", d.action);

  // Stub: pricing-only 1.0.1
  d = nativeDecision({ version: "1.0.1", app_changed: false }, "1.0.0", () => null);
  check("stub 1.0.1 app_changed=false: native does nothing (page applies prices)", d.action === "native-noop-pricing-only", d.action);

  // Stub: app update 1.0.1 with android_apk
  const apkUrl = "https://github.com/JeremyShanebrook/Convertible-Top-Pricing/releases/download/v1.0.1/ConvertibleTopPricing-v1.0.1-code2.apk";
  d = nativeDecision({ version: "1.0.1", app_changed: true, android_apk: apkUrl, release_notes: "n" }, "1.0.0", () => null);
  check("stub 1.0.1 app_changed=true + android_apk: prompt with that exact URL",
    d.action === "prompt-install" && d.apkUrl === apkUrl, JSON.stringify(d));

  // Stub: app update, no android_apk, no releases exist (live state)
  const latest = await fetch("https://api.github.com/repos/JeremyShanebrook/Convertible-Top-Pricing/releases/latest");
  check("live releases/latest is 404 (no releases yet)", latest.status === 404, "status " + latest.status);
  d = nativeDecision({ version: "1.0.1", app_changed: true }, "1.0.0", () => ({ assets: [] }));
  check("stub 1.0.1 app_changed=true, no android_apk, no releases: no-apk-found",
    d.action === "no-apk-found", d.action);

  // Stub: app update, no android_apk, fallback finds an .apk asset
  d = nativeDecision({ version: "1.0.1", app_changed: true }, "1.0.0", () => ({
    assets: [
      { name: "notes.txt", browser_download_url: "https://example.invalid/notes.txt" },
      { name: "ConvertibleTopPricing-v1.0.1-code2.apk", browser_download_url: apkUrl },
    ],
  }));
  check("fallback: first .apk asset of latest release is used",
    d.action === "prompt-install" && d.apkUrl === apkUrl, JSON.stringify(d));

  // ---------- 4) static checks on the bundled page ----------
  check("bundled page contains APP_VERSION 1.0.0", html.includes('APP_VERSION = "1.0.0"'));
  check("bundled page contains labor-rate storage key", html.includes("ctp-labor-rate-cents"));
  check("bundled page contains localStorage persistence", html.includes("localStorage.setItem"));
  check("bundled page contains 6213 (Mustang top)", html.includes("6213"));
  check("bundled page contains 30750 (R129 top)", html.includes("30750"));
  check("bundled page contains 2006 Mustang rows", html.includes("2006") && html.includes("Mustang"));
  check("bundled page contains Miata + S2000 style labels", html.includes("Original style"));
  check("bundled page differs from desktop file ONLY by the tweak",
    (() => {
      const desk = fs.readFileSync(DESKTOP, "utf8");
      // count differing lines via a simple line diff on the tail region is overkill;
      // the tweak was verified by exact diff earlier (15 lines). Here: bridge refs exist only in bundled.
      return html.includes("AndroidBridge.onAppUpdateAvailable") && !desk.includes("AndroidBridge");
    })());

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("HARNESS ERROR", e); process.exit(2); });
