package com.jeremyshanebrook.convertibletoppricing

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.core.content.FileProvider
import androidx.core.view.WindowCompat
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * WebView shell for Convertible Top Pricing, same shape as the Baseball AB
 * Tracker: a single activity loads the bundled catalog page from assets and
 * the native side owns app updates through GitHub.
 *
 * Update contract (mirrors the desktop build):
 * - version.json on main is the version of record. Pricing-only months set
 *   app_changed=false and the page's own JS applies the price-updates.json
 *   entries itself; the native side does nothing for those.
 * - App updates set app_changed=true. The native side downloads the APK
 *   from version.json's "android_apk" URL (falling back to the latest
 *   GitHub release's .apk asset, same pattern as the tracker) and fires
 *   the install intent so it installs over the current build.
 * - The page suppresses its desktop "Download update" banner when it
 *   detects this bridge and hands the update to onAppUpdateAvailable().
 */
class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView

    private fun currentVersionName(): String =
        packageManager.getPackageInfo(packageName, 0).versionName ?: "1.0"

    companion object {
        private const val GITHUB_OWNER = "JeremyShanebrook"
        private const val GITHUB_REPO = "Convertible-Top-Pricing"
        private const val VERSION_URL =
            "https://raw.githubusercontent.com/JeremyShanebrook/Convertible-Top-Pricing/main/version.json"
        private const val RELEASES_LATEST_URL =
            "https://api.github.com/repos/JeremyShanebrook/Convertible-Top-Pricing/releases/latest"
    }

    private var updateCheckDone = false
    private var promptedUpdateVersion: String? = null

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        window.statusBarColor = Color.rgb(0x1A, 0x1A, 0x1A)
        window.navigationBarColor = Color.rgb(0x1A, 0x1A, 0x1A)

        webView = WebView(this).apply {
            setBackgroundColor(Color.rgb(0x1A, 0x1A, 0x1A))
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.allowFileAccess = true
            settings.allowContentAccess = true
            // The bundled page is a file:// document; its update checker
            // fetches version.json / price-updates.json from
            // raw.githubusercontent.com, so file URLs must be allowed to
            // reach the network (raw.githubusercontent.com answers CORS *).
            settings.allowFileAccessFromFileURLs = true
            settings.allowUniversalAccessFromFileURLs = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.builtInZoomControls = false
            settings.displayZoomControls = false
            settings.textZoom = 100
            addJavascriptInterface(AndroidBridge(), "AndroidBridge")
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val uri = request.url
                    return if (uri.scheme == "http" || uri.scheme == "https") {
                        try { startActivity(Intent(Intent.ACTION_VIEW, uri)) } catch (_: Exception) {}
                        true
                    } else {
                        false
                    }
                }
                override fun onPageFinished(view: WebView, url: String) {
                    super.onPageFinished(view, url)
                    if (!updateCheckDone) {
                        updateCheckDone = true
                        postDelayed({ checkForUpdatesInternal(silent = true) }, 1200)
                    }
                }
            }
            loadUrl("file:///android_asset/index.html")
        }

        setContentView(webView)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }

    private inner class AndroidBridge {
        @JavascriptInterface fun versionName(): String = currentVersionName()
        @JavascriptInterface fun versionCode(): Int =
            packageManager.getPackageInfo(packageName, 0).longVersionCode.toInt()
        @JavascriptInterface fun isAndroidApp(): Boolean = true
        @JavascriptInterface fun checkForUpdates() { checkForUpdatesInternal(silent = false) }
        @JavascriptInterface fun onAppUpdateAvailable(version: String, notes: String, force: Boolean) {
            promptForAppUpdate(version, notes, force, versionJson = null)
        }
        @JavascriptInterface fun openInstallSettings() {
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
        }
        @JavascriptInterface fun debugInfo(): String {
            return "version=${versionName()}\nversionCode=${versionCode()}\nandroid=${android.os.Build.VERSION.RELEASE}\ndevice=${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}"
        }
    }

    // Port of the page's compareVersions (JS): numeric, three parts.
    private fun compareVersions(a: String, b: String): Int {
        val pa = a.split(".")
        val pb = b.split(".")
        for (i in 0 until 3) {
            val x = pa.getOrNull(i)?.toIntOrNull() ?: 0
            val y = pb.getOrNull(i)?.toIntOrNull() ?: 0
            if (x > y) return 1
            if (x < y) return -1
        }
        return 0
    }

    private fun fetchJson(url: String): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 10000
        conn.readTimeout = 10000
        conn.requestMethod = "GET"
        conn.setRequestProperty("Accept", "application/json")
        conn.setRequestProperty("User-Agent", "Convertible-Top-Pricing")
        val code = conn.responseCode
        if (code !in 200..299) throw IllegalStateException("GitHub returned HTTP $code")
        val body = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()
        return JSONObject(body)
    }

    private fun checkForUpdatesInternal(silent: Boolean) {
        thread {
            try {
                val info = fetchJson(VERSION_URL)
                val remote = info.optString("version", "")
                val current = currentVersionName()
                if (remote.isBlank() || compareVersions(remote, current) <= 0) {
                    if (!silent) runOnUiThread { showMessage("You're up to date.\nVersion $current") }
                    return@thread
                }
                // Pricing-only: the page's own checker applies the
                // price-updates.json entries; the native side does nothing.
                if (!info.optBoolean("app_changed", true)) return@thread
                val notes = info.optString("release_notes", "")
                promptForAppUpdate(remote, notes, force = !silent, versionJson = info)
            } catch (e: Exception) {
                if (!silent) runOnUiThread {
                    showMessage("Couldn't check GitHub for updates.\n\n${e.message ?: "Unknown error"}")
                }
            }
        }
    }

    // Resolves the APK download URL: version.json's "android_apk" when it is
    // published, otherwise the latest GitHub release's .apk asset (same
    // pattern as the Baseball AB Tracker).
    private fun resolveApkUrl(versionJson: JSONObject?): String {
        val fromManifest = versionJson?.optString("android_apk", "")?.takeIf { it.isNotBlank() }
        if (fromManifest != null) return fromManifest
        val release = fetchJson(RELEASES_LATEST_URL)
        val assets = release.optJSONArray("assets") ?: return ""
        for (i in 0 until assets.length()) {
            val asset = assets.optJSONObject(i) ?: continue
            if (asset.optString("name", "").lowercase().endsWith(".apk")) {
                return asset.optString("browser_download_url", "")
            }
        }
        return ""
    }

    private fun promptForAppUpdate(version: String, notes: String, force: Boolean, versionJson: JSONObject?) {
        runOnUiThread {
            if (!force && promptedUpdateVersion == version) return@runOnUiThread
            promptedUpdateVersion = version
            thread {
                try {
                    val apkUrl = resolveApkUrl(versionJson)
                    if (apkUrl.isBlank()) throw IllegalStateException("No APK was found for version $version")
                    runOnUiThread { showUpdateDialog(version, notes, apkUrl) }
                } catch (e: Exception) {
                    promptedUpdateVersion = null
                    if (force) runOnUiThread {
                        showMessage("Couldn't get the update.\n\n${e.message ?: "Unknown error"}")
                    }
                }
            }
        }
    }

    private fun showUpdateDialog(version: String, notes: String, apkUrl: String) {
        AlertDialog.Builder(this)
            .setTitle("Update available")
            .setMessage("Version $version is available.\n\n$notes")
            .setNegativeButton("Later", null)
            .setPositiveButton("Download & Install") { _, _ -> downloadAndInstall(apkUrl, version) }
            .show()
    }

    private fun downloadAndInstall(apkUrl: String, version: String) {
        thread {
            try {
                val dir = File(cacheDir, "updates").apply { mkdirs() }
                val apk = File(dir, "ConvertibleTopPricing-$version.apk")
                val conn = URL(apkUrl).openConnection() as HttpURLConnection
                conn.connectTimeout = 15000
                conn.readTimeout = 60000
                conn.setRequestProperty("User-Agent", "Convertible-Top-Pricing")
                val code = conn.responseCode
                if (code !in 200..299) {
                    conn.disconnect()
                    throw IllegalStateException("GitHub returned HTTP $code while downloading the APK")
                }
                conn.inputStream.use { input -> apk.outputStream().use { output -> input.copyTo(output) } }
                conn.disconnect()
                // Verify it is a real APK (ZIP magic) before handing it to the installer.
                val magic = ByteArray(4)
                java.io.FileInputStream(apk).use { it.read(magic) }
                if (apk.length() < 1024 || magic[0] != 0x50.toByte() || magic[1] != 0x4B.toByte() ||
                    magic[2] != 0x03.toByte() || magic[3] != 0x04.toByte()
                ) {
                    throw IllegalStateException("The download is not a valid APK file")
                }
                val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apk)
                runOnUiThread {
                    if (!packageManager.canRequestPackageInstalls()) {
                        AlertDialog.Builder(this)
                            .setTitle("Allow installs from this app")
                            .setMessage("Android needs permission before this app can install its own updates. Turn on \"Allow from this source\", then check for updates again.")
                            .setNegativeButton("Cancel", null)
                            .setPositiveButton("Open settings") { _, _ ->
                                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                            }
                            .show()
                        return@runOnUiThread
                    }
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    try { startActivity(intent) } catch (_: Exception) {
                        showMessage("Android blocked the installer. Allow this app to install unknown apps, then try again.")
                    }
                }
            } catch (_: Exception) {
                runOnUiThread { showMessage("The update download failed.") }
            }
        }
    }

    private fun showMessage(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("OK", null).show()
    }

    override fun onDestroy() {
        try { webView.stopLoading() } catch (_: Exception) {}
        try { webView.destroy() } catch (_: Exception) {}
        super.onDestroy()
    }
}
