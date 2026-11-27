# DeliverEx Live — Real-Time Gemini Live Voice Agent & WhatsApp Field Ops

> **Google Hackathon Prototype** — Real-time native voice-to-voice Customer & Frontline Ops Agent for Indian MSME logistics, combining **Gemini Live API** (sub-second Hinglish/Indic voice + mid-sentence barge-in) with **WhatsApp Voice Notes**, **Tally/SAP ERP auto-sync**, and **1-Tap Manager Approval (Human-in-the-Loop)**.

### Live Production Server & Android App
- **Live Web App & Backend (Cloud Run):** https://deliverex-live-353183969363.asia-south1.run.app
- **Health & Go-Live Check:** https://deliverex-live-353183969363.asia-south1.run.app/api/health
- **Android APK Direct Download (Raju Bhai v1.2.0, Signed):** https://storage.googleapis.com/deliverex-downloads-353183969363/Raju-Bhai-v1.2.0.apk
- **Native Android App (Kotlin + Jetpack Compose, Play Store-ready):** [`android-app/`](./android-app) (see [`android-app/PLAY_STORE_RELEASE_GUIDE.md`](./android-app/PLAY_STORE_RELEASE_GUIDE.md))

---

## Why DeliverEx Live (v2) Beats Top Hackathon Winners
Benchmarked against Google Cloud Gemini Live Agent Challenge Grand Prize winners (*ORION*, *OpsVoice*, *drone-copilot*, *ARCHITECT*):
- **True Multimodality — See + Hear + Speak (Gemini Live API):** Bidirectional `16kHz/24kHz` PCM audio + live **Camera / Proof-of-Delivery JPEG video streaming** (`Show 2 Torn Bags` / webcam) so Gemini visually verifies damaged goods and attaches visual evidence directly to **Priya's 1-Tap Manager Approval Card**.
- **Native Real-Time Voice + Barge-In + Latency Sparkline:** Real mid-sentence interruption flush, turn-by-turn **TTFA Latency Sparkline (ms)**, and live **Acoustic Noise Floor (`42 dB` → `78 dB Busy Mandi`)** meter.
- **Pan-India Vernacular Code-Switching:** Live **Hinglish** (*Old Delhi — Krishna Hardware*) AND **Tanglish** (*Chennai T. Nagar — Murugan Builders*) out of the box.
- **Real-Time Understanding HUD + Frontline Staff Coach:** Live Intent, Code-Switch Detector, Sentiment Meter (`CALM → CONCERNED → FRUSTRATED → RESOLVED`), and actionable in-the-moment coaching & suggested de-escalation phrases for the field driver.
- **Grounded Organizational Knowledge + Live ERP + HITL:** Grounded in `SOP-4.2`, `SOP-5.1`, `SOP-2.3`, `SOP-6.0`, live SQLite **Tally/SAP Ledger + Warehouse Stock**, and **Priya's 1-Tap Approval / Reject / Live Call Takeover** looping back into the active call + official **WhatsApp Receipt Card**.
- **WhatsApp Channel & Cloud Run Ready:** Includes real Meta Cloud API webhook (`GET/POST /webhook/whatsapp`), async WhatsApp Voice Note tab, **Field Intelligence + ROI Calculator (Bonus)**, plus 1-command **Google Cloud Run** deployment (`Dockerfile` + `deploy_cloud_run.ps1`).

---

## Quickstart (Runs in 60 Seconds — Python Only, Zero Node Build!)

### 1. Create Virtual Environment & Install Dependencies
```powershell
cd deliverex-live
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Your Gemini API Key
```powershell
copy .env.example .env
```
Open `.env` and paste your key from Google AI Studio (`GEMINI_API_KEY=...`).

> **Note:** Even without a key, the app launches in **Interactive Demo Mode** so teammates can test the 3-panel UI, SQLite Tally/SAP updates, Priya's 1-tap approval, and ROI calculator immediately. Adding `GEMINI_API_KEY` automatically switches to **Live Gemini Voice-to-Voice API**.

### 3. Run the App
```powershell
uvicorn app.main:app --reload --port 8000
```
Open **http://localhost:8000** in Chrome.

---

## 3-Minute Winning Demo Flow
1. Click **🔊 Market Noise: ON** and **📞 Start Live Call**.
2. Speak in Hinglish (or click **Step 1**): *"Krishna Hardware pe 20 bags cement deliver kar diya aur ₹15,000 cash mil gaya."*
3. **Mid-sentence interrupt** while AI is speaking (or click **Step 2 ⚡ Interrupt**): *"Ruko ruko! 20 nahi, 18 bags intact the, 2 bags damaged nikle, aur uncle ₹500 extra discount maang rahe hain!"*
4. Watch **Barge-In** trigger, **SOP-4.2 & SOP-5.1** highlight, **Tally/SAP Ledger & Warehouse Stock** update live, and **Priya's 1-Tap Approval Card** pop up.
5. Click **✅ 1-Tap Approve** — watch the AI immediately speak the approval back to Raju in Hinglish and display the official **WhatsApp Receipt Card**.
6. Switch to **WhatsApp Note** tab (Yogesh's async flow) and **Insights & ROI (Bonus)** tab to close with unit economics (`13.6x ROI`, `₹2.20/call` vs `₹30/call`).
7. Before presenting to the next judge, click **↺ Reset Demo**.

---

## Optional: Connecting Real Meta WhatsApp Cloud API
1. Expose your local server with `ngrok http 8000` (or deploy to Google Cloud Run).
2. In Meta Developer Portal → WhatsApp → Configuration:
   - Callback URL: `https://<your-domain>/webhook/whatsapp`
   - Verify Token: `deliverex_hackathon_verify_2026` (matches `WHATSAPP_VERIFY_TOKEN` in `.env`)
3. Add `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` in `.env`.
