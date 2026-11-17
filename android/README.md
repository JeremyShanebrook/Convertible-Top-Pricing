# Convertible Top Pricing — Android

WebView-shell Android app, same shape as the Baseball AB Tracker
(`JeremyShanebrook/Baseball-At-Bat-Tracker`): one activity loads the
bundled catalog page from `app/src/main/assets/index.html` and the native
side owns app updates through GitHub.

- Package: `com.jeremyshanebrook.convertibletoppricing`
- App label: Convertible Top Pricing
- Version: 1.0.1 (versionCode 2)
- Catalog: 19,450 rows (Robbins 10,648 / GAHH 1,886 / EZON 6,916), MSRP +
  labor (hours × Settings rate), bundled in the page — works fully offline.
  One card per supplier per vehicle; cascading dropdowns (part type / top
  style / window type / material / color / zipper / rain rail / drip rail /
  part) with leave-one-out bidirectional filtering.
- The labor rate persists in the WebView's localStorage
  (`ctp-labor-rate-cents`), same key as the desktop build.

## Build

```sh
export JAVA_HOME=~/workspace/tools/jdk17
export GRADLE_USER_HOME=~/workspace/tools/gradle-home
export JAVA_TOOL_OPTIONS="-Djava.net.preferIPv4Stack=true -Djavax.net.ssl.trustStore=/home/hatch/workspace/tools/truststore.jks -Djavax.net.ssl.trustStorePassword=changeit"
~/workspace/tools/gradle-8.10.2/bin/gradle clean assembleDebug --offline
```

Use the installed Gradle binary, not `./gradlew`. Output:
`app/build/outputs/apk/debug/app-debug.apk`. Copy it to the distinct
release filename — a new filename per rebuild, including the versionCode:

```
ConvertibleTopPricing-v1.0.1-code2.apk
```

Reusing a filename makes Android stop recognizing the download as
installable.

## Signing

Both `debug` and `release` build types sign with the tracker's debug key
at `~/workspace/tools/jeremy-debug.keystore` (alias `androiddebugkey`,
password `android`). `/root/.android/debug.keystore` is wiped on VM
restarts, so the same key lives at this persistent path — its SHA-256
fingerprint is `AB:BA:B8:A2:D2:F4:04:BD:97:F6:B1:A7:9A:BA:DD:04:6E:D5:
DF:9E:E2:E1:CF:FE:DE:52:B5:E8:67:51:99:90`, verified identical to the key
that signed the tracker's v1.3.1 APK. Override the path with
`-PctpDebugKeystore=/path/to/keystore`. Never sign a build with a fresh
key: future versions would no longer install over this one.

## Update contract (same as the desktop version)

`version.json` on the repo's `main` branch is the version of record:

```json
{
  "version": "1.0.1",
  "app_changed": true,
  "desktop_download": "ConvertibleTopPricing-Desktop.html",
  "android_apk": "https://github.com/JeremyShanebrook/Convertible-Top-Pricing/releases/download/v1.0.1/ConvertibleTopPricing-v1.0.1-code2.apk",
  "release_notes": "..."
}
```

- Launch: the native side fetches `version.json` (10 s timeout, silent
  when offline) and compares versions with real semver logic.
- Pricing-only update (`app_changed: false`): the native side does
  nothing — the page's own JS applies the `price-updates.json` entries
  and shows its price notice.
- App update (`app_changed: true`): the native side downloads the APK
  from `android_apk` (falling back to the latest GitHub release's `.apk`
  asset, same pattern as the tracker), verifies it is a real APK
  (ZIP magic), then fires the install intent. First install needs
  "Allow from this source" (Android 8+); the app walks Jeremy through
  it with `openInstallSettings()`.
- The bundled page detects the `AndroidBridge` and hands app updates to
  it instead of showing its desktop "Download update" banner. That is
  the only difference between `assets/index.html` and the desktop file
  (see the diff: the `showUpdatePrompt` handoff plus one line in
  `checkForUpdates`).
- Settings has a "Check for updates" button that runs the same check on
  demand (page JS → native handoff for app updates).

## Releasing a new version

1. Bump `versionCode` / `versionName` in `app/build.gradle.kts` and
   `APP_VERSION` in the new desktop file.
2. Copy the new desktop file to `app/src/main/assets/index.html` and
   re-apply the AndroidBridge tweak (the two edits in
   `showUpdatePrompt` / `checkForUpdates`).
3. Build, copy the APK to its distinct filename, create a GitHub
   Release on `main` with the APK as the asset, and set `android_apk`
   in `version.json` to the release asset URL.
