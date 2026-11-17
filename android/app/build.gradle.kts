plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.jeremyshanebrook.convertibletoppricing"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jeremyshanebrook.convertibletoppricing"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        // AGP pre-creates a "debug" config; repoint it at the tracker's key.
        getByName("debug") {
            // The tracker's debug key. /root/.android/debug.keystore is wiped
            // on VM restarts, so the same key lives at this persistent path
            // (SHA-256 AB:BA:B8:A2:D2:F4:04:BD:97:F6:B1:A7:9A:BA:DD:04:6E:D5:
            // DF:9E:E2:E1:CF:FE:DE:52:B5:E8:67:51:99:90 — verified identical
            // to the key that signed the tracker's v1.3.1 APK). Override with
            // -PctpDebugKeystore=/path/to/keystore if the key ever moves.
            val keystorePath = findProperty("ctpDebugKeystore") as String?
                ?: "/home/hatch/workspace/tools/jeremy-debug.keystore"
            storeFile = file(keystorePath)
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
        release {
            isMinifyEnabled = false
            // Same debug key as the tracker: betas install as in-place
            // updates over prior builds signed with this key.
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-ktx:1.10.1")
}
