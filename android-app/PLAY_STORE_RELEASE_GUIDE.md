# DeliverEx Live — Android & Google Play Store Release Guide

Native Kotlin + Jetpack Compose Android app for **DeliverEx Live** (`com.deliverex.live`), connecting to the FastAPI / Gemini Live backend (`../deliverex-live`) and featuring a built-in Offline Interactive Demo Engine for Play Store review & field resilience.

---

## 1. Project Structure
- `app/src/main/java/com/deliverex/live/MainActivity.kt` — Edge-to-edge Material 3 host, runtime permission launchers (`RECORD_AUDIO`, `CAMERA`), and 4-tab navigation (`Live Call`, `WhatsApp`, `Manager`, `Insights`).
- `app/src/main/java/com/deliverex/live/audio/LiveAudioEngine.kt` — 16kHz PCM16 mono `AudioRecord` (with hardware AEC + NoiseSuppressor), 24kHz PCM16 mono `AudioTrack` playback with instant Barge-In flush, `TextToSpeech` (`en-IN`) fallback, and `MediaRecorder` WhatsApp voice note capture.
- `app/src/main/java/com/deliverex/live/data/remote/` — `DeliverExApiClient.kt` (OkHttp REST) and `LiveCallWebSocketClient.kt` (`/ws/live-call` bidirectional streaming).
- `app/src/main/java/com/deliverex/live/data/local/OfflineDemoEngine.kt` — Self-contained SOP-4.2 / SOP-5.1 / SOP-2.3 / SOP-6.0 simulation when offline.
- `app/src/main/res/xml/network_security_config.xml` — Release builds enforce HTTPS (`cleartextTrafficPermitted="false"`); debug builds (`app/src/debug/res/xml/network_security_config.xml`) permit local HTTP testing (`10.0.2.2:8000` / LAN IPs).

---

## 2. Connecting to Your Backend
1. **Android Emulator (Local FastAPI)**: Start `deliverex-live` on port `8000` (`uvicorn app.main:app --host 0.0.0.0 --port 8000`). Debug builds default to `http://10.0.2.2:8000`.
2. **Production / Google Play Release (HTTPS)**: Deploy `deliverex-live` to Google Cloud Run (`deploy_cloud_run.ps1`) and enter your `https://...` URL in **Insights -> Server & Privacy**, or update `DEFAULT_BASE_URL` in `app/build.gradle.kts`.

---

## 3. Generating a Signed Play Store `.aab` (Android App Bundle)

### Step A: Create an Upload Keystore (Once)
```powershell
keytool -genkey -v -keystore deliverex-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias deliverex
```

### Step B: Configure `keystore.properties` in Project Root (Do NOT Commit)
```properties
storeFile=C:/path/to/deliverex-upload.jks
storePassword=YOUR_STORE_PASSWORD
keyAlias=deliverex
keyPassword=YOUR_KEY_PASSWORD
```
*(Alternatively, set `DELIVEREX_KEYSTORE_PATH`, `DELIVEREX_KEYSTORE_PASSWORD`, `DELIVEREX_KEY_ALIAS`, `DELIVEREX_KEY_PASSWORD` environment variables.)*

### Step C: Build Release App Bundle & Run Tests
```powershell
./gradlew testDebugUnitTest
./gradlew bundleRelease
```
Output bundle: `app/build/outputs/bundle/release/app-release.aab`

---

## 4. Google Play Console Checklist
- **Target API Level**: Configured for **Android 15 (`targetSdk = 35`, `minSdk = 26`)** with R8 minification + resource shrinking enabled.
- **Data Safety Form**:
  - *Audio*: Collected ephemerally when driver taps **Start Live Call** or records a WhatsApp Voice Note; encrypted in transit (TLS/WSS); not used for advertising.
  - *Photos*: Collected only when driver captures a Proof-of-Delivery photo (`SOP-5.1`); encrypted in transit.
- **Permissions Justifications**:
  - `RECORD_AUDIO`: Real-time Hinglish/Tanglish voice call & WhatsApp voice note recording.
  - `CAMERA`: Proof-of-Delivery photo verification for damaged goods (`SOP-5.1`).
  - `uses-feature` set `required="false"` so compatible tablets/devices are not excluded.
- **App Review Readiness**: Built-in **Offline Interactive Demo Engine** activates automatically if the configured backend is not running, allowing Google Play reviewers to test all 4 tabs and workflows immediately.
