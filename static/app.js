// DeliverEx Live — Real-Time Gemini Live Audio + WhatsApp Field Ops Frontend

let healthInfo = { gemini_configured: false, live_model: "", whatsapp_configured: false };
let liveReady = false;
let ws = null;
let callActive = false;
let callTimerInterval = null;
let callStartTime = 0;

// Audio capture & playback state (Gemini Live API: 16kHz in, 24kHz out)
let captureCtx = null;
let mediaStream = null;
let workletNode = null;
let playbackCtx = null;
let nextPlayTime = 0;
let activeAudioSources = [];
let currentEnergy = 0.02;

// Ambient Market Noise synthesizer
let noiseCtx = null;
let noiseActive = false;
let noiseInterval = null;

// Live Multimodal Vision (Camera / Proof Photo) state
let cameraStream = null;
let cameraInterval = null;
let cameraActive = false;

// Latency Sparkline history
let latencyHistory = [];

// Live transcript & telemetry state
let interruptionCount = 0;
let currentRoleBubble = null;
let currentRole = null;
let highlightedPolicyIds = new Set();
let lastLedgerCount = 0;

// WhatsApp voice note MediaRecorder state
let waRecorder = null;
let waChunks = [];
let waRecording = false;

// --- INITIALIZATION ---
async function initApp() {
  drawWaveformLoop();
  updateRoiCalculator();
  try {
    const [hRes, sRes] = await Promise.all([fetch("/api/health"), fetch("/api/state")]);
    healthInfo = await hRes.json();
    const stateData = await sRes.json();

    const badge = document.getElementById("modeBadge");
    if (healthInfo.gemini_configured) {
      badge.textContent = `LIVE GEMINI API • ${healthInfo.live_model}`;
      badge.className = "text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
    } else {
      badge.textContent = "INTERACTIVE DEMO MODE (Add GEMINI_API_KEY in .env for Live Audio)";
      badge.className = "text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40";
    }

    renderPolicies(stateData.policies || []);
    renderErpState(stateData.state);
  } catch (err) {
    console.error("Init error:", err);
  }
}

// --- VIEW & TAB SWITCHING ---
function switchMainView(view) {
  const ops = document.getElementById("opsView");
  const ins = document.getElementById("insightsView");
  const bOps = document.getElementById("viewOpsBtn");
  const bIns = document.getElementById("viewInsightsBtn");

  if (view === "ops") {
    ops.classList.remove("hidden");
    ins.classList.add("hidden");
    bOps.className = "px-3 py-1 rounded-md text-xs font-semibold bg-emerald-500 text-slate-950 transition";
    bIns.className = "px-3 py-1 rounded-md text-xs font-semibold text-slate-300 hover:text-white transition";
  } else {
    ops.classList.add("hidden");
    ins.classList.remove("hidden");
    bIns.className = "px-3 py-1 rounded-md text-xs font-semibold bg-emerald-500 text-slate-950 transition";
    bOps.className = "px-3 py-1 rounded-md text-xs font-semibold text-slate-300 hover:text-white transition";
  }
}

function switchDriverTab(tab) {
  const livePanel = document.getElementById("driverLivePanel");
  const waPanel = document.getElementById("driverWhatsAppPanel");
  const tLive = document.getElementById("tabLiveCall");
  const tWa = document.getElementById("tabWhatsApp");

  if (tab === "live") {
    livePanel.classList.remove("hidden");
    waPanel.classList.add("hidden");
    tLive.className = "px-2.5 py-1 rounded-md font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
    tWa.className = "px-2.5 py-1 rounded-md font-semibold text-slate-400 hover:text-white";
  } else {
    livePanel.classList.add("hidden");
    waPanel.classList.remove("hidden");
    tWa.className = "px-2.5 py-1 rounded-md font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
    tLive.className = "px-2.5 py-1 rounded-md font-semibold text-slate-400 hover:text-white";
  }
}

// --- LIVE GEMINI VOICE CALL MANAGEMENT ---
async function toggleLiveCall() {
  if (callActive) {
    stopLiveCall();
  } else {
    await startLiveCall();
  }
}

async function startLiveCall() {
  callActive = true;
  callStartTime = Date.now();
  clearInterval(callTimerInterval);
  callTimerInterval = setInterval(updateCallTimer, 1000);

  const btn = document.getElementById("callToggleBtn");
  btn.textContent = "🔴 End Live Call";
  btn.className = "flex-1 py-2.5 px-4 rounded-xl font-bold text-sm bg-rose-500 hover:bg-rose-400 text-white transition shadow-lg shadow-rose-500/25";
  document.getElementById("avatarRing").classList.add("pulse-ring");
  document.getElementById("callStatusTitle").textContent = healthInfo.gemini_configured
    ? "Connecting to Gemini Live API..."
    : "Interactive Demo Call Active";
  document.getElementById("callStatusSub").textContent = healthInfo.gemini_configured
    ? "Speak Hinglish / Hindi / Tanglish naturally — interrupt anytime!"
    : "Click Step 1 → Step 2 (Interrupt!) below to preview full live workflow";

  // Connect WebSocket
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/live-call`);

  ws.onmessage = (evt) => handleServerEvent(JSON.parse(evt.data));
  ws.onclose = () => {
    if (callActive && healthInfo.gemini_configured) {
      setSpeakingIndicator("Disconnected", "slate");
    }
  };

  if (healthInfo.gemini_configured) {
    try {
      await startMicStreaming();
    } catch (err) {
      addSystemBanner(`Mic permission unavailable (${err.message}). You can still use the Live Script / text input below!`);
    }
  } else {
    setSpeakingIndicator("Demo Ready", "amber");
    addSystemBanner("Interactive Demo Mode active — click Step 1, then click Step 2 mid-speech to test real-time interruption + Tally/SAP ERP + Priya 1-tap approval!");
  }
}

function stopLiveCall() {
  callActive = false;
  clearInterval(callTimerInterval);
  document.getElementById("callTimer").textContent = "00:00";

  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }
  stopMicStreaming();
  flushPlaybackAudio();
  if (window.speechSynthesis) window.speechSynthesis.cancel();

  const btn = document.getElementById("callToggleBtn");
  btn.textContent = "📞 Start Live Call";
  btn.className = "flex-1 py-2.5 px-4 rounded-xl font-bold text-sm bg-emerald-500 hover:bg-emerald-400 text-slate-950 transition shadow-lg shadow-emerald-500/20";
  document.getElementById("avatarRing").classList.remove("pulse-ring");
  document.getElementById("callStatusTitle").textContent = "Tap to Start Real-Time Voice Call";
  setSpeakingIndicator("Idle", "slate");
}

function updateCallTimer() {
  const sec = Math.floor((Date.now() - callStartTime) / 1000);
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  document.getElementById("callTimer").textContent = `${mm}:${ss}`;
}

async function startMicStreaming() {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  captureCtx = new (window.AudioContext || window.webkitAudioContext)();
  await captureCtx.audioWorklet.addModule("/static/pcm-processor.js");

  const src = captureCtx.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(captureCtx, "pcm16-processor");

  workletNode.port.onmessage = (event) => {
    const { pcm, rms } = event.data;
    currentEnergy = Math.max(0.02, Math.min(1, rms * 8));
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const bytes = new Uint8Array(pcm);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    const b64 = btoa(binary);

    ws.send(JSON.stringify({
      type: "audio_chunk",
      data: b64,
      speaking: rms > 0.025,
    }));
  };

  src.connect(workletNode);
  workletNode.connect(captureCtx.destination);
}

function stopMicStreaming() {
  if (workletNode) {
    try { workletNode.disconnect(); } catch {}
    workletNode = null;
  }
  if (captureCtx) {
    try { captureCtx.close(); } catch {}
    captureCtx = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  currentEnergy = 0.02;
}

// --- 24kHz PCM AUDIO PLAYBACK + INSTANT BARGE-IN BUFFER FLUSH ---
function playPcm24kBase64(b64) {
  if (!playbackCtx) {
    playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    nextPlayTime = playbackCtx.currentTime;
  }
  if (playbackCtx.state === "suspended") playbackCtx.resume();

  const bin = atob(b64);
  const len = bin.length;
  const buf = new ArrayBuffer(len);
  const view = new Uint8Array(buf);
  for (let i = 0; i < len; i++) view[i] = bin.charCodeAt(i);

  const int16 = new Int16Array(buf);
  const float32 = new Float32Array(int16.length);
  let energySum = 0;
  for (let i = 0; i < int16.length; i++) {
    const f = int16[i] / 32768.0;
    float32[i] = f;
    energySum += Math.abs(f);
  }
  currentEnergy = Math.max(0.15, Math.min(1, (energySum / float32.length) * 6));

  const audioBuffer = playbackCtx.createBuffer(1, float32.length, 24000);
  audioBuffer.copyToChannel(float32, 0);

  const source = playbackCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playbackCtx.destination);

  const now = playbackCtx.currentTime;
  if (nextPlayTime < now) nextPlayTime = now + 0.02;
  source.start(nextPlayTime);
  nextPlayTime += audioBuffer.duration;

  activeAudioSources.push(source);
  source.onended = () => {
    activeAudioSources = activeAudioSources.filter((s) => s !== source);
  };
  setSpeakingIndicator("AI Speaking", "emerald");
}

function flushPlaybackAudio() {
  for (const s of activeAudioSources) {
    try { s.stop(); } catch {}
  }
  activeAudioSources = [];
  if (playbackCtx) nextPlayTime = playbackCtx.currentTime;
}

// --- SERVER WEBSOCKET EVENT HANDLER ---
function handleServerEvent(msg) {
  switch (msg.type) {
    case "status":
      liveReady = Boolean(msg.connected);
      document.getElementById("callStatusTitle").textContent = msg.connected
        ? "Live Call Active • Listening"
        : msg.message;
      if (msg.connected) {
        setSpeakingIndicator("Listening (Live)", "cyan");
        addSystemBanner(`Connected to ${msg.model}. Start speaking Hinglish/English or use the stage triggers.`);
      }
      break;

    case "audio_out":
      playPcm24kBase64(msg.data);
      break;

    case "latency":
      updateLatencyBadge(msg.ttfa_ms);
      break;

    case "interrupted":
      flushPlaybackAudio();
      interruptionCount = msg.count || (interruptionCount + 1);
      document.getElementById("bargeInBadge").textContent = String(interruptionCount);
      setSpeakingIndicator("⚡ Interrupted (Barge-In)", "amber");
      addInterruptionBadge();
      currentRoleBubble = null;
      currentRole = null;
      break;

    case "transcript":
      appendTranscript(msg.role, msg.text, msg.final);
      break;

    case "turn_complete":
      currentRoleBubble = null;
      currentRole = null;
      currentEnergy = 0.03;
      setSpeakingIndicator("Listening", "cyan");
      break;

    case "tool_call_start":
      logToolCall(msg.name, msg.args, "RUNNING", null);
      break;

    case "tool_call_result":
      logToolCall(msg.name, msg.args, msg.meta?.status || "OK", msg.meta?.elapsed_ms);
      if (msg.name === "check_company_policy" && msg.result?.matched_policies) {
        msg.result.matched_policies.forEach((p) => highlightedPolicyIds.add(p.id));
        refreshPoliciesHighlight();
      }
      if (msg.name === "update_frontline_guidance" && msg.meta?.guidance) {
        updateFrontlineHud(msg.meta.guidance);
      }
      break;

    case "erp_state":
      renderErpState(msg.state);
      break;

    case "manager_decision_event":
      handleManagerDecisionUi(msg);
      break;

    case "error":
      liveReady = false;
      addSystemBanner(`⚠️ ${msg.message} (Stage buttons 1–4 still work in Interactive Demo Mode!)`);
      setSpeakingIndicator("Demo Fallback Ready", "amber");
      break;
  }
}

function handleManagerDecisionUi(msg) {
  const { decision, approval, receipt } = msg;
  if (decision === "APPROVED") {
    addSystemBanner(`✅ Priya Sharma APPROVED ${approval.customer_name} (Rs ${approval.discount_requested} discount) — looped back to Raju's live call!`);
    if (receipt) showReceiptCard(receipt.receipt_id, receipt.message);
    if (!liveReady) {
      const reply = `Badhiya khabar Raju bhai! Priya ma'am ne Rs ${approval.discount_requested} special discount approve kar diya hai. ${approval.customer_name} ka invoice Tally mein settle ho gaya aur official receipt aapke WhatsApp pe bhej di gayi hai!`;
      speakDemoVoice(reply, 340);
    }
  } else if (decision === "REJECTED") {
    addSystemBanner(`❌ Priya Sharma REJECTED Rs ${approval.discount_requested} extra discount for ${approval.customer_name}.`);
    if (!liveReady) {
      const reply = `Raju bhai, Priya ma'am ne Rs ${approval.discount_requested} ka extra discount approve nahi kiya hai. Remaining balance customer ke credit account mein open rahega.`;
      speakDemoVoice(reply, 360);
    }
  } else if (decision === "TAKE_OVER") {
    addSystemBanner(`📞 Area Manager Priya Sharma is taking over the live call for ${approval.customer_name}!`);
    if (!liveReady) {
      const reply = `Raju bhai, main aapko seedha Priya ma'am se connect kar raha hoon. Unke paas aapki poori delivery details screen par aa chuki hain.`;
      speakDemoVoice(reply, 310);
    }
  }
}

// --- GUIDED DEMO STEPS & CUSTOM TEXT (Works in BOTH Live Gemini API & Demo Mode!) ---
async function runGuidedStep(step) {
  if (!callActive) await startLiveCall();
  const useLiveWs = healthInfo.gemini_configured && liveReady && ws && ws.readyState === WebSocket.OPEN;

  if (step === 1) {
    const text = "Hello, main Raju bol raha hoon Old Delhi market se. Krishna Hardware pe 20 bags cement deliver kar diya aur 15000 rupees cash mil gaya.";
    if (useLiveWs) {
      ws.send(JSON.stringify({ type: "text_turn", text }));
    } else {
      await runOfflineDemoStep1(text);
    }
  } else if (step === 2) {
    const text = "Ruko ruko! 20 nahi, 18 bags sahi deliver hue hain, 2 bags phate hue damaged nikle. Aur uncle bol rahe hain 500 rupees extra discount de do aur 15000 mein invoice settle kar lo!";
    if (useLiveWs) {
      flushPlaybackAudio();
      interruptionCount += 1;
      document.getElementById("bargeInBadge").textContent = String(interruptionCount);
      addInterruptionBadge();
      ws.send(JSON.stringify({ type: "text_turn", text }));
    } else {
      await runOfflineDemoStep2(text);
    }
  } else if (step === 3) {
    const text = "Uncle gussa ho rahe hain invoice balance pe, please Priya ma'am se direct baat karwa do!";
    if (useLiveWs) {
      ws.send(JSON.stringify({ type: "text_turn", text }));
    } else {
      await runOfflineDemoStep3(text);
    }
  } else if (step === 4) {
    const text = "Anna, T. Nagar Murugan Builders-la 25 bags cement unload pannitten, 18400 cash kedaichuduchu, receipt WhatsApp-la anuppunga!";
    if (useLiveWs) {
      ws.send(JSON.stringify({ type: "text_turn", text }));
    } else {
      await runOfflineDemoStep4Tanglish(text);
    }
  }
}

function sendCustomTextTurn(e) {
  e.preventDefault();
  const input = document.getElementById("customTextInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  if (!callActive) {
    startLiveCall().then(() => dispatchCustomText(text));
  } else {
    dispatchCustomText(text);
  }
}

async function dispatchCustomText(text) {
  if (healthInfo.gemini_configured && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "text_turn", text }));
  } else {
    appendTranscript("user", text, true);
    const res = await fetch("/api/whatsapp/voice-note", {
      method: "POST",
      body: toFormData({ text, driver_name: "Raju Kumar" }),
    }).then((r) => r.json());
    renderErpState(res.state);
    logToolCall("record_delivery_and_update_ledger", res.extracted, "OK", res.processing_ms);
    speakDemoVoice(res.whatsapp_reply.replace(/\n/g, " "), 410);
  }
}

// --- INTERACTIVE OFFLINE DEMO ENGINE (Real SQLite ERP Tools + Browser Voice + Real Barge-In) ---
async function runOfflineDemoStep1(userText) {
  appendTranscript("user", userText, true);
  setSpeakingIndicator("Thinking + Tool Call", "cyan");

  updateFrontlineHud({
    intent: "DELIVERY_AND_CASH_LOG",
    language: "Hinglish (HI+EN)",
    sentiment: "CALM",
    coach_tip: "Verify intact bag count against INV-8841 (20 bags expected, ₹15,500 due).",
    suggested_phrase: "Uncle, 20 bags ka invoice ₹15,500 hai — ₹15,000 cash count kar liya.",
  });

  const r1 = await callDemoTool("lookup_customer_and_invoice", { customer_name: "Krishna Hardware" });
  logToolCall("lookup_customer_and_invoice", { customer_name: "Krishna Hardware" }, "OK", r1.meta.elapsed_ms);

  const aiReply =
    "Ji Raju bhai, Krishna Hardware (ID CUST-104) ka pending invoice INV-8841 mil gaya — total 20 bags UltraTech Cement aur Rs 15,500 due hai. Main 20 bags aur Rs 15,000 cash Tally ledger mein post karne jaa raha hoon, baaki Rs 500 balance...";
  speakDemoVoice(aiReply, 420);
}

async function runOfflineDemoStep2(userText) {
  // Simulate immediate mid-sentence barge-in!
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  flushPlaybackAudio();
  interruptionCount += 1;
  document.getElementById("bargeInBadge").textContent = String(interruptionCount);
  addInterruptionBadge();
  setSpeakingIndicator("⚡ Interrupted (Barge-In)", "amber");

  appendTranscript("user", userText, true);

  updateFrontlineHud({
    intent: "DAMAGE_CLAIM + SPOT_DISCOUNT_EXCEPTION",
    language: "Hinglish (HI+EN)",
    sentiment: "CONCERNED",
    coach_tip: "Policy SOP-4.2 & SOP-5.1 triggered! Click 'Show 2 Torn Bags' to attach visual proof for Priya Ma'am.",
    suggested_phrase: "Uncle chinta mat karo — maine Priya ma'am ko photo aur ₹500 discount approval bhej diya hai, 10 second mein confirmation aa jayega!",
  });

  const rPol = await callDemoTool("check_company_policy", { topic: "discount damaged bags" });
  logToolCall("check_company_policy", { topic: "discount damaged bags" }, "OK", rPol.meta.elapsed_ms);
  (rPol.result.matched_policies || []).forEach((p) => highlightedPolicyIds.add(p.id));
  refreshPoliciesHighlight();

  const args = {
    customer_name: "Krishna Hardware",
    delivered_bags: 18,
    damaged_bags: 2,
    cash_received: 15000,
    discount_requested: 500,
    driver_name: "Raju Kumar",
    notes: "18 intact bags delivered, 2 damaged bags quarantined, Rs 500 spot discount requested",
  };
  const rLed = await callDemoTool("record_delivery_and_update_ledger", args);
  logToolCall("record_delivery_and_update_ledger", args, rLed.meta.status, rLed.meta.elapsed_ms);
  renderErpState(rLed.state);

  const aiReply =
    "Achha samajh gaya Raju bhai — 18 bags delivered, 2 damaged bags quarantine mein, aur Rs 15,000 cash Tally ledger mein post kar diya hai. Company Policy SOP-4.2 ke hisaab se Rs 200 se zyada discount aur damaged stock ke liye Area Manager Priya ma'am ki approval zaroori hai. Maine unko WhatsApp par 1-tap approval bhej diya hai — aap 'Show 2 Torn Bags' se photo bhi attach kar sakte ho!";
  speakDemoVoice(aiReply, 385);
}

async function runOfflineDemoStep3(userText) {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  appendTranscript("user", userText, true);

  updateFrontlineHud({
    intent: "CUSTOMER_DISPUTE_ESCALATION",
    language: "Hinglish (HI+EN)",
    sentiment: "FRUSTRATED",
    coach_tip: "De-escalate calmly. Warm handoff packet + transcript already sent to Priya Sharma (SOP-6.0).",
    suggested_phrase: "Sir, hamari Area Manager Priya ma'am abhi 5 second mein line par jud rahi hain.",
  });

  const args = {
    customer_name: "Krishna Hardware",
    reason: "Shop owner disputing remaining invoice balance — requested direct live call with Area Manager Priya Sharma",
  };
  const rHandoff = await callDemoTool("request_human_handoff", args);
  logToolCall("request_human_handoff", args, "HANDOFF", rHandoff.meta.elapsed_ms);
  renderErpState(rHandoff.state);

  const aiReply =
    "Bilkul Raju bhai, chinta mat karo. Company Policy SOP-6.0 ke tahat maine Area Manager Priya ma'am ko poori call summary ke saath Live Call Takeover alert bhej diya hai. Wo abhi join kar rahi hain.";
  speakDemoVoice(aiReply, 350);
}

async function runOfflineDemoStep4Tanglish(userText) {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  appendTranscript("user", userText, true);

  updateFrontlineHud({
    intent: "CLEAN_DELIVERY_SETTLEMENT",
    language: "Tanglish (TA+EN)",
    sentiment: "POSITIVE",
    coach_tip: "Exact match with INV-8862 (25 bags, ₹18,400). Auto-settling in Tally/SAP — no manager approval needed!",
    suggested_phrase: "Sir, 25 bags & ₹18,400 cash Tally-la settle aayiduchu. Official WhatsApp receipt vandhuruchu!",
  });

  const r1 = await callDemoTool("lookup_customer_and_invoice", { customer_name: "Murugan Builders" });
  logToolCall("lookup_customer_and_invoice", { customer_name: "Murugan Builders" }, "OK", r1.meta.elapsed_ms);

  const args = {
    customer_name: "Murugan Builders",
    delivered_bags: 25,
    damaged_bags: 0,
    cash_received: 18400,
    discount_requested: 0,
    driver_name: "Karthik (Chennai Route-7)",
    notes: "Tanglish voice settlement — 25 intact bags delivered, Rs 18,400 full cash",
  };
  const rLed = await callDemoTool("record_delivery_and_update_ledger", args);
  logToolCall("record_delivery_and_update_ledger", args, rLed.meta.status, rLed.meta.elapsed_ms);
  renderErpState(rLed.state);

  const aiReply =
    "Super anna! Murugan Builders T. Nagar invoice INV-8862 full settle aayiduchu — 25 bags intact, Rs 18,400 cash Tally ledger-la update pannitten, official WhatsApp receipt-um anuppitten!";
  speakDemoVoice(aiReply, 360);
}

async function callDemoTool(name, args) {
  const res = await fetch("/api/demo/tool", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, args, channel: "GEMINI_LIVE_VOICE" }),
  });
  return await res.json();
}

function speakDemoVoice(text, simulatedTtfaMs) {
  updateLatencyBadge(simulatedTtfaMs);
  appendTranscript("assistant", text, true);
  setSpeakingIndicator("AI Speaking", "emerald");
  currentEnergy = 0.45;

  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-IN";
    utter.rate = 1.08;
    utter.onend = () => {
      currentEnergy = 0.03;
      setSpeakingIndicator("Listening", "cyan");
    };
    window.speechSynthesis.speak(utter);
  } else {
    setTimeout(() => {
      currentEnergy = 0.03;
      setSpeakingIndicator("Listening", "cyan");
    }, 2500);
  }
}

// --- PRIYA'S 1-TAP MANAGER APPROVAL (HITL) ---
async function decideApproval(approvalId, decision) {
  try {
    const res = await fetch(`/api/approvals/${approvalId}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    const data = await res.json();
    renderErpState(data.state);

    // If WebSocket isn't active, still update local UI smoothly
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      handleManagerDecisionUi(data);
    }
  } catch (err) {
    console.error("Approval error:", err);
  }
}

// --- WHATSAPP VOICE NOTE TAB (YOGESH'S ASYNC FLOW) ---
async function toggleWhatsAppRecord() {
  const btn = document.getElementById("waRecordBtn");
  if (!waRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      waRecorder = new MediaRecorder(stream);
      waChunks = [];
      waRecorder.ondataavailable = (e) => { if (e.data.size > 0) waChunks.push(e.data); };
      waRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(waChunks, { type: "audio/webm" });
        await uploadWhatsAppVoiceNote(blob, null);
      };
      waRecorder.start();
      waRecording = true;
      btn.textContent = "⏹ Stop & Send Voice Note";
      btn.className = "flex-1 py-2 px-3 rounded-xl bg-rose-500 hover:bg-rose-400 text-white font-bold text-xs transition";
    } catch (err) {
      appendWaBubble("system", `Mic unavailable (${err.message}). Click "Send Sample Hinglish Note" instead!`);
    }
  } else {
    waRecording = false;
    waRecorder.stop();
    btn.textContent = "🎤 Record Voice Note";
    btn.className = "flex-1 py-2 px-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition";
  }
}

async function sendSampleWhatsAppNote() {
  const sampleText =
    "Shri Ganesh Stores pe 30 bags ACC cement deliver kar diya, 22000 cash received, koi damage nahi hai.";
  await uploadWhatsAppVoiceNote(null, sampleText);
}

async function uploadWhatsAppVoiceNote(audioBlob, textFallback) {
  appendWaBubble(
    "driver",
    audioBlob
      ? "🎤 [WhatsApp Voice Note • 0:08 • OGG/WEBM] Sending to Meta Webhook..."
      : `🎤 [Voice Note] "${textFallback}"`
  );

  const fd = new FormData();
  if (audioBlob) fd.append("file", audioBlob, "voice_note.webm");
  if (textFallback) fd.append("text", textFallback);
  fd.append("driver_name", "Raju Kumar");

  const res = await fetch("/api/whatsapp/voice-note", { method: "POST", body: fd }).then((r) => r.json());
  renderErpState(res.state);
  logToolCall("whatsapp_voice_note_webhook", res.extracted, res.used_gemini ? "GEMINI_AUDIO" : "PARSED", res.processing_ms);

  appendWaBubble(
    "bot",
    `${res.whatsapp_reply}\n\n⚡ Processed in ${res.processing_ms}ms (${res.used_gemini ? "Gemini Multimodal Audio" : "Demo Parser"})`
  );
  if (res.erp_result?.receipt) {
    showReceiptCard(res.erp_result.receipt.receipt_id, res.erp_result.receipt.message);
  }
}

function appendWaBubble(sender, text) {
  const feed = document.getElementById("waChatFeed");
  const div = document.createElement("div");
  if (sender === "driver") {
    div.className = "ml-auto bg-emerald-700/80 text-white text-xs p-2.5 rounded-xl rounded-tr-none max-w-[88%] whitespace-pre-wrap";
  } else if (sender === "bot") {
    div.className = "bg-slate-800/95 text-slate-100 text-xs p-2.5 rounded-xl rounded-tl-none max-w-[92%] border border-emerald-500/30 whitespace-pre-wrap";
  } else {
    div.className = "text-center text-[11px] text-amber-300 bg-amber-500/10 rounded-lg py-1 px-2";
  }
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// --- REALISTIC MARKET NOISE SYNTHESIZER (No external audio files needed!) ---
function toggleMarketNoise() {
  const btn = document.getElementById("noiseToggleBtn");
  const dbBadge = document.getElementById("noiseDbBadge");
  if (noiseActive) {
    noiseActive = false;
    clearInterval(noiseInterval);
    if (noiseCtx) { try { noiseCtx.close(); } catch {} noiseCtx = null; }
    btn.textContent = "🔊 Noise: OFF";
    btn.className = "py-2.5 px-2.5 rounded-xl font-semibold text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition";
    if (dbBadge) {
      dbBadge.textContent = "42 dB";
      dbBadge.className = "mono text-xs font-bold text-cyan-300";
    }
    return;
  }

  noiseActive = true;
  btn.textContent = "🔊 Noise: 78dB";
  btn.className = "py-2.5 px-2.5 rounded-xl font-semibold text-xs bg-amber-500/20 text-amber-300 border border-amber-500/40 transition";
  if (dbBadge) {
    dbBadge.textContent = "78 dB MANDI";
    dbBadge.className = "mono text-xs font-bold text-amber-400";
  }

  noiseCtx = new (window.AudioContext || window.webkitAudioContext)();
  // Pink-ish filtered street/crowd murmur
  const bufferSize = noiseCtx.sampleRate * 2;
  const noiseBuffer = noiseCtx.createBuffer(1, bufferSize, noiseCtx.sampleRate);
  const output = noiseBuffer.getChannelData(0);
  let b0 = 0, b1 = 0, b2 = 0;
  for (let i = 0; i < bufferSize; i++) {
    const white = Math.random() * 2 - 1;
    b0 = 0.997 * b0 + white * 0.029;
    b1 = 0.985 * b1 + white * 0.032;
    b2 = 0.950 * b2 + white * 0.048;
    output[i] = (b0 + b1 + b2 + white * 0.015) * 0.28;
  }
  const src = noiseCtx.createBufferSource();
  src.buffer = noiseBuffer;
  src.loop = true;

  const filter = noiseCtx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = 650;
  filter.Q.value = 0.7;

  const gain = noiseCtx.createGain();
  gain.gain.value = 0.16;

  src.connect(filter);
  filter.connect(gain);
  gain.connect(noiseCtx.destination);
  src.start();

  // Occasional subtle Indian scooter/truck horn beep in background
  noiseInterval = setInterval(() => {
    if (!noiseCtx || !noiseActive) return;
    const osc = noiseCtx.createOscillator();
    const g = noiseCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = Math.random() > 0.5 ? 440 : 520;
    g.gain.setValueAtTime(0.001, noiseCtx.currentTime);
    g.gain.linearRampToValueAtTime(0.035, noiseCtx.currentTime + 0.04);
    g.gain.exponentialRampToValueAtTime(0.0001, noiseCtx.currentTime + 0.28);
    osc.connect(g);
    g.connect(noiseCtx.destination);
    osc.start();
    osc.stop(noiseCtx.currentTime + 0.3);
  }, 4500);
}

// --- UI RENDERERS ---
function appendTranscript(role, text, isFinal) {
  const feed = document.getElementById("transcriptFeed");
  if (feed.children.length === 1 && feed.firstElementChild.textContent.includes("Start a Live Call")) {
    feed.innerHTML = "";
  }

  if (!isFinal && currentRole === role && currentRoleBubble) {
    currentRoleBubble.querySelector(".bubble-text").textContent += text;
    feed.scrollTop = feed.scrollHeight;
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = role === "user"
    ? "p-2.5 rounded-xl bg-slate-800/90 border border-slate-700/80 ml-4"
    : "p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-500/30 mr-4";

  const label = role === "user"
    ? `<span class="text-[10px] font-bold uppercase text-cyan-300">🚚 Raju (Field Driver)</span>`
    : `<span class="text-[10px] font-bold uppercase text-emerald-400">🤖 DeliverEx Live AI</span>`;

  wrap.innerHTML = `${label}<div class="bubble-text text-slate-100 mt-0.5 leading-relaxed"></div>`;
  wrap.querySelector(".bubble-text").textContent = text;
  feed.appendChild(wrap);
  feed.scrollTop = feed.scrollHeight;

  if (!isFinal) {
    currentRole = role;
    currentRoleBubble = wrap;
  } else {
    currentRole = null;
    currentRoleBubble = null;
  }
}

function addInterruptionBadge() {
  const feed = document.getElementById("transcriptFeed");
  const div = document.createElement("div");
  div.className = "text-center my-1";
  div.innerHTML = `<span class="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">⚡ Mid-Sentence Interruption (Barge-In) — AI Audio Flushed</span>`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function addSystemBanner(text) {
  const feed = document.getElementById("transcriptFeed");
  if (feed.children.length === 1 && feed.firstElementChild.textContent.includes("Start a Live Call")) {
    feed.innerHTML = "";
  }
  const div = document.createElement("div");
  div.className = "text-[11px] text-cyan-200 bg-cyan-950/40 border border-cyan-500/25 rounded-lg px-2.5 py-1.5";
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function logToolCall(name, args, status, elapsedMs) {
  const box = document.getElementById("toolLog");
  if (box.children.length === 1 && box.firstElementChild.textContent.includes("Waiting for spoken")) {
    box.innerHTML = "";
  }
  const row = document.createElement("div");
  const color = status === "ESCALATED" || status === "HANDOFF"
    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  row.className = `p-2 rounded-lg border ${color}`;
  const timeTxt = elapsedMs != null ? `${elapsedMs}ms` : "running...";
  row.innerHTML = `
    <div class="flex items-center justify-between font-bold">
      <span>⚙ ${name}()</span>
      <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-950/60">${status} • ${timeTxt}</span>
    </div>
    <div class="text-[10px] text-slate-300 mt-1 truncate">${escapeHtml(JSON.stringify(args || {}))}</div>
  `;
  box.prepend(row);
}

let cachedPolicies = [];
function renderPolicies(policies) {
  cachedPolicies = policies;
  refreshPoliciesHighlight();
}

function refreshPoliciesHighlight() {
  const el = document.getElementById("policyList");
  el.innerHTML = cachedPolicies
    .map((p) => {
      const active = highlightedPolicyIds.has(p.id);
      return `
        <div class="p-2.5 rounded-xl border transition ${
          active
            ? "bg-cyan-500/15 border-cyan-400/60 shadow-sm shadow-cyan-500/20"
            : "bg-slate-900/60 border-slate-800"
        }">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold ${active ? "text-cyan-300" : "text-slate-200"}">${p.id}: ${p.title}</span>
            ${active ? `<span class="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-cyan-400 text-slate-950">GROUNDED</span>` : ""}
          </div>
          <p class="text-[11px] text-slate-400 mt-1 leading-snug">${p.rule}</p>
        </div>
      `;
    })
    .join("");
}

function renderErpState(state) {
  if (!state) return;

  // 1. Manager Priya Approvals
  const approvals = state.approvals || [];
  const pending = approvals.filter((a) => a.status === "PENDING");
  const pBadge = document.getElementById("pendingApprovalCount");
  pBadge.textContent = `${pending.length} Pending`;
  pBadge.className = pending.length > 0
    ? "mono text-xs font-bold px-2.5 py-0.5 rounded-full bg-amber-500 text-slate-950 animate-pulse"
    : "mono text-xs font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300";

  const qEl = document.getElementById("approvalQueue");
  if (approvals.length === 0) {
    qEl.innerHTML = `<div class="text-xs text-slate-500 bg-slate-900/50 rounded-xl p-3 border border-slate-800/80 text-center">No policy exceptions yet. Routine deliveries auto-sync to Tally/SAP!</div>`;
  } else {
    qEl.innerHTML = approvals
      .map((a) => {
        const isPending = a.status === "PENDING";
        const statusClass =
          a.status === "APPROVED"
            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
            : a.status === "REJECTED"
            ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
            : a.status === "TAKE_OVER"
            ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
            : "bg-amber-500/20 text-amber-300 border-amber-500/50";
        return `
          <div class="p-3 rounded-xl border ${isPending ? "bg-amber-950/25 border-amber-500/50" : "bg-slate-900/60 border-slate-800"}">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-bold text-white">${escapeHtml(a.customer_name)} <span class="mono text-[10px] text-cyan-300">(${a.policy_ref})</span></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${statusClass}">${a.status}</span>
            </div>
            <p class="text-[11px] text-slate-300 mt-1">${escapeHtml(a.summary)}</p>
            ${
              a.proof_image
                ? `<div class="mt-2 rounded-lg overflow-hidden border border-cyan-500/35 bg-slate-950/70">
                     <img src="${a.proof_image}" alt="Visual proof of damage" class="w-full h-24 object-cover" />
                     <div class="px-2 py-1 text-[10px] text-cyan-300 flex items-center justify-between">
                       <span>👁️ Gemini Vision Verified Proof</span>
                       <span class="mono text-slate-400">GPS: Old Delhi Mandi</span>
                     </div>
                   </div>`
                : ""
            }
            ${
              isPending
                ? `<div class="flex gap-1.5 mt-2.5">
                     <button onclick="decideApproval('${a.approval_id}', 'APPROVED')" class="flex-1 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition">✅ 1-Tap Approve</button>
                     <button onclick="decideApproval('${a.approval_id}', 'REJECTED')" class="px-2.5 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 font-bold text-xs transition">❌ Reject</button>
                     <button onclick="decideApproval('${a.approval_id}', 'TAKE_OVER')" class="px-2.5 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 font-bold text-xs transition">📞 Take Over</button>
                   </div>`
                : `<div class="text-[10px] text-slate-400 mt-1.5">Decided by Priya Sharma &bull; ${a.decided_at || ""}</div>`
            }
          </div>
        `;
      })
      .join("");
  }

  // 2. Tally / SAP Ledger Table
  const ledger = state.ledger || [];
  const shouldFlash = ledger.length > lastLedgerCount;
  lastLedgerCount = ledger.length;
  const tbody = document.getElementById("ledgerTableBody");
  tbody.innerHTML = ledger
    .map((r, idx) => {
      const badgeColor = r.tally_status.includes("PENDING")
        ? "bg-amber-500/15 text-amber-300"
        : r.tally_status.includes("REJECTED")
        ? "bg-rose-500/15 text-rose-300"
        : "bg-emerald-500/15 text-emerald-300";
      return `
        <tr class="${shouldFlash && idx === 0 ? "flash-row" : ""}">
          <td class="py-2 pr-2">
            <div class="font-bold text-white">${escapeHtml(r.customer_name)}</div>
            <div class="mono text-[10px] text-slate-400">${r.entry_id} &bull; ${r.invoice_id}</div>
          </td>
          <td class="py-2 pr-2 mono">
            <div class="text-emerald-300">${r.delivered_qty} ok</div>
            ${r.damaged_qty > 0 ? `<div class="text-rose-400 text-[10px]">${r.damaged_qty} dmg</div>` : ""}
          </td>
          <td class="py-2 pr-2 mono">
            <div class="text-white">₹${Number(r.cash_received).toLocaleString("en-IN")}</div>
            ${r.discount_amount > 0 ? `<div class="text-cyan-300 text-[10px]">-₹${r.discount_amount} disc</div>` : ""}
          </td>
          <td class="py-2">
            <span class="text-[9px] font-bold px-1.5 py-0.5 rounded ${badgeColor}">${r.tally_status.replaceAll("_", " ")}</span>
          </td>
        </tr>
      `;
    })
    .join("");

  // 3. Warehouse Inventory & Open Customer Invoices
  const invCustEl = document.getElementById("inventoryAndCustomers");
  const invHtml = (state.inventory || [])
    .map(
      (i) => `
      <div class="flex items-center justify-between text-[11px] bg-slate-900/70 px-2.5 py-1.5 rounded-lg border border-slate-800">
        <div>
          <span class="font-semibold text-slate-200">${escapeHtml(i.item_name)}</span>
          <span class="mono text-[10px] text-slate-500 ml-1">(${i.sku_code})</span>
        </div>
        <div class="mono flex items-center gap-2">
          <span class="text-emerald-300 font-bold">${i.warehouse_stock} in stock</span>
          <span class="text-rose-400 text-[10px]">${i.damaged_quarantine} dmg</span>
        </div>
      </div>`
    )
    .join("");

  const custHtml = (state.customers || [])
    .map(
      (c) => `
      <div class="flex items-center justify-between text-[11px] bg-slate-950/60 px-2.5 py-1.5 rounded-lg border border-slate-800/80">
        <div>
          <span class="font-semibold text-white">${escapeHtml(c.name)}</span>
          <span class="mono text-[10px] text-slate-400 ml-1">${c.pending_invoice_id}</span>
        </div>
        <div class="mono flex items-center gap-2">
          <span class="${c.balance_due === 0 ? "text-emerald-400" : "text-amber-300"} font-bold">Due: ₹${Number(c.balance_due).toLocaleString("en-IN")}</span>
          <span class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">${c.status}</span>
        </div>
      </div>`
    )
    .join("");

  invCustEl.innerHTML = `
    <div class="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Warehouse Stock</div>
    ${invHtml}
    <div class="text-[10px] uppercase tracking-wider text-slate-400 font-bold mt-1">Customer Invoices</div>
    ${custHtml}
  `;

  // 4. Latest Receipt Card
  const receipts = state.receipts || [];
  if (receipts.length > 0) {
    showReceiptCard(receipts[0].receipt_id, receipts[0].message_text);
  } else {
    document.getElementById("receiptCardBox").classList.add("hidden");
  }

  // 5. Bonus Field Insights
  const insEl = document.getElementById("insightsList");
  insEl.innerHTML = (state.insights || [])
    .map((ins) => {
      const sevColor =
        ins.severity === "HIGH"
          ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
          : ins.severity === "MEDIUM"
          ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
          : "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
      return `
        <div class="p-3.5 rounded-xl bg-slate-900/75 border border-slate-800">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-bold text-white">${escapeHtml(ins.title)}</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${sevColor}">${ins.severity}</span>
          </div>
          <p class="text-xs text-slate-300 mt-1">${escapeHtml(ins.detail)}</p>
          <div class="text-[10px] text-slate-500 mt-1.5 mono">${ins.route} &bull; ${ins.category} &bull; ${ins.created_at}</div>
        </div>
      `;
    })
    .join("");
}

function showReceiptCard(receiptId, text) {
  document.getElementById("receiptCardBox").classList.remove("hidden");
  document.getElementById("receiptIdBadge").textContent = receiptId;
  document.getElementById("receiptCardText").textContent = text;
}

function updateLatencyBadge(ms) {
  const el = document.getElementById("latencyBadge");
  el.textContent = `${ms} ms`;
  el.className = ms < 900 ? "mono text-xs font-bold text-emerald-400" : "mono text-xs font-bold text-amber-400";
  latencyHistory.push(ms);
  if (latencyHistory.length > 12) latencyHistory.shift();
  renderLatencySparkline();
}

function renderLatencySparkline() {
  const canvas = document.getElementById("latencySparkline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (latencyHistory.length === 0) return;

  const maxVal = Math.max(900, ...latencyHistory);
  const bw = Math.max(3, Math.floor(w / Math.max(6, latencyHistory.length)) - 1);
  latencyHistory.forEach((v, i) => {
    const bh = Math.max(3, Math.round((v / maxVal) * (h - 2)));
    ctx.fillStyle = v < 600 ? "#10b981" : v < 900 ? "#38bdf8" : "#f59e0b";
    ctx.fillRect(i * (bw + 1) + 1, h - bh, bw, bh);
  });
}

// --- LIVE MULTIMODAL VISION PROOF-OF-DELIVERY (See + Hear + Speak) ---
async function toggleLiveCamera() {
  const btn = document.getElementById("cameraToggleBtn");
  const video = document.getElementById("cameraPreview");
  const badge = document.getElementById("visionStatusBadge");

  if (cameraActive) {
    cameraActive = false;
    clearInterval(cameraInterval);
    if (cameraStream) cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
    video.classList.add("hidden");
    btn.textContent = "📷 Live Camera";
    badge.textContent = "Ready";
    return;
  }

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 270 } });
    video.srcObject = cameraStream;
    video.classList.remove("hidden");
    document.getElementById("proofThumbPreview").classList.add("hidden");
    cameraActive = true;
    btn.textContent = "⏹ Stop Camera";
    badge.textContent = "Streaming 1 FPS";

    const snapAndSend = async (includePrompt) => {
      if (!video.videoWidth) return;
      const c = document.createElement("canvas");
      c.width = 480;
      c.height = 270;
      c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
      const dataUrl = c.toDataURL("image/jpeg", 0.72);
      await dispatchProofFrame(
        dataUrl,
        "Live Camera Proof",
        includePrompt ? "Yeh dekho camera pe live dikha raha hoon — check karo kitne bags damaged hain!" : null
      );
    };

    setTimeout(() => snapAndSend(true), 600);
    cameraInterval = setInterval(() => snapAndSend(false), 3000);
  } catch (err) {
    addSystemBanner(`Camera unavailable (${err.message}). Click "Show 2 Torn Bags" to test visual verification!`);
  }
}

async function sendSampleDamagePhoto() {
  if (!callActive) await startLiveCall();
  const dataUrl = generateSampleDamageProofImage();
  const img = document.getElementById("proofThumbPreview");
  img.src = dataUrl;
  img.classList.remove("hidden");
  document.getElementById("cameraPreview").classList.add("hidden");
  document.getElementById("visionStatusBadge").textContent = "2 Torn Bags Verified";

  await dispatchProofFrame(
    dataUrl,
    "2 Torn UltraTech Cement Bags (Old Delhi Market)",
    "Yeh dekho photo bhej diya hai — 2 UltraTech Cement bags phate hue hain. Verify karke Priya ma'am ko bhej do!"
  );

  if (!liveReady) {
    logToolCall("gemini_live_vision_inspect", { frame: "jpeg_480x270", detected: "2 torn cement bags" }, "VERIFIED", 290);
    updateFrontlineHud({
      intent: "VISUAL_DAMAGE_VERIFIED",
      language: "Hinglish (HI+EN)",
      sentiment: "CALM",
      coach_tip: "2 torn UltraTech bags visually verified & attached directly to Priya Sharma's 1-Tap Approval Card!",
      suggested_phrase: "Uncle, photo AI ne verify karke Priya ma'am ko bhej di hai — ab 1-tap approval turant ho jayega.",
    });
    speakDemoVoice(
      "Haan Raju bhai, camera photo mein 2 torn UltraTech Cement bags clear dikh rahe hain! Maine yeh visual proof seedha Priya ma'am ke approval card par attach kar diya hai.",
      310
    );
  }
}

async function dispatchProofFrame(dataUrl, caption, prompt) {
  if (liveReady && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "video_frame", data_url: dataUrl, caption, prompt }));
  } else {
    const res = await fetch("/api/proof-photo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_url: dataUrl, caption }),
    }).then((r) => r.json());
    renderErpState(res.state);
  }
}

function generateSampleDamageProofImage() {
  const c = document.createElement("canvas");
  c.width = 480;
  c.height = 240;
  const ctx = c.getContext("2d");

  // Warehouse truck bed backdrop
  const grad = ctx.createLinearGradient(0, 0, 480, 240);
  grad.addColorStop(0, "#1e293b");
  grad.addColorStop(1, "#0f172a");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 480, 240);

  // Draw two stylized torn cement bags with AI bounding boxes
  const drawBag = (x, y, label) => {
    ctx.fillStyle = "#cbd5e1";
    ctx.beginPath();
    ctx.roundRect(x, y, 165, 115, 14);
    ctx.fill();
    ctx.fillStyle = "#facc15";
    ctx.fillRect(x + 10, y + 18, 145, 28);
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 14px Inter, sans-serif";
    ctx.fillText("ULTRATECH 50KG", x + 22, y + 37);

    // Tear mark + spilled cement dust
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x + 40, y + 60);
    ctx.lineTo(x + 75, y + 82);
    ctx.lineTo(x + 115, y + 70);
    ctx.lineTo(x + 135, y + 96);
    ctx.stroke();

    // Vision detection bounding box
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 6, y - 6, 177, 127);
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(x - 6, y - 24, 155, 18);
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 11px monospace";
    ctx.fillText(label, x, y - 11);
  };

  drawBag(45, 65, "TORN_BAG #1 (96% conf)");
  drawBag(260, 65, "TORN_BAG #2 (94% conf)");

  // Timestamp + GPS watermark
  ctx.fillStyle = "rgba(2, 6, 23, 0.78)";
  ctx.fillRect(0, 206, 480, 34);
  ctx.fillStyle = "#34d399";
  ctx.font = "bold 11px monospace";
  ctx.fillText(`DELIVEREX CAM • OLD DELHI MANDI • ${new Date().toLocaleTimeString()} • INV-8841`, 14, 227);

  return c.toDataURL("image/jpeg", 0.85);
}

// --- FRONTLINE UNDERSTANDING & COACH HUD ---
function updateFrontlineHud(g) {
  if (!g) return;
  document.getElementById("hudIntent").textContent = g.intent || "DELIVERY_UPDATE";
  document.getElementById("hudLanguage").textContent = g.language || "Hinglish (HI+EN)";
  document.getElementById("langBadge").textContent = g.language || "Hinglish";
  document.getElementById("hudCoachTip").textContent = g.coach_tip || "";

  const phraseEl = document.getElementById("hudSuggestedPhrase");
  if (g.suggested_phrase) {
    phraseEl.textContent = `Say to shop owner: "${g.suggested_phrase}"`;
    phraseEl.classList.remove("hidden");
  } else {
    phraseEl.classList.add("hidden");
  }

  const s = (g.sentiment || "CALM").toUpperCase();
  const badge = document.getElementById("sentimentBadge");
  badge.textContent = `SENTIMENT: ${s}`;
  const map = {
    CALM: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    POSITIVE: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    RESOLVED: "bg-emerald-500/25 text-emerald-200 border-emerald-400/50",
    CONCERNED: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    FRUSTRATED: "bg-rose-500/20 text-rose-300 border-rose-500/45 animate-pulse",
  };
  badge.className = `text-[10px] font-bold px-2 py-0.5 rounded-full border ${map[s] || map.CALM}`;
}

function setSpeakingIndicator(text, tone) {
  const el = document.getElementById("speakingIndicator");
  const styles = {
    emerald: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
    amber: "bg-amber-500/20 text-amber-300 border border-amber-500/40",
    cyan: "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40",
    slate: "bg-slate-800 text-slate-400",
  };
  el.textContent = text;
  el.className = `text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${styles[tone] || styles.slate}`;
}

// --- BONUS ROI CALCULATOR ---
function updateRoiCalculator() {
  const vol = Number(document.getElementById("volumeSlider").value);
  const manual = vol * 30;
  const ai = Math.round(vol * 2.2);
  const savings = manual - ai;
  const roi = (manual / ai).toFixed(1);

  document.getElementById("volumeLabel").textContent = `${vol.toLocaleString("en-IN")} / month`;
  document.getElementById("roiManualCost").textContent = `₹${manual.toLocaleString("en-IN")}`;
  document.getElementById("roiAiCost").textContent = `₹${ai.toLocaleString("en-IN")}`;
  document.getElementById("roiSavings").textContent = `₹${savings.toLocaleString("en-IN")}`;
  document.getElementById("roiMultiple").textContent = `${roi}x ROI • 92.7% Cost Reduction`;
}

// --- RESET DEMO ---
async function resetDemo() {
  stopLiveCall();
  if (cameraActive) toggleLiveCamera();
  interruptionCount = 0;
  latencyHistory = [];
  renderLatencySparkline();
  highlightedPolicyIds.clear();
  document.getElementById("bargeInBadge").textContent = "0";
  document.getElementById("latencyBadge").textContent = "-- ms";
  document.getElementById("proofThumbPreview").classList.add("hidden");
  document.getElementById("visionStatusBadge").textContent = "Ready";
  updateFrontlineHud({
    intent: "AWAITING_SPEECH",
    language: "Hinglish / Tanglish",
    sentiment: "CALM",
    coach_tip: "Ready — speak naturally in Hinglish or Tanglish. Show damaged bags via camera for instant verification.",
    suggested_phrase: "",
  });
  document.getElementById("transcriptFeed").innerHTML = `<div class="text-slate-500 text-center mt-14 text-xs">Demo reset! Start a Live Call or click <strong class="text-slate-300">Step 1</strong> to run the 3-minute pitch flow.</div>`;
  document.getElementById("toolLog").innerHTML = `<div class="text-slate-500 font-sans text-xs">Waiting for spoken intent to trigger ERP actions...</div>`;
  refreshPoliciesHighlight();

  const res = await fetch("/api/reset", { method: "POST" }).then((r) => r.json());
  renderErpState(res.state);
}

// --- LIVE AUDIO WAVEFORM ANIMATION ---
function drawWaveformLoop() {
  const canvas = document.getElementById("waveCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let phase = 0;

  function frame() {
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const bars = 36;
    const barW = w / bars;
    phase += 0.12;
    const amp = callActive ? Math.max(0.12, currentEnergy) : 0.04;

    for (let i = 0; i < bars; i++) {
      const distCenter = 1 - Math.abs((i - bars / 2) / (bars / 2));
      const wave = Math.abs(Math.sin(phase + i * 0.45)) * distCenter;
      const barH = Math.max(4, wave * h * 0.9 * amp + (callActive ? 4 : 2));
      const x = i * barW + 2;
      const y = (h - barH) / 2;

      ctx.fillStyle = callActive ? (amp > 0.35 ? "#10b981" : "#38bdf8") : "#334155";
      ctx.beginPath();
      ctx.roundRect(x, y, barW - 4, barH, 3);
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function toFormData(obj) {
  const fd = new FormData();
  Object.entries(obj).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

window.addEventListener("DOMContentLoaded", initApp);
