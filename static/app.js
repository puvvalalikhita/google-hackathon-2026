// DeliverEx Live — 4D Glassmorphic Field Ops + Central Agent Live Screen

let healthInfo = { gemini_configured: false, live_model: "", whatsapp_configured: false, storage_mode: "sqlite", manager_auth_enforced: false };
let ownerToken = "";
let ownerSessionState = { authenticated: false, auth_enforced: false, actor: "Guest" };
let pendingAuthCallback = null;

try {
  ownerToken = localStorage.getItem("deliverex_owner_token") || "";
} catch {}

function getOwnerHeaders(extra = {}) {
  const h = { ...extra };
  if (ownerToken) h["Authorization"] = `Bearer ${ownerToken}`;
  return h;
}
let liveReady = false;
let wsWorkflowReady = false;
let lastWorkflowTtfa = 310;
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
let aiSpeakingUntil = 0;
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

// Dashboard Working State (Filters, Cached ERP, 4D Mode, Autopilot, Role Status)
let cachedErpState = null;
let cachedPolicies = [];
let activeLedgerFilter = "ALL";
let is4dEnabled = true;
let sfxEnabled = true;
let sfxCtx = null;
const chartHitRegions = {};
let autopilotTimers = [];
let autopilotRunning = false;
let toolCallCount = 0;
let currentAgentBadge = "STANDBY";
let currentAgentTask = "Waiting for driver speech, camera frame, or field trigger...";
let currentAgentLang = "Hinglish / Tanglish";

// WhatsApp Chat & voice note MediaRecorder state
let waRecorder = null;
let waChunks = [];
let waRecording = false;
let activeDriverTab = "live";
let waUnreadCount = 0;
let seenWaMsgIds = new Set();
let waInitialized = false;
let waSending = false;

// Theme Palettes (All Color Schemes + Royal Gold Default)
const THEME_PALETTES = {
  gold: { name: "Gold", primary: "#fbbf24", secondary: "#fde68a", tertiary: "#f59e0b", danger: "#fb7185", barTarget: "rgba(251, 191, 36, 0.28)", areaFillTop: "rgba(251, 191, 36, 0.45)" },
  emerald: { name: "Emerald", primary: "#10b981", secondary: "#38bdf8", tertiary: "#818cf8", danger: "#f43f5e", barTarget: "rgba(56, 189, 248, 0.28)", areaFillTop: "rgba(56, 189, 248, 0.42)" },
  sapphire: { name: "Sapphire", primary: "#60a5fa", secondary: "#a78bfa", tertiary: "#22d3ee", danger: "#fb7185", barTarget: "rgba(167, 139, 250, 0.28)", areaFillTop: "rgba(96, 165, 250, 0.44)" },
  ruby: { name: "Ruby", primary: "#fb7185", secondary: "#f472b6", tertiary: "#fb923c", danger: "#facc15", barTarget: "rgba(244, 114, 182, 0.28)", areaFillTop: "rgba(244, 63, 94, 0.44)" },
  platinum: { name: "Platinum", primary: "#e2e8f0", secondary: "#7dd3fc", tertiary: "#94a3b8", danger: "#fb7185", barTarget: "rgba(125, 211, 252, 0.28)", areaFillTop: "rgba(226, 232, 240, 0.4)" },
  sunset: { name: "Sunset", primary: "#fb923c", secondary: "#fbbf24", tertiary: "#fb7185", danger: "#f43f5e", barTarget: "rgba(251, 191, 36, 0.28)", areaFillTop: "rgba(249, 115, 22, 0.45)" },
};
let activeColorTheme = "gold";

function getThemePalette() {
  return THEME_PALETTES[activeColorTheme] || THEME_PALETTES.gold;
}

function setColorTheme(themeKey) {
  if (!THEME_PALETTES[themeKey]) themeKey = "gold";
  activeColorTheme = themeKey;
  document.documentElement.setAttribute("data-theme", themeKey);
  try { localStorage.setItem("deliverex_theme", themeKey); } catch {}

  const pal = getThemePalette();
  const lbl = document.getElementById("activeThemeLabel");
  if (lbl) lbl.textContent = pal.name;

  Object.keys(THEME_PALETTES).forEach((k) => {
    const sw = document.getElementById(`swatch-${k}`);
    if (sw) sw.classList.toggle("active", k === themeKey);
  });

  // Update wired flow connector colors to match active theme
  const wireColors = [pal.secondary, pal.primary, pal.tertiary];
  for (let i = 1; i <= 3; i++) {
    const col = wireColors[i - 1];
    [document.getElementById(`opsWire${i}`), document.getElementById(`boardWire${i}`)].forEach((line) => {
      if (!line) return;
      line.setAttribute("stroke", col);
      const poly = line.nextElementSibling;
      if (poly) poly.setAttribute("fill", col);
    });
  }

  if (cachedErpState) {
    renderHybridCharts(cachedErpState);
  } else {
    renderAgentLatencyGraph("opsAgentGraph");
    renderAgentLatencyGraph("boardAgentGraph");
  }
}

// --- INITIALIZATION ---
async function initApp() {
  try {
    const savedTheme = localStorage.getItem("deliverex_theme");
    setColorTheme(savedTheme && THEME_PALETTES[savedTheme] ? savedTheme : "gold");
  } catch {
    setColorTheme("gold");
  }
  init4DTiles();
  initChartTooltips();
  document.getElementById("activeStoreSelect")?.addEventListener("change", () => updateRouteRadarMap(cachedErpState));
  drawWaveformLoop();
  updateRoiCalculator();
  setAgentPipeline(0, "STANDBY", "Waiting for driver speech, camera frame, or field trigger...", "cyan");
  setVoiceLoopStage("standby", "Voice catcher armed — ready to catch speech, run agents & ask back.");

  try {
    const [hRes, sRes, glRes, authRes] = await Promise.all([
      fetch("/api/health"),
      fetch("/api/state"),
      fetch("/api/go-live-check"),
      fetch("/api/auth/session", { headers: getOwnerHeaders() }),
    ]);
    healthInfo = await hRes.json();
    const stateData = await sRes.json();
    const goLiveData = glRes.ok ? await glRes.json() : null;
    if (authRes.ok) {
      ownerSessionState = await authRes.json();
      updateOwnerAuthUi();
    }
    const storagePill = document.getElementById("storageModePill");
    if (storagePill && healthInfo.storage_mode) {
      storagePill.textContent = healthInfo.storage_mode.toUpperCase();
    }

    const badge = document.getElementById("modeBadge");
    if (healthInfo.gemini_configured) {
      const authLbl = healthInfo.auth_mode === "vertex_ai" ? "Vertex AI" : "AI Studio";
      badge.textContent = `LIVE GEMINI (${authLbl}) • ${healthInfo.live_model}`;
      badge.className = "text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-200 border border-emerald-400/40 backdrop-blur-md";
    } else {
      badge.textContent = "BACKEND WORKFLOW ENGINE (Add GEMINI_API_KEY for Live Voice)";
      badge.className = "text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-400/40 backdrop-blur-md";
    }

    renderPolicies(stateData.policies || []);
    renderErpState(stateData.state);
    if (goLiveData) renderGoLiveReadiness(goLiveData);
  } catch (err) {
    console.error("Init error:", err);
  }
}

// --- 4D SPATIAL TILE PHYSICS ENGINE (3D Tilt + Dynamic Specular Light + Time Depth) ---
function init4DTiles() {
  const attachTile = (el) => {
    if (el.dataset.bound4d === "1") return;
    el.dataset.bound4d = "1";
    const isLarge = el.classList.contains("glass-4d");
    const maxTilt = isLarge ? 3.2 : 5.5;

    el.addEventListener("pointermove", (e) => {
      if (!is4dEnabled) return;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const px = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const py = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
      const rx = ((0.5 - py) * 2 * maxTilt).toFixed(2);
      const ry = ((px - 0.5) * 2 * maxTilt).toFixed(2);

      el.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
      el.style.setProperty("--rx", `${rx}deg`);
      el.style.setProperty("--ry", `${ry}deg`);
      el.style.setProperty("--tz", isLarge ? "4px" : "6px");
      el.style.setProperty("--sheen-opacity", "1");
    });

    el.addEventListener("pointerleave", () => {
      el.style.setProperty("--rx", "0deg");
      el.style.setProperty("--ry", "0deg");
      el.style.setProperty("--tz", "0px");
      el.style.setProperty("--sheen-opacity", "0");
    });
  };

  document.querySelectorAll(".glass-4d, .subtile-4d").forEach(attachTile);

  // Observe dynamically rendered sub-tiles (policies, approvals, insights, stock)
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.matches?.(".glass-4d, .subtile-4d")) attachTile(node);
        node.querySelectorAll?.(".glass-4d, .subtile-4d").forEach(attachTile);
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function toggle4dMode() {
  is4dEnabled = !is4dEnabled;
  const btn = document.getElementById("toggle4dBtn");
  document.body.classList.toggle("flat-4d", !is4dEnabled);
  if (btn) {
    btn.textContent = is4dEnabled ? "4D: ON" : "4D: OFF";
    btn.className = is4dEnabled
      ? "btn-tactile px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-white/10 text-slate-200 border border-white/15"
      : "btn-tactile px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-900/70 text-slate-400 border border-white/10";
  }
}

// --- CENTRAL AGENT LIVE SCREEN CONTROLLER ---
function setAgentPipeline(activeStep, badgeText, taskText, tone = "cyan") {
  const badge = document.getElementById("agentStageBadge");
  const taskEl = document.getElementById("agentCurrentTask");
  const toneClasses = {
    cyan: "bg-cyan-500/20 text-cyan-200 border-cyan-400/45 shadow-[0_0_14px_rgba(34,211,238,0.25)]",
    emerald: "bg-emerald-500/20 text-emerald-200 border-emerald-400/45 shadow-[0_0_14px_rgba(16,185,129,0.25)]",
    amber: "bg-amber-500/20 text-amber-200 border-amber-400/50 shadow-[0_0_14px_rgba(245,158,11,0.3)]",
    rose: "bg-rose-500/20 text-rose-200 border-rose-400/50 shadow-[0_0_14px_rgba(244,63,94,0.28)]",
  };

  if (badge && badgeText) {
    currentAgentBadge = badgeText;
    badge.textContent = badgeText;
    badge.className = `mono text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${toneClasses[tone] || toneClasses.cyan}`;
  }
  if (taskEl && taskText) {
    currentAgentTask = taskText;
    taskEl.textContent = taskText;
  }

  for (let i = 1; i <= 5; i++) {
    const node = document.getElementById(`pipeStage${i}`);
    if (!node) continue;
    if (activeStep === 0) {
      node.className = "subtile-4d rounded-xl py-1.5 px-1 text-center border-white/10 opacity-75";
    } else if (i < activeStep) {
      node.className = "subtile-4d rounded-xl py-1.5 px-1 text-center border-emerald-400/45 bg-emerald-500/15 shadow-[0_0_12px_rgba(16,185,129,0.2)]";
    } else if (i === activeStep) {
      const activeBorder =
        tone === "amber"
          ? "border-amber-400/70 bg-amber-500/25 shadow-[0_0_16px_rgba(245,158,11,0.35)] scale-[1.04]"
          : tone === "emerald"
          ? "border-emerald-400/70 bg-emerald-500/25 shadow-[0_0_16px_rgba(16,185,129,0.35)] scale-[1.04]"
          : "border-cyan-400/70 bg-cyan-500/25 shadow-[0_0_16px_rgba(34,211,238,0.35)] scale-[1.04]";
      node.className = `subtile-4d rounded-xl py-1.5 px-1 text-center transition-all ${activeBorder}`;
    } else {
      node.className = "subtile-4d rounded-xl py-1.5 px-1 text-center border-white/10 opacity-55";
    }
  }
  updateRoleStatusDashboard();
  updateRouteRadarMap(cachedErpState);
}

function pushAgentAction(label, detail, tone = "cyan") {
  const feed = document.getElementById("agentActionFeed");
  if (!feed) return;
  if (feed.children.length === 1 && feed.firstElementChild?.textContent?.includes("Gemini Live Brain armed")) {
    feed.innerHTML = "";
  }
  const dotColor =
    tone === "emerald"
      ? "bg-emerald-400 shadow-[0_0_8px_#34d399]"
      : tone === "amber"
      ? "bg-amber-400 shadow-[0_0_8px_#fbbf24]"
      : tone === "rose"
      ? "bg-rose-400 shadow-[0_0_8px_#fb7185]"
      : "bg-cyan-400 shadow-[0_0_8px_#22d3ee]";

  const row = document.createElement("div");
  row.className = "flex items-start gap-2 text-[11px] py-0.5";
  const ts = new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  row.innerHTML = `
    <span class="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dotColor}"></span>
    <div class="flex-1 min-w-0">
      <span class="font-bold text-white">${escapeHtml(label)}</span>
      <span class="text-slate-300 ml-1">${escapeHtml(detail)}</span>
    </div>
    <span class="mono text-[9px] text-slate-500 shrink-0 mt-0.5">${ts}</span>
  `;
  feed.prepend(row);
  while (feed.children.length > 18) {
    feed.removeChild(feed.lastElementChild);
  }
}

// --- AUTOPILOT SHOWCASE (Watch the Central Agent Execute End-to-End) ---
function clearAutopilotTimers() {
  autopilotTimers.forEach((t) => clearTimeout(t));
  autopilotTimers = [];
  autopilotRunning = false;
  const btn = document.getElementById("autoDemoBtn");
  if (btn) btn.textContent = "▶ Auto-Run Agent";
}

async function runAutopilotShowcase() {
  if (autopilotRunning) {
    clearAutopilotTimers();
    return;
  }
  await resetDemo();
  autopilotRunning = true;
  const btn = document.getElementById("autoDemoBtn");
  if (btn) btn.textContent = "⏹ Stop Auto-Run";

  pushAgentAction("AUTOPILOT", "Starting live end-to-end agent execution sequence...", "cyan");
  await runGuidedStep(1);

  autopilotTimers.push(
    setTimeout(async () => {
      if (!autopilotRunning) return;
      await runGuidedStep(2);
    }, 2600)
  );

  autopilotTimers.push(
    setTimeout(async () => {
      if (!autopilotRunning) return;
      await sendSampleDamagePhoto();
    }, 5600)
  );

  autopilotTimers.push(
    setTimeout(async () => {
      if (!autopilotRunning) return;
      const pending = (cachedErpState?.approvals || []).find((a) => a.status === "PENDING");
      if (pending) {
        pushAgentAction("HITL LOOP", `Manager Priya approving ${pending.customer_name} (${pending.approval_id})...`, "emerald");
        await decideApproval(pending.approval_id, "APPROVED");
      }
      clearAutopilotTimers();
    }, 8800)
  );
}

// --- VIEW & TAB SWITCHING ---
function switchMainView(view) {
  const ops = document.getElementById("opsView");
  const roles = document.getElementById("rolesView");
  const ins = document.getElementById("insightsView");
  const bOps = document.getElementById("viewOpsBtn");
  const bRoles = document.getElementById("viewRolesBtn");
  const bIns = document.getElementById("viewInsightsBtn");

  const activeCls = "btn-tactile w-full text-left flex items-center gap-2.5 min-h-[44px] px-3.5 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-amber-300 to-amber-500 text-slate-950";
  const idleCls = "w-full text-left flex items-center gap-2.5 min-h-[44px] px-3.5 py-2.5 rounded-xl text-xs font-semibold text-slate-200 hover:bg-white/10 transition";

  ops?.classList.toggle("hidden", view !== "ops");
  roles?.classList.toggle("hidden", view !== "roles");
  ins?.classList.toggle("hidden", view !== "insights");

  if (bOps) bOps.className = view === "ops" ? activeCls : idleCls;
  if (bRoles) bRoles.className = view === "roles" ? activeCls : idleCls;
  if (bIns) bIns.className = view === "insights" ? activeCls : idleCls;

  if (view === "roles") updateRoleStatusDashboard();
}

function switchDriverTab(tab) {
  activeDriverTab = tab;
  const livePanel = document.getElementById("driverLivePanel");
  const waPanel = document.getElementById("driverWhatsAppPanel");
  const tLive = document.getElementById("tabLiveCall");
  const tWa = document.getElementById("tabWhatsApp");
  const badge = document.getElementById("waUnreadBadge");

  if (tab === "live") {
    livePanel.classList.remove("hidden");
    waPanel.classList.add("hidden");
    tLive.className = "btn-tactile px-2.5 py-1 rounded-lg font-semibold bg-emerald-500/25 text-emerald-200 border border-emerald-400/40";
    tWa.className = "px-2.5 py-1 rounded-lg font-semibold text-slate-400 hover:text-white transition flex items-center gap-1";
  } else {
    livePanel.classList.add("hidden");
    waPanel.classList.remove("hidden");
    tWa.className = "btn-tactile px-2.5 py-1 rounded-lg font-semibold bg-emerald-500/25 text-emerald-200 border border-emerald-400/40 flex items-center gap-1";
    tLive.className = "px-2.5 py-1 rounded-lg font-semibold text-slate-400 hover:text-white transition";
    waUnreadCount = 0;
    if (badge) {
      badge.textContent = "0";
      badge.classList.add("hidden");
    }
    const feed = document.getElementById("waChatFeed");
    if (feed) feed.scrollTop = feed.scrollHeight;
    setTimeout(() => document.getElementById("waChatInput")?.focus(), 50);
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

  if (!playbackCtx) {
    playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
  }
  if (playbackCtx.state === "suspended") {
    try { await playbackCtx.resume(); } catch {}
  }
  nextPlayTime = playbackCtx.currentTime;

  const btn = document.getElementById("callToggleBtn");
  btn.textContent = "🔴 End Call";
  btn.className = "btn-tactile flex-1 whitespace-nowrap min-h-[44px] py-2.5 px-3 rounded-xl font-extrabold text-sm bg-gradient-to-b from-rose-400 to-rose-600 text-white shadow-lg shadow-rose-500/25";
  document.getElementById("endTurnBtn")?.classList.remove("hidden");
  document.getElementById("avatarRing").classList.add("pulse-ring");
  document.getElementById("callStatusTitle").textContent = healthInfo.gemini_configured
    ? "Connecting to Gemini Live API..."
    : "Interactive Demo Call Active";
  document.getElementById("callStatusSub").textContent = healthInfo.gemini_configured
    ? "Speak Hinglish / Hindi / Tanglish naturally — interrupt anytime!"
    : "Click Step 1 → Step 2 (Interrupt!) below to preview full live workflow";

  setAgentPipeline(1, "LISTENING", "Call active — streaming audio & monitoring Hinglish/Tanglish intent", "cyan");
  setVoiceLoopStage("catching", "Voice catcher live — listening for Hinglish / Tanglish speech...");
  pushAgentAction("CALL STARTED", "Audio bridge opened on Route-4 handset.", "cyan");

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/live-call`);

  ws.onmessage = (evt) => handleServerEvent(JSON.parse(evt.data));
  ws.onerror = () => {
    if (callActive && !liveReady) {
      document.getElementById("callStatusTitle").textContent = "Backend Workflow Call Active";
      setSpeakingIndicator("Workflow Ready", "cyan");
    }
  };
  ws.onclose = () => {
    if (callActive && healthInfo.gemini_configured) {
      setSpeakingIndicator("Disconnected", "slate");
    }
  };

  setTimeout(() => {
    if (callActive && !liveReady && !wsWorkflowReady) {
      document.getElementById("callStatusTitle").textContent = "Interactive Call Active • Triggers & Text Ready";
      setSpeakingIndicator("Ready (Triggers/Text)", "cyan");
    }
  }, 5000);

  if (healthInfo.gemini_configured) {
    try {
      await startMicStreaming();
    } catch (err) {
      addSystemBanner(`Mic permission unavailable (${err.message}). You can still use Live Field Triggers / text input below!`);
    }
  } else {
    setSpeakingIndicator("Demo Ready", "amber");
    addSystemBanner("Interactive Demo Mode active — click Step 1, Step 2 (Interrupt!), or ▶ Auto-Run Agent!");
  }
}

function stopLiveCall() {
  callActive = false;
  liveReady = false;
  wsWorkflowReady = false;
  clearInterval(callTimerInterval);
  document.getElementById("callTimer").textContent = "00:00";

  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }
  stopMicStreaming();
  stopBrowserSpeechLoop();
  flushPlaybackAudio();
  if (window.speechSynthesis) window.speechSynthesis.cancel();

  const btn = document.getElementById("callToggleBtn");
  btn.textContent = "📞 Start Live Call";
  btn.className = "btn-tactile flex-1 whitespace-nowrap min-h-[44px] py-2.5 px-3 rounded-xl font-extrabold text-sm bg-gradient-to-b from-emerald-400 to-emerald-500 text-slate-950 shadow-lg shadow-emerald-500/25";
  document.getElementById("endTurnBtn")?.classList.add("hidden");
  document.getElementById("avatarRing").classList.remove("pulse-ring");
  document.getElementById("callStatusTitle").textContent = "Tap to Start Real-Time Voice Call";
  setSpeakingIndicator("Idle", "slate");
  setAgentPipeline(0, "STANDBY", "Call ended — ready for next field delivery check-in.", "cyan");
  setVoiceLoopStage("standby", "Voice catcher armed — ready to catch speech, run agents & ask back.");
}

function forceEndTurn() {
  if (ws && ws.readyState === WebSocket.OPEN && liveReady) {
    ws.send(JSON.stringify({ type: "force_end_turn" }));
    setSpeakingIndicator("Processing Turn...", "cyan");
    setAgentPipeline(2, "ANALYZING", "Processing driver speech turn...", "cyan");
  } else if (ws && ws.readyState === WebSocket.OPEN && wsWorkflowReady) {
    if (vadChunks.length > 0) {
      flushVadAudioTurn(true);
    } else {
      addSystemBanner("Speak into your microphone first, then pause or tap ✓ Reply Now.");
    }
  }
}

function updateCallTimer() {
  const sec = Math.floor((Date.now() - callStartTime) / 1000);
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  document.getElementById("callTimer").textContent = `${mm}:${ss}`;
}

// 16kHz PCM VAD state for Workflow Mode voice turns
let vadPreRoll = [];
let vadChunks = [];
let vadRecording = false;
let vadSilenceMs = 0;
let vadSpeechFrames = 0;
let bargeInSpeechFrames = 0;
let ttsCooldownUntil = 0;
let ttsStartedAt = 0;
let consecutiveUnclearAudio = 0;

function encodePcm16ToWavBase64(chunks, sampleRate = 16000) {
  let totalSamples = 0;
  chunks.forEach((c) => { totalSamples += c.length; });
  const buffer = new ArrayBuffer(44 + totalSamples * 2);
  const view = new DataView(buffer);
  const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + totalSamples * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, totalSamples * 2, true);

  let offset = 44;
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++) {
      view.setInt16(offset, chunk[i], true);
      offset += 2;
    }
  }

  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function flushVadAudioTurn(manualForce = false) {
  if (!vadChunks.length) return;
  const captured = vadChunks;
  vadChunks = [];
  vadRecording = false;
  vadSilenceMs = 0;
  vadSpeechFrames = 0;

  if (!ws || ws.readyState !== WebSocket.OPEN || !wsWorkflowReady) return;
  // Require at least ~600ms of audio (6 chunks) to avoid sending short background pops/beeps
  if (!manualForce && captured.length < 6) {
    setSpeakingIndicator("Voice & Workflow Ready", "emerald");
    if (callActive) setVoiceLoopStage("catching", "Listening — speak Hinglish/English or click Triggers 1–4!");
    return;
  }

  // Verify captured utterance has sustained human speech energy (not ambient hiss or a short beep)
  let peakAbs = 0;
  let sumSq = 0;
  let sampleCount = 0;
  for (const chunk of captured) {
    for (let i = 0; i < chunk.length; i++) {
      const s = chunk[i];
      const a = Math.abs(s);
      if (a > peakAbs) peakAbs = a;
      const f = s / 32768.0;
      sumSq += f * f;
      sampleCount += 1;
    }
  }
  const peakNorm = peakAbs / 32768.0;
  const meanRms = sampleCount > 0 ? Math.sqrt(sumSq / sampleCount) : 0;
  if (!manualForce && (peakNorm < 0.18 || meanRms < 0.045)) {
    setSpeakingIndicator("Voice & Workflow Ready", "emerald");
    if (callActive) setVoiceLoopStage("catching", "Listening — speak Hinglish/English or click Triggers 1–4!");
    return;
  }

  const wavB64 = encodePcm16ToWavBase64(captured, 16000);
  setSpeakingIndicator("Thinking + Tool Call", "cyan");
  setVoiceLoopStage("working", "⚙️ Agents transcribing your voice & updating Tally/SAP...");
  setAgentPipeline(2, "VOICE CAPTURED", "Transcribing spoken Hinglish/Tanglish via Gemini...", "cyan");
  ws.send(JSON.stringify({
    type: "audio_turn",
    data: wavB64,
    mime_type: "audio/wav",
    driver_name: "Raju Kumar",
    active_store: getActiveStoreName(),
    preferred_language: serverLangPref(),
  }));
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
  if (captureCtx.state === "suspended") {
    try { await captureCtx.resume(); } catch {}
  }
  await captureCtx.audioWorklet.addModule("/static/pcm-processor.js");

  const src = captureCtx.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(captureCtx, "pcm16-processor");
  vadPreRoll = [];
  vadChunks = [];
  vadRecording = false;
  vadSilenceMs = 0;
  vadSpeechFrames = 0;

  workletNode.port.onmessage = (event) => {
    const { pcm, rms } = event.data;
    currentEnergy = Math.max(0.05, Math.min(1, rms * 18));
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // Path A: Native Gemini Live Audio streaming
    if (liveReady) {
      const aiCurrentlySpeaking =
        activeAudioSources.length > 0 || (playbackCtx && playbackCtx.currentTime < aiSpeakingUntil);
      if (aiCurrentlySpeaking && rms < 0.085) return;

      const bytes = new Uint8Array(pcm);
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
      ws.send(JSON.stringify({
        type: "audio_chunk",
        data: btoa(binary),
        speaking: rms > 0.02,
      }));
      return;
    }

    // Path B: Workflow Mode 16kHz PCM acoustic meter, barge-in, & WAV fallback if SpeechRecognition unavailable
    if (wsWorkflowReady) {
      const int16 = new Int16Array(pcm);
      const aiSpeaking = isAiSpeakingNow();

      // Interrupt AI voice on sustained close-mic speech (>= 300ms), never initial echo or single tone pops
      if (aiSpeaking && Date.now() >= ttsStartedAt + 900 && rms >= 0.2) {
        bargeInSpeechFrames += 1;
        if (bargeInSpeechFrames >= 3) {
          bargeInSpeechFrames = 0;
          cancelAllAiVoice();
          ttsCooldownUntil = Date.now() + 280;
          interruptionCount += 1;
          document.getElementById("bargeInBadge").textContent = String(interruptionCount);
          addInterruptionBadge();
          setVoiceLoopStage("bargein", "⚡ Interrupted mid-sentence — catching your voice!");
          playSpatialChime("bargein");
        }
      } else {
        bargeInSpeechFrames = 0;
      }

      // When Web SpeechRecognition is available & active, let it handle clean Hinglish/English speech-to-text
      // instead of sending raw WAV chunks continuously in the background.
      const srSupported = Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
      if (srSupported && !speechRecFailed) {
        return;
      }

      if (aiSpeaking || Date.now() < ttsCooldownUntil) {
        vadSpeechFrames = 0;
        return; // Don't record AI's own speaker output or echo tail
      }

      if (!vadRecording) {
        vadPreRoll.push(int16);
        if (vadPreRoll.length > 3) vadPreRoll.shift();

        if (rms >= 0.085) {
          vadSpeechFrames += 1;
        } else {
          vadSpeechFrames = 0;
        }

        if (vadSpeechFrames >= 3) {
          vadRecording = true;
          vadSilenceMs = 0;
          vadChunks = [...vadPreRoll];
          setVoiceLoopStage("catching", "🎙️ Catching your voice — speak naturally...");
          setSpeakingIndicator("Catching Voice", "cyan");
        }
      } else {
        vadChunks.push(int16);
        if (rms < 0.045) {
          vadSilenceMs += 100;
        } else {
          vadSilenceMs = 0;
        }
        if (vadSilenceMs >= 900 || vadChunks.length >= 90) {
          flushVadAudioTurn(false);
        }
      }
    }
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

// --- BROWSER SPEECH RECOGNITION (Live Conversational Hinglish/English Mic -> Workflow Engine) ---
let speechRec = null;
let speechRecActive = false;
let speechRecFailed = false;
let lastSpokenAiText = "";

// --- ADAPTIVE CONVERSATION LANGUAGE ---
const LANG_META = {
  en: { label: "English", sr: "en-IN", tts: "English", short: "English" },
  hinglish: { label: "Hinglish (HI+EN)", sr: "en-IN", tts: "Hinglish (HI+EN)", short: "Hinglish" },
  hi: { label: "Hindi (HI)", sr: "hi-IN", tts: "Hindi (HI)", short: "हिंदी" },
  tanglish: { label: "Tanglish (TA+EN)", sr: "en-IN", tts: "Tanglish (TA+EN)", short: "Tanglish" },
  ta: { label: "Tamil (TA)", sr: "ta-IN", tts: "Tamil (TA)", short: "தமிழ்" },
  tenglish: { label: "Tenglish (TE+EN)", sr: "en-IN", tts: "Tenglish (TE+EN)", short: "Tenglish" },
  te: { label: "Telugu (TE)", sr: "te-IN", tts: "Telugu (TE)", short: "తెలుగు" },
};
const LANG_GREETINGS = {
  en: "Hi Raju! DeliverEx Live here — which shop did you just deliver to?",
  hinglish: "Namaste Raju bhai, DeliverEx Live bol raha hoon — bataiye kis shop pe delivery hui?",
  hi: "नमस्ते राजू भाई! DeliverEx Live तैयार है — बताइए किस दुकान पर डिलीवरी हुई?",
  tanglish: "Vanakkam anna! DeliverEx Live ready — endha kadaiyila delivery aachu nu sollunga.",
  ta: "வணக்கம் அண்ணா! DeliverEx Live தயார் — எந்த கடையில டெலிவரி ஆச்சுன்னு சொல்லுங்க.",
  tenglish: "Namaskaram anna! DeliverEx Live ready — e shop lo delivery ayyindo cheppandi.",
  te: "నమస్కారం అన్నా! DeliverEx Live సిద్ధంగా ఉంది — ఏ షాప్‌లో డెలివరీ అయిందో చెప్పండి.",
};
let sessionLangCode = "hinglish";

function getPreferredLang() {
  const v = document.getElementById("voiceLangSelect")?.value || "auto";
  return v === "auto" ? null : v;
}

function serverLangPref() {
  return document.getElementById("voiceLangSelect")?.value || "auto";
}

function effectiveLangCode() {
  return getPreferredLang() || sessionLangCode || "hinglish";
}

function renderLangBadge() {
  const badge = document.getElementById("voiceLangBadge");
  if (!badge) return;
  const code = effectiveLangCode();
  const auto = !getPreferredLang();
  badge.textContent = `${auto ? "✨ " : ""}${LANG_META[code]?.short || code}`;
  badge.title = auto ? "Auto-detected from the driver's speech" : "Fixed by selection";
}

function restartSpeechRecIfLocaleChanged() {
  if (!speechRec || !callActive) return;
  const wanted = LANG_META[effectiveLangCode()]?.sr || "en-IN";
  if (speechRec.lang !== wanted) {
    try { speechRec.onend = null; speechRec.stop(); } catch {}
    speechRec = null;
    speechRecActive = false;
    setTimeout(startBrowserSpeechLoop, 200);
  }
}

function applyServerLanguage(code, intent) {
  if (!code || !LANG_META[code]) return;
  const changed = code !== sessionLangCode;
  sessionLangCode = code;
  const sel = document.getElementById("voiceLangSelect");
  // "Speak Telugu / Hindi mein bolo" locks the conversation to that language until changed again
  if (sel && intent === "LANG_SWITCH") {
    sel.value = code;
    showGlassToast("🌐 Language Switched", `Now speaking ${LANG_META[code].label} — set Auto-Adapt to unlock`, "cyan");
  } else if (sel && sel.value !== "auto" && sel.value !== code) {
    sel.value = code;
  }
  renderLangBadge();
  if (changed) {
    pushAgentAction("LANGUAGE ADAPTED", `Now conversing in ${LANG_META[code].label}`, "cyan");
    restartSpeechRecIfLocaleChanged();
  }
}

function onVoiceLangChange() {
  const pref = getPreferredLang();
  if (pref) sessionLangCode = pref;
  renderLangBadge();
  restartSpeechRecIfLocaleChanged();
  if (liveReady && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "set_language",
      language: pref ? LANG_META[pref].label : "auto",
    }));
  }
  showGlassToast(
    "🌐 Conversation Language",
    pref ? `Switched live voice to ${LANG_META[pref].label}` : "Auto-Adapt on — AI will match your spoken language",
    "cyan"
  );
}

function isLikelyAiEcho(heard) {
  const h = (heard || "").toLowerCase().trim();
  if (h.length < 4 || !lastSpokenAiText) return false;
  const ai = lastSpokenAiText.toLowerCase();
  if (ai.includes(h)) return true;
  const words = h.split(/[\s,.!?—-]+/).filter((w) => w.length > 2);
  if (words.length < 2) return false;
  const aiWords = new Set(ai.split(/[\s,.!?—-]+/));
  const overlap = words.filter((w) => aiWords.has(w)).length / words.length;
  // Echo only matters while/just after the AI spoke
  return overlap >= 0.6 && Date.now() < ttsCooldownUntil + 4000;
}

function isAiSpeakingNow() {
  return Boolean(
    activeAudioSources.length > 0 ||
    (window.speechSynthesis && window.speechSynthesis.speaking)
  );
}

function cancelAllAiVoice() {
  if (window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch {}
  }
  flushPlaybackAudio();
}

function startBrowserSpeechLoop() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR || !callActive || liveReady || speechRecActive || speechRecFailed) return;

  try {
    speechRec = new SR();
    speechRec.lang = LANG_META[effectiveLangCode()]?.sr || "en-IN";
    speechRec.continuous = true;
    speechRec.interimResults = true;
    speechRecActive = true;

    speechRec.onresult = (event) => {
      if (!callActive || !ws || ws.readyState !== WebSocket.OPEN) return;
      let interim = "";
      let finalTxt = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) finalTxt += res[0].transcript;
        else interim += res[0].transcript;
      }

      const aiSpeaking = isAiSpeakingNow();
      const candidateText = (finalTxt || interim).trim();
      const looksLikeAiEcho = isLikelyAiEcho(candidateText);

      // Ignore self-echo from speakers right after AI starts talking
      if ((aiSpeaking || Date.now() < ttsCooldownUntil) && (looksLikeAiEcho || Date.now() < ttsStartedAt + 950)) {
        return;
      }

      // Natural vocal barge-in if user speaks clearly while AI voice is playing
      if (aiSpeaking && (interim.trim().length > 6 || finalTxt.trim().length > 2) && !looksLikeAiEcho) {
        cancelAllAiVoice();
        ttsCooldownUntil = Date.now() + 250;
        interruptionCount += 1;
        document.getElementById("bargeInBadge").textContent = String(interruptionCount);
        addInterruptionBadge();
        setVoiceLoopStage("bargein", "⚡ Interrupted mid-sentence — catching your voice!");
        playSpatialChime("bargein");
      }

      if (interim.trim() && !isAiSpeakingNow()) {
        setVoiceLoopStage("catching", `🎙️ Hearing: "${interim.trim().slice(0, 48)}..."`);
      }

      const clean = finalTxt.trim();
      if (clean && !looksLikeAiEcho) {
        const conf = event.results[event.results.length - 1]?.[0]?.confidence;
        addSystemBanner(`🎙️ Heard (${LANG_META[effectiveLangCode()]?.sr || "en-IN"}${conf ? `, ${Math.round(conf * 100)}%` : ""}): "${clean}"`);
      }
      if (clean && !isAiSpeakingNow() && !looksLikeAiEcho) {
        setVoiceLoopStage("working", `⚙️ Agents processing: "${clean.slice(0, 44)}..."`);
        setSpeakingIndicator("Thinking + Tool Call", "cyan");
        ws.send(JSON.stringify({
          type: "text_turn",
          text: clean,
          driver_name: "Raju Kumar",
          active_store: getActiveStoreName(),
          preferred_language: serverLangPref(),
        }));
      }
    };

    speechRec.onerror = (ev) => {
      if (ev && ["not-allowed", "service-not-allowed", "audio-capture"].includes(ev.error)) {
        speechRecFailed = true;
      }
    };
    speechRec.onend = () => {
      speechRecActive = false;
      if (callActive && wsWorkflowReady && !liveReady && !speechRecFailed) {
        setTimeout(startBrowserSpeechLoop, 280);
      }
    };
    speechRec.start();
  } catch {
    speechRecActive = false;
    speechRecFailed = true;
  }
}

function stopBrowserSpeechLoop() {
  speechRecActive = false;
  speechRecFailed = false;
  if (speechRec) {
    try { speechRec.onend = null; speechRec.stop(); } catch {}
    speechRec = null;
  }
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
  aiSpeakingUntil = nextPlayTime + 0.4;

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
  aiSpeakingUntil = 0;
  if (playbackCtx) nextPlayTime = playbackCtx.currentTime;
}

// --- SERVER WEBSOCKET EVENT HANDLER ---
function handleServerEvent(msg) {
  switch (msg.type) {
    case "status":
      liveReady = Boolean(msg.connected);
      wsWorkflowReady = Boolean(msg.workflow_ready);
      document.getElementById("callStatusTitle").textContent = msg.connected
        ? "Live Call Active • Listening"
        : msg.workflow_ready
        ? "Backend Workflow Live • Ready"
        : msg.message;
      if (msg.connected) {
        setSpeakingIndicator("Listening (Live)", "cyan");
        setAgentPipeline(1, "LIVE LISTENING", `Connected to ${msg.model} — awaiting driver voice/vision`, "cyan");
        addSystemBanner(`Connected to ${msg.model}. Start speaking Hinglish/English or use the field triggers.`);
      } else if (msg.workflow_ready) {
        setSpeakingIndicator("Voice & Workflow Ready", "emerald");
        setAgentPipeline(1, "VOICE + WORKFLOW", msg.message, "cyan");
        addSystemBanner(msg.message);
        if (callActive) {
          startBrowserSpeechLoop();
          const greetCode = effectiveLangCode();
          const greet = LANG_GREETINGS[greetCode] || LANG_GREETINGS.hinglish;
          renderLangBadge();
          fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: greet, language: LANG_META[greetCode]?.tts || "Hinglish (HI+EN)" }),
          })
            .then((r) => r.json())
            .then((d) => {
              if (callActive) speakDemoVoice(greet, 210, d?.audio_b64 || null);
            })
            .catch(() => {
              if (callActive) speakDemoVoice(greet, 240, null);
            });
        }
      }
      break;

    case "audio_out":
      playPcm24kBase64(msg.data);
      setVoiceLoopStage("asking", "Gemini AI speaking / asking back — interrupt anytime!");
      break;

    case "latency":
      lastWorkflowTtfa = msg.ttfa_ms || 310;
      updateLatencyBadge(msg.ttfa_ms);
      break;

    case "workflow_reply":
      if (msg.lang_code) applyServerLanguage(msg.lang_code, msg.intent);
      if (msg.intent === "UNCLEAR_AUDIO") {
        consecutiveUnclearAudio += 1;
        setSpeakingIndicator("Listening (Ready)", "cyan");
        setAgentPipeline(1, "LISTENING", "Audio unclear — speak clearly or click Triggers 1–4.", "cyan");
        setVoiceLoopStage("catching", "Listening — speak clearly or click Triggers 1–4!");
        if (consecutiveUnclearAudio === 1 && msg.text) {
          addSystemBanner(msg.text);
        }
        break;
      }
      consecutiveUnclearAudio = 0;
      if (msg.guidance) updateFrontlineHud(msg.guidance);
      if (msg.intent === "ESCALATE") {
        setAgentPipeline(4, "WARM HANDOFF", "Escalated to Area Manager Priya Sharma (SOP-6.0).", "rose");
      } else if (msg.result?.needs_manager_approval) {
        setAgentPipeline(4, "HITL DISPATCHED", `Exception routed to Priya Ma'am (${msg.result?.approval?.policy_ref || "SOP"})`, "amber");
      } else if (msg.intent === "RECORD_DELIVERY" && msg.result?.success) {
        setAgentPipeline(5, "AUTO-SETTLED", `${msg.result.customer_name || "Store"} synced to Tally/SAP & WhatsApp receipt sent!`, "emerald");
      } else if (msg.intent === "VISUAL_DAMAGE_VERIFIED") {
        setAgentPipeline(4, "VISION VERIFIED", "Torn bag proof attached to Priya Sharma's 1-Tap Approval Card.", "amber");
      } else {
        setAgentPipeline(4, "WORKFLOW DONE", `Processed ${msg.intent || "TURN"} via backend workflow`, "emerald");
      }
      if (msg.text) {
        speakDemoVoice(msg.text, lastWorkflowTtfa || 310, msg.audio_b64 || null);
      }
      break;

    case "interrupted":
      flushPlaybackAudio();
      interruptionCount = msg.count || (interruptionCount + 1);
      document.getElementById("bargeInBadge").textContent = String(interruptionCount);
      setSpeakingIndicator("⚡ Interrupted (Barge-In)", "amber");
      setAgentPipeline(2, "BARGE-IN", "Driver interrupted mid-sentence — flushing audio & re-evaluating intent!", "amber");
      setVoiceLoopStage("bargein", "⚡ Interrupted mid-sentence — catching your updated voice!");
      pushAgentAction("BARGE-IN DETECTED", "Audio buffer flushed immediately; adapting to driver correction.", "amber");
      addInterruptionBadge();
      currentRoleBubble = null;
      currentRole = null;
      break;

    case "transcript":
      appendTranscript(msg.role, msg.text, msg.final);
      if (msg.role === "user") {
        setAgentPipeline(2, "UNDERSTANDING", "Parsing Hinglish/Tanglish speech & extracting entities...", "cyan");
        setVoiceLoopStage("catching", `Caught voice: "${(msg.text || "").slice(0, 44)}..."`);
      } else if (msg.role === "assistant") {
        setVoiceLoopStage("asking", `Asking / replying: "${(msg.text || "").slice(0, 44)}..."`);
      }
      break;

    case "turn_complete":
      currentRoleBubble = null;
      currentRole = null;
      currentEnergy = 0.03;
      setSpeakingIndicator("Listening", "cyan");
      setAgentPipeline(1, "LISTENING", "Turn complete — listening for next driver update.", "cyan");
      setVoiceLoopStage("catching", "Turn complete — listening again for your next reply...");
      break;

    case "tool_call_start":
      logToolCall(msg.name, msg.args, "RUNNING", null);
      setVoiceLoopStage("working", `Agents working: executing ${msg.name}()...`);
      if (msg.name === "check_company_policy") {
        setAgentPipeline(3, "GROUNDING SOP", `Checking DeliverEx SOP rules for "${msg.args?.topic || "policy"}"...`, "cyan");
      } else {
        setAgentPipeline(4, "EXECUTING TOOL", `Running ${msg.name}() against live ERP...`, "emerald");
      }
      pushAgentAction("TOOL START", `${msg.name}(${JSON.stringify(msg.args || {})})`, "cyan");
      break;

    case "tool_call_result":
      logToolCall(msg.name, msg.args, msg.meta?.status || "OK", msg.meta?.elapsed_ms);
      if (msg.name === "check_company_policy" && msg.result?.matched_policies) {
        msg.result.matched_policies.forEach((p) => highlightedPolicyIds.add(p.id));
        refreshPoliciesHighlight();
        pushAgentAction("SOP GROUNDED", `Matched ${msg.result.matched_policies.map((p) => p.id).join(", ")}`, "cyan");
      }
      if (msg.name === "update_frontline_guidance" && msg.meta?.guidance) {
        updateFrontlineHud(msg.meta.guidance);
      }
      if (msg.name === "record_delivery_and_update_ledger") {
        const needsHitl = msg.result?.needs_manager_approval;
        setAgentPipeline(
          needsHitl ? 4 : 5,
          needsHitl ? "HITL APPROVAL" : "ERP SETTLED",
          needsHitl
            ? `Exception flagged for ${msg.result?.approval?.customer_name || "store"} — awaiting Priya 1-tap approval`
            : `Tally/SAP settled & WhatsApp receipt dispatched!`,
          needsHitl ? "amber" : "emerald"
        );
      }
      if (msg.result?.customer_name || msg.result?.name) {
        syncActiveStoreDropdown(msg.result.customer_name || msg.result.name);
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
    playSpatialChime("approve");
    showGlassToast("✅ Invoice Settled!", `${approval.customer_name} approved (₹${approval.discount_requested} disc) • WhatsApp receipt sent.`, "emerald");
    setAgentPipeline(5, "SETTLED • RECEIPT", `Priya approved ${approval.customer_name} — Tally settled & WhatsApp receipt sent!`, "emerald");
    pushAgentAction("HITL APPROVED", `${approval.customer_name} settled (₹${approval.discount_requested} disc). Receipt ${receipt?.receipt_id || ""} sent.`, "emerald");
    addSystemBanner(`✅ Priya Sharma APPROVED ${approval.customer_name} (Rs ${approval.discount_requested} discount) — looped back to Raju's live call!`);
    if (receipt) showReceiptCard(receipt.receipt_id, receipt.message);
    if (!liveReady) {
      const reply = `Badhiya khabar Raju bhai! Priya ma'am ne Rs ${approval.discount_requested} special discount approve kar diya hai. ${approval.customer_name} ka invoice Tally mein settle ho gaya aur official receipt aapke WhatsApp pe bhej di gayi hai!`;
      speakDemoVoice(reply, 340);
    }
  } else if (decision === "REJECTED") {
    setAgentPipeline(5, "DISCOUNT REJECTED", `Priya rejected ₹${approval.discount_requested} discount for ${approval.customer_name}.`, "rose");
    pushAgentAction("HITL REJECTED", `Extra discount denied for ${approval.customer_name}; credit balance kept open.`, "rose");
    addSystemBanner(`❌ Priya Sharma REJECTED Rs ${approval.discount_requested} extra discount for ${approval.customer_name}.`);
    if (!liveReady) {
      const reply = `Raju bhai, Priya ma'am ne Rs ${approval.discount_requested} ka extra discount approve nahi kiya hai. Remaining balance customer ke credit account mein open rahega.`;
      speakDemoVoice(reply, 360);
    }
  } else if (decision === "TAKE_OVER") {
    setAgentPipeline(4, "WARM HANDOFF", `Connecting Raju live to Area Manager Priya Sharma...`, "cyan");
    pushAgentAction("LIVE TAKEOVER", `Priya Sharma joining live voice call for ${approval.customer_name}.`, "cyan");
    addSystemBanner(`📞 Area Manager Priya Sharma is taking over the live call for ${approval.customer_name}!`);
    if (!liveReady) {
      const reply = `Raju bhai, main aapko seedha Priya ma'am se connect kar raha hoon. Unke paas aapki poori delivery details screen par aa chuki hain.`;
      speakDemoVoice(reply, 310);
    }
  }
}

// --- GUIDED DEMO STEPS & CUSTOM TEXT (Powered by Backend Workflow Engine) ---
async function waitForWsReady(maxMs = 700) {
  const start = Date.now();
  while (ws && ws.readyState === WebSocket.CONNECTING && Date.now() - start < maxMs) {
    await new Promise((r) => setTimeout(r, 60));
  }
  return Boolean(ws && ws.readyState === WebSocket.OPEN && (liveReady || wsWorkflowReady));
}

async function runGuidedStep(step) {
  if (!callActive) await startLiveCall();
  const wsReady = await waitForWsReady(650);

  if (step === 2) {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    flushPlaybackAudio();
  }

  if (wsReady) {
    if (step === 2 && liveReady) {
      interruptionCount += 1;
      document.getElementById("bargeInBadge").textContent = String(interruptionCount);
      addInterruptionBadge();
    }
    setVoiceLoopStage(step === 2 ? "bargein" : "working", `Running backend workflow for Step ${step}...`);
    ws.send(JSON.stringify({ type: "guided_step", step, preferred_language: serverLangPref() }));
    return;
  }

  // HTTP fallback to backend workflow engine
  setSpeakingIndicator("Thinking + Backend Workflow", "cyan");
  setVoiceLoopStage(step === 2 ? "bargein" : "working", `Running backend workflow for Step ${step}...`);
  const prefQ = `?preferred_language=${encodeURIComponent(serverLangPref())}`;
  const res = await fetch(`/api/agent/guided/${step}${prefQ}`, { method: "POST" }).then((r) => r.json());
  applyBackendWorkflowResponse(res, res.user_text);
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
  const wsReady = await waitForWsReady(650);
  if (wsReady) {
    setVoiceLoopStage("working", `Processing "${text.slice(0, 40)}..." via WebSocket backend...`);
    ws.send(JSON.stringify({ type: "text_turn", text, active_store: getActiveStoreName(), preferred_language: serverLangPref() }));
    return;
  }

  setAgentPipeline(2, "PARSING TURN", `Running backend workflow for: "${text.slice(0, 48)}..."`, "cyan");
  setVoiceLoopStage("working", "Backend workflow analyzing intent, SOPs & ERP...");
  pushAgentAction("CUSTOM TURN", text, "cyan");

  const res = await fetch("/api/agent/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      driver_name: "Raju Kumar",
      active_store: getActiveStoreName(),
      channel: "GEMINI_LIVE_VOICE",
      preferred_language: serverLangPref(),
    }),
  }).then((r) => r.json());
  applyBackendWorkflowResponse(res, text);
}

function applyBackendWorkflowResponse(res, userText) {
  if (!res) return;
  if (res.lang_code) applyServerLanguage(res.lang_code, res.intent);
  if (res.is_barge_in) {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    flushPlaybackAudio();
    interruptionCount += 1;
    document.getElementById("bargeInBadge").textContent = String(interruptionCount);
    addInterruptionBadge();
    setSpeakingIndicator("⚡ Interrupted (Barge-In)", "amber");
    setVoiceLoopStage("bargein", "⚡ Interrupted! Agents grounding SOP & updating Tally...");
    playSpatialChime("bargein");
    showGlassToast("⚡ Barge-In Detected", "AI audio flushed mid-sentence; adapting to driver correction.", "amber");
    pushAgentAction("BARGE-IN", "Audio flushed mid-sentence; adapting via backend workflow.", "amber");
  }

  if (userText) appendTranscript("user", userText, true);

  (res.tool_events || []).forEach((ev) => {
    logToolCall(ev.name, ev.args, ev.meta?.status || "OK", ev.meta?.elapsed_ms);
    if (ev.name === "check_company_policy" && ev.result?.matched_policies) {
      ev.result.matched_policies.forEach((p) => highlightedPolicyIds.add(p.id));
      refreshPoliciesHighlight();
      pushAgentAction("SOP GROUNDED", ev.result.matched_policies.map((p) => p.id).join(", "), "cyan");
    }
    if (ev.result?.customer_name || ev.result?.name) {
      syncActiveStoreDropdown(ev.result.customer_name || ev.result.name);
    }
  });

  if (res.guidance) updateFrontlineHud(res.guidance);
  if (res.state) renderErpState(res.state);

  const needsHitl = Boolean(res.result?.needs_manager_approval);
  if (res.intent === "ESCALATE") {
    setAgentPipeline(4, "WARM HANDOFF", "Escalated to Area Manager Priya Sharma (SOP-6.0).", "rose");
    pushAgentAction("ESCALATION", `Handoff ${res.result?.handoff_id || ""} sent to Priya Sharma`, "rose");
  } else if (needsHitl) {
    setAgentPipeline(4, "HITL DISPATCHED", `Exception routed to Priya Ma'am (${res.result?.approval?.policy_ref || "SOP"})`, "amber");
    pushAgentAction("TALLY + HITL", `${res.result?.tally_entry_id || ""} logged; awaiting Priya 1-tap approval`, "amber");
  } else if (res.intent === "RECORD_DELIVERY" && res.result?.success) {
    setAgentPipeline(5, "AUTO-SETTLED", `${res.result.customer_name} synced to Tally/SAP & WhatsApp receipt sent!`, "emerald");
    pushAgentAction("SETTLED", `${res.result.tally_entry_id} • ₹${Number(res.result.cash_posted_inr || 0).toLocaleString("en-IN")}`, "emerald");
  } else if (res.customer_match?.found) {
    setAgentPipeline(4, "TALLY LOOKUP OK", `Found ${res.customer_match.customer_id} (${res.customer_match.pending_invoice_id})`, "emerald");
    pushAgentAction("ERP LOOKUP", `${res.customer_match.pending_invoice_id} matched (${res.processing_ms}ms)`, "emerald");
  } else {
    setAgentPipeline(4, "WORKFLOW DONE", `Processed ${res.intent || "TURN"} (${res.processing_ms}ms)`, "emerald");
  }

  if (res.reply_text) {
    speakDemoVoice(res.reply_text, Math.max(180, Math.round(res.processing_ms || 320)), res.audio_b64 || null);
  }
}

async function callDemoTool(name, args) {
  const res = await fetch("/api/demo/tool", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, args, channel: "GEMINI_LIVE_VOICE" }),
  });
  return await res.json();
}

function pickNaturalIndianVoice() {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  const code = effectiveLangCode();
  if (code === "hi" || code === "ta" || code === "te") {
    const locale = code === "hi" ? /hi[-_]IN/i : code === "ta" ? /ta[-_]IN/i : /te[-_]IN/i;
    const native = voices.find((v) => locale.test(v.lang));
    if (native) return native;
  }
  const preferred = [
    /neerja/i,
    /swara/i,
    /google\s*हिन्दी/i,
    /google\s*hindi/i,
    /prabhat/i,
    /heera/i,
    /ravi/i,
    /en-IN/i,
    /hi-IN/i,
  ];
  for (const pat of preferred) {
    const match = voices.find((v) => pat.test(v.name) || pat.test(v.lang));
    if (match) return match;
  }
  return voices.find((v) => /natural|online|google/i.test(v.name)) || null;
}

if ("speechSynthesis" in window && typeof window.speechSynthesis.getVoices === "function") {
  window.speechSynthesis.getVoices();
}

async function playNeuralAudioBase64(b64, onComplete, onFallback) {
  try {
    if (!playbackCtx) {
      playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (playbackCtx.state === "suspended") {
      await playbackCtx.resume();
    }

    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);

    const audioBuffer = await playbackCtx.decodeAudioData(bytes.buffer.slice(0));
    flushPlaybackAudio();

    const source = playbackCtx.createBufferSource();
    source.buffer = audioBuffer;

    const analyser = playbackCtx.createAnalyser();
    analyser.fftSize = 256;
    const freqBins = new Uint8Array(analyser.frequencyBinCount);

    source.connect(analyser);
    analyser.connect(playbackCtx.destination);
    activeAudioSources.push(source);

    let stopped = false;
    const pumpEnergy = () => {
      if (stopped || !activeAudioSources.includes(source)) return;
      analyser.getByteTimeDomainData(freqBins);
      let sum = 0;
      for (let i = 0; i < freqBins.length; i++) {
        const d = (freqBins[i] - 128) / 128.0;
        sum += d * d;
      }
      const rms = Math.sqrt(sum / freqBins.length);
      currentEnergy = Math.max(0.14, Math.min(1, rms * 4.5));
      requestAnimationFrame(pumpEnergy);
    };

    source.onended = () => {
      stopped = true;
      activeAudioSources = activeAudioSources.filter((s) => s !== source);
      if (onComplete) onComplete();
    };

    ttsStartedAt = Date.now();
    ttsCooldownUntil = Date.now() + 900;
    source.start(0);
    requestAnimationFrame(pumpEnergy);
  } catch {
    if (onFallback) onFallback();
  }
}

function speakDemoVoice(text, simulatedTtfaMs, neuralAudioB64 = null) {
  updateLatencyBadge(simulatedTtfaMs);
  appendTranscript("assistant", text, true);
  setSpeakingIndicator("AI Speaking", "emerald");
  setVoiceLoopStage("asking", `Asking / replying back: "${text.slice(0, 56)}..."`);
  lastSpokenAiText = text;
  currentEnergy = 0.42;
  vadRecording = false;
  vadChunks = [];
  vadSilenceMs = 0;
  vadSpeechFrames = 0;
  ttsStartedAt = Date.now();
  ttsCooldownUntil = Date.now() + 1200;

  const returnToListen = () => {
    currentEnergy = 0.04;
    ttsCooldownUntil = Date.now() + 650;
    setSpeakingIndicator("Listening", "cyan");
    if (callActive) {
      setVoiceLoopStage("catching", "Listening again — speak your reply or interrupt anytime!");
    }
  };

  const speakBrowserFallback = () => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      const naturalVoice = pickNaturalIndianVoice();
      if (naturalVoice) utter.voice = naturalVoice;
      utter.lang = naturalVoice?.lang || "en-IN";
      utter.rate = 1.03;
      utter.pitch = 1.02;
      utter.onstart = () => {
        ttsStartedAt = Date.now();
        ttsCooldownUntil = Date.now() + 850;
      };
      utter.onend = returnToListen;
      utter.onerror = returnToListen;
      window.speechSynthesis.speak(utter);
    } else {
      setTimeout(returnToListen, 2200);
    }
  };

  if (neuralAudioB64) {
    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel(); } catch {}
    }
    playNeuralAudioBase64(neuralAudioB64, returnToListen, speakBrowserFallback);
    return;
  }

  speakBrowserFallback();
}

// --- VOICE CATCHER + AGENTS WORKING & ASKING-AGAIN LOOP STAGE ---
let currentOrbState = "standby";
function setVoiceLoopStage(stage, captionText) {
  currentOrbState = stage || "standby";
  const orbShell = document.getElementById("plasmaOrbShell");
  const pill = document.getElementById("voiceCatcherPill");
  const nCatch = document.getElementById("vLoopCatch");
  const nWork = document.getElementById("vLoopWork");
  const nAsk = document.getElementById("vLoopAsk");
  const t1 = document.getElementById("vLoopTrack1");
  const t2 = document.getElementById("vLoopTrack2");
  const gear = document.getElementById("vLoopWorkGear");
  const cap = document.getElementById("voiceLoopCaption");

  [nCatch, nWork, nAsk].forEach((n) => n?.classList.remove("is-active"));
  orbShell?.classList.remove("orb-state-catching", "orb-state-working", "orb-state-asking", "orb-state-bargein");
  t1?.classList.remove("is-flowing", "is-returning");
  t2?.classList.remove("is-flowing", "is-returning");
  gear?.classList.remove("voice-spin-active");

  // Highlight Spatial Mind Graph SVG nodes
  const m1 = document.getElementById("mindNode1");
  const m2 = document.getElementById("mindNode2");
  const m3 = document.getElementById("mindNode3");
  const m4 = document.getElementById("mindNode4");
  [m1, m2, m3, m4].forEach((m) => m?.setAttribute("stroke-width", "1.2"));

  if (stage === "catching") {
    orbShell?.classList.add("orb-state-catching");
    nCatch?.classList.add("is-active");
    t1?.classList.add("is-flowing");
    m1?.setAttribute("stroke-width", "2.8");
    if (pill) {
      pill.className = "text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-200 border border-cyan-400/45 flex items-center gap-1.5";
      pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span><span>Catching Voice</span>`;
    }
  } else if (stage === "working") {
    orbShell?.classList.add("orb-state-working");
    nWork?.classList.add("is-active");
    t1?.classList.add("is-flowing");
    t2?.classList.add("is-flowing");
    gear?.classList.add("voice-spin-active");
    m2?.setAttribute("stroke-width", "2.8");
    m3?.setAttribute("stroke-width", "2.8");
    if (pill) {
      pill.className = "text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-400/45 flex items-center gap-1.5";
      pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span><span>Agents Working</span>`;
    }
  } else if (stage === "asking") {
    orbShell?.classList.add("orb-state-asking");
    nAsk?.classList.add("is-active");
    t2?.classList.add("is-returning");
    m4?.setAttribute("stroke-width", "2.8");
    if (pill) {
      pill.className = "text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-emerald-500/25 text-emerald-200 border border-emerald-400/45 flex items-center gap-1.5";
      pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span><span>Asking / Replying</span>`;
    }
  } else if (stage === "bargein") {
    orbShell?.classList.add("orb-state-bargein");
    nCatch?.classList.add("is-active");
    nWork?.classList.add("is-active");
    t1?.classList.add("is-flowing");
    gear?.classList.add("voice-spin-active");
    m1?.setAttribute("stroke-width", "2.8");
    m2?.setAttribute("stroke-width", "2.8");
    if (pill) {
      pill.className = "text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-rose-500/25 text-rose-200 border border-rose-400/50 flex items-center gap-1.5";
      pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping"></span><span>⚡ Barge-In Catch</span>`;
    }
  } else {
    if (pill) {
      pill.className = "text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/35 flex items-center gap-1.5";
      pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span><span>Voice Catcher • Standby</span>`;
    }
  }

  if (cap && captionText) {
    const dotCol = stage === "asking" ? "bg-emerald-400" : stage === "working" ? "bg-amber-400" : stage === "bargein" ? "bg-rose-400" : "bg-cyan-400";
    cap.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${dotCol} shrink-0"></span><span class="truncate">${escapeHtml(captionText)}</span>`;
  }
}

// --- OWNER AUTH, AUDIT VAULT & TALLYPRIME EXPORT ---
function updateOwnerAuthUi() {
  const btn = document.getElementById("ownerAuthBtn");
  if (!btn) return;
  if (ownerSessionState.token_valid) {
    btn.textContent = "🔓 Priya Verified";
    btn.className = "btn-tactile mono text-[10px] font-bold px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-200 border border-emerald-400/45";
  } else if (!ownerSessionState.auth_enforced) {
    btn.textContent = "🔓 Dev Mode";
    btn.className = "btn-tactile mono text-[10px] font-bold px-2.5 py-1 rounded-full bg-cyan-500/20 text-cyan-200 border border-cyan-400/45";
  } else {
    btn.textContent = "🔒 Unlock Priya";
    btn.className = "btn-tactile mono text-[10px] font-bold px-2.5 py-1 rounded-full bg-amber-500/25 text-amber-200 border border-amber-400/55 animate-pulse";
  }
}

function openOwnerPinModal(callback = null) {
  pendingAuthCallback = callback;
  document.getElementById("ownerPinModal")?.classList.remove("hidden");
  setTimeout(() => document.getElementById("ownerPinInput")?.focus(), 40);
}

function closeOwnerPinModal() {
  document.getElementById("ownerPinModal")?.classList.add("hidden");
  pendingAuthCallback = null;
}

async function quickDemoOwnerUnlock() {
  const inp = document.getElementById("ownerPinInput");
  if (inp) inp.value = "4242";
  await submitOwnerPin();
}

async function submitOwnerPin() {
  const pin = (document.getElementById("ownerPinInput")?.value || "").trim();
  if (!pin) return;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin, actor: "Priya Sharma (Area Manager)" }),
    });
    if (!res.ok) {
      showGlassToast("❌ Invalid PIN", "Enter the configured Owner PIN (demo: 4242).", "rose");
      return;
    }
    const data = await res.json();
    ownerToken = data.token || "";
    try { localStorage.setItem("deliverex_owner_token", ownerToken); } catch {}
    ownerSessionState = { authenticated: true, token_valid: true, auth_enforced: true, actor: data.actor };
    updateOwnerAuthUi();
    showGlassToast("🔓 Owner Authenticated", "Priya Sharma verified — approvals & Tally exports unlocked.", "emerald");
    const cb = pendingAuthCallback;
    closeOwnerPinModal();
    if (cb) await cb();
  } catch (err) {
    showGlassToast("⚠️ Auth Error", err.message, "rose");
  }
}

async function downloadWithOwnerAuth(url, filename) {
  const res = await fetch(url, { headers: getOwnerHeaders() });
  if (res.status === 401) {
    openOwnerPinModal(() => downloadWithOwnerAuth(url, filename));
    return;
  }
  if (!res.ok) {
    showGlassToast("⚠️ Export Failed", `HTTP ${res.status}`, "rose");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showGlassToast("📥 Export Ready", `Downloaded ${filename} + logged to Audit Vault.`, "emerald");
  fetch("/api/state").then((r) => r.json()).then((d) => renderErpState(d.state)).catch(() => {});
}

function exportTallyXml() {
  downloadWithOwnerAuth("/api/ledger/export/tally.xml", "deliverex_tally_vouchers.xml");
}

function exportLedgerCsv() {
  downloadWithOwnerAuth("/api/ledger/export/ledger.csv", "deliverex_ledger.csv");
}

// --- PRIYA'S 1-TAP MANAGER APPROVAL (HITL) ---
async function decideApproval(approvalId, decision) {
  try {
    const res = await fetch(`/api/approvals/${approvalId}/decide`, {
      method: "POST",
      headers: getOwnerHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ decision }),
    });
    if (res.status === 401) {
      openOwnerPinModal(() => decideApproval(approvalId, decision));
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showGlassToast("⚠️ Approval Error", err.detail || `HTTP ${res.status}`, "rose");
      return;
    }
    const data = await res.json();
    renderErpState(data.state);

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      handleManagerDecisionUi(data);
    }
  } catch (err) {
    console.error("Approval error:", err);
  }
}

// --- WHATSAPP BUSINESS CHAT & VOICE NOTE CONTROLLER ---
function formatWaTime(isoStr) {
  if (!isoStr) return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const parts = String(isoStr).split(" ");
  return parts[1] ? parts[1].slice(0, 5) : String(isoStr).slice(0, 5);
}

function renderWhatsAppMessages(messages) {
  const feed = document.getElementById("waChatFeed");
  if (!feed) return;

  const incomingList = Array.isArray(messages) ? messages : [];
  if (!waInitialized) {
    incomingList.forEach((m) => seenWaMsgIds.add(m.msg_id));
    waInitialized = true;
  } else if (activeDriverTab !== "whatsapp") {
    let added = 0;
    incomingList.forEach((m) => {
      if (!seenWaMsgIds.has(m.msg_id)) {
        seenWaMsgIds.add(m.msg_id);
        if (m.sender !== "driver") added += 1;
      }
    });
    if (added > 0) {
      waUnreadCount += added;
      const badge = document.getElementById("waUnreadBadge");
      if (badge) {
        badge.textContent = String(waUnreadCount);
        badge.classList.remove("hidden");
      }
    }
  } else {
    incomingList.forEach((m) => seenWaMsgIds.add(m.msg_id));
  }

  feed.innerHTML = "";
  incomingList.forEach((m) => {
    const timeStr = formatWaTime(m.created_at);
    const meta = m.metadata || {};
    const div = document.createElement("div");

    if (m.sender === "driver") {
      div.className = "ml-auto subtile-4d bg-emerald-600/35 border-emerald-400/40 text-white text-xs p-2.5 rounded-2xl rounded-tr-none max-w-[88%] space-y-1.5";
      let mediaHtml = "";
      if (m.msg_type === "image" && m.media_data_url) {
        mediaHtml = `<img src="${m.media_data_url}" alt="WhatsApp Photo Proof" class="w-full max-h-32 object-cover rounded-xl border border-white/20" />`;
      } else if (m.msg_type === "audio" && m.media_data_url) {
        mediaHtml = `<audio controls src="${m.media_data_url}" class="w-full h-8"></audio>`;
      }
      div.innerHTML = `
        ${mediaHtml}
        <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(m.body)}</div>
        <div class="flex items-center justify-end gap-1 text-[9px] text-emerald-200/80 mono">
          <span>${timeStr}</span>
          <span class="text-cyan-300 font-bold">✓✓</span>
        </div>
      `;
    } else if (m.sender === "system") {
      div.className = "text-center text-[11px] text-amber-200 bg-amber-500/15 border border-amber-400/30 rounded-xl py-1 px-2";
      div.textContent = m.body;
    } else {
      const isReceipt = m.msg_type === "receipt";
      const isManager = m.sender === "manager";
      const senderLabel = isManager
        ? "👩‍💼 Priya Sharma (Area Manager)"
        : (meta.sender_label || "DeliverEx Official Ops");
      div.className = isReceipt
        ? "subtile-4d text-emerald-50 text-xs p-2.5 rounded-2xl rounded-tl-none max-w-[94%] border-emerald-400/55 bg-emerald-950/50 space-y-1"
        : isManager
        ? "subtile-4d text-amber-50 text-xs p-2.5 rounded-2xl rounded-tl-none max-w-[94%] border-amber-400/50 bg-amber-950/35 space-y-1"
        : "subtile-4d text-slate-100 text-xs p-2.5 rounded-2xl rounded-tl-none max-w-[94%] border-emerald-400/30 space-y-1";

      const badgeChip = isReceipt
        ? `<span class="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-emerald-400/20 text-emerald-300 border border-emerald-400/35">Official Receipt</span>`
        : meta.processing_ms != null
        ? `<span class="text-[9px] mono text-cyan-300/90">⚡ ${meta.processing_ms}ms • ${meta.used_gemini ? "Gemini AI" : "Smart Ops"}</span>`
        : "";

      div.innerHTML = `
        <div class="flex items-center justify-between gap-2">
          <span class="text-[10px] font-bold ${isManager ? "text-amber-300" : "text-emerald-300"}">${escapeHtml(senderLabel)}</span>
          ${badgeChip}
        </div>
        <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(m.body)}</div>
        <div class="text-right text-[9px] text-slate-400 mono">${timeStr}</div>
      `;
    }

    feed.appendChild(div);
  });

  if (waSending) {
    const typing = document.createElement("div");
    typing.className = "subtile-4d text-emerald-200 text-[11px] px-3 py-2 rounded-2xl rounded-tl-none max-w-[70%] border-emerald-400/30 italic";
    typing.textContent = "DeliverEx Ops AI is processing...";
    feed.appendChild(typing);
  }

  feed.scrollTop = feed.scrollHeight;
}

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
      btn.textContent = "⏹";
      btn.title = "Stop & Send Voice Note";
      btn.className = "btn-tactile w-9 h-9 rounded-xl bg-gradient-to-b from-rose-400 to-rose-600 text-white font-black text-sm shrink-0 animate-pulse";
    } catch (err) {
      appendWaBubble("system", `Mic unavailable (${err.message}). Type a message or click "⚡ Sample Note" instead!`);
    }
  } else {
    waRecording = false;
    waRecorder.stop();
    btn.textContent = "🎤";
    btn.title = "Record & send WhatsApp voice note";
    btn.className = "btn-tactile w-9 h-9 rounded-xl bg-white/10 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-400/35 flex items-center justify-center text-sm shrink-0";
  }
}

async function sendSampleWhatsAppNote() {
  const sampleText =
    "Shri Ganesh Stores pe 30 bags ACC cement deliver kar diya, 22000 cash received, koi damage nahi hai.";
  await uploadWhatsAppVoiceNote(null, sampleText);
}

async function sendWhatsAppTextChat(event) {
  if (event) event.preventDefault();
  const input = document.getElementById("waChatInput");
  const text = (input?.value || "").trim();
  if (!text || waSending) return;
  input.value = "";
  await uploadWhatsAppVoiceNote(null, text);
}

async function sendWhatsAppQuickMessage(text) {
  if (!text || waSending) return;
  await uploadWhatsAppVoiceNote(null, text);
}

async function sendWhatsAppDamageProof() {
  if (waSending) return;
  const storeName = getActiveStoreName();
  const dataUrl = generateSampleDamageProofImage(storeName);
  await uploadWhatsAppVoiceNote(
    null,
    `${storeName} pe 2 bags torn nikle — photo proof bhej diya hai`,
    dataUrl
  );
}

function handleWaPhotoSelected(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async () => {
    const storeName = getActiveStoreName();
    await uploadWhatsAppVoiceNote(
      null,
      `${storeName} ke damaged bags ki photo proof attach ki hai`,
      String(reader.result || "")
    );
  };
  reader.readAsDataURL(file);
  event.target.value = "";
}

async function uploadWhatsAppVoiceNote(audioBlob, textFallback, imageDataUrl = null) {
  const storeName = getActiveStoreName();
  waSending = true;
  setAgentPipeline(2, "WHATSAPP CHAT", `Processing WhatsApp message${storeName ? ` (${storeName})` : ""}...`, "cyan");
  pushAgentAction("WHATSAPP MSG", textFallback || (imageDataUrl ? "Photo proof received" : "Voice note received"), "cyan");

  appendWaBubble(
    "driver",
    imageDataUrl
      ? `📷 ${textFallback || "Photo proof attached"}`
      : audioBlob
      ? "🎤 [WhatsApp Voice Note] Uploading..."
      : textFallback
  );
  if (cachedErpState?.whatsapp_messages) {
    // Show typing indicator below optimistic bubble
    const feed = document.getElementById("waChatFeed");
    const typing = document.createElement("div");
    typing.id = "waTypingIndicator";
    typing.className = "subtile-4d text-emerald-200 text-[11px] px-3 py-2 rounded-2xl rounded-tl-none max-w-[70%] border-emerald-400/30 italic";
    typing.textContent = "DeliverEx Ops AI is typing...";
    feed?.appendChild(typing);
    if (feed) feed.scrollTop = feed.scrollHeight;
  }

  try {
    const fd = new FormData();
    if (audioBlob) fd.append("file", audioBlob, "voice_note.webm");
    if (textFallback) fd.append("text", textFallback);
    if (imageDataUrl) fd.append("image_data_url", imageDataUrl);
    if (storeName) fd.append("active_store", storeName);
    fd.append("driver_name", "Raju Kumar");

    const resp = await fetch("/api/whatsapp/voice-note", { method: "POST", body: fd });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${errText.slice(0, 120)}`);
    }
    const res = await resp.json();
    waSending = false;

    if (Array.isArray(res.grounded_policies)) {
      res.grounded_policies.forEach((p) => highlightedPolicyIds.add(p.id));
      refreshPoliciesHighlight();
    }
    if (res.customer_match?.name || res.erp_result?.customer_name) {
      syncActiveStoreDropdown(res.customer_match?.name || res.erp_result?.customer_name);
    }

    renderErpState(res.state);
    logToolCall(
      `whatsapp_${String(res.intent || "chat").toLowerCase()}`,
      res.extracted || { text: textFallback },
      res.erp_result?.needs_manager_approval ? "ESCALATED" : (res.used_gemini ? "GEMINI_AI" : "SYNCED"),
      res.processing_ms
    );

    const needsHitl = Boolean(res.erp_result?.needs_manager_approval);
    setAgentPipeline(
      needsHitl ? 4 : 5,
      needsHitl ? "WA • HITL QUEUED" : `WA • ${res.intent || "REPLIED"}`,
      needsHitl
        ? `WhatsApp exception sent to Priya Ma'am (${res.processing_ms}ms)`
        : `WhatsApp chat handled in ${res.processing_ms}ms`,
      needsHitl ? "amber" : "emerald"
    );
    pushAgentAction(
      "WA REPLY SENT",
      `${res.intent || "CHAT"} • ${res.customer_match?.name || res.erp_result?.customer_name || "DeliverEx Ops"} (${res.processing_ms}ms)`,
      needsHitl ? "amber" : "emerald"
    );

    if (res.erp_result?.receipt) {
      showReceiptCard(res.erp_result.receipt.receipt_id, res.erp_result.receipt.message);
    }

    // Co-work with Live Voice Transcript & Central Agent Screen
    const driverText = textFallback || res.extracted?.transcript || "🎤 [WhatsApp Voice Note]";
    appendTranscript("user", `[WhatsApp] ${driverText}`, true);
    if (res.whatsapp_reply) {
      appendTranscript("assistant", `[WhatsApp] ${res.whatsapp_reply}`, true);
    }
    setVoiceLoopStage("asking", "WhatsApp & Live Ops synced — ready for next update!");
  } catch (err) {
    waSending = false;
    document.getElementById("waTypingIndicator")?.remove();
    appendWaBubble("system", `Could not send WhatsApp message (${err.message}). Please try again.`);
    setAgentPipeline(0, "WA ERROR", `WhatsApp request failed: ${err.message}`, "rose");
  }
}

function appendWaBubble(sender, text) {
  const feed = document.getElementById("waChatFeed");
  if (!feed) return;
  const div = document.createElement("div");
  if (sender === "driver") {
    div.className = "ml-auto subtile-4d bg-emerald-600/35 border-emerald-400/40 text-white text-xs p-2.5 rounded-2xl rounded-tr-none max-w-[88%] whitespace-pre-wrap";
  } else if (sender === "bot") {
    div.className = "subtile-4d text-slate-100 text-xs p-2.5 rounded-2xl rounded-tl-none max-w-[94%] border-emerald-400/35 whitespace-pre-wrap";
  } else {
    div.className = "text-center text-[11px] text-amber-200 bg-amber-500/15 border border-amber-400/30 rounded-xl py-1 px-2";
  }
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// --- REALISTIC MARKET NOISE SYNTHESIZER ---
function toggleMarketNoise() {
  const btn = document.getElementById("noiseToggleBtn");
  const dbBadge = document.getElementById("noiseDbBadge");
  if (noiseActive) {
    noiseActive = false;
    clearInterval(noiseInterval);
    if (noiseCtx) { try { noiseCtx.close(); } catch {} noiseCtx = null; }
    btn.textContent = "🔊 Noise: OFF";
    btn.className = "btn-tactile py-2.5 px-2.5 rounded-xl font-semibold text-xs bg-white/10 text-slate-200 border border-white/15";
    if (dbBadge) {
      dbBadge.textContent = "42 dB";
      dbBadge.className = "mono text-xs font-bold text-cyan-300";
    }
    return;
  }

  noiseActive = true;
  btn.textContent = "🔊 Noise: 78dB";
  btn.className = "btn-tactile py-2.5 px-2.5 rounded-xl font-bold text-xs bg-amber-500/25 text-amber-200 border border-amber-400/45";
  if (dbBadge) {
    dbBadge.textContent = "78 dB MANDI";
    dbBadge.className = "mono text-xs font-bold text-amber-400";
  }
  pushAgentAction("ACOUSTIC ENV", "78 dB Wholesale Mandi ambient noise active — noise suppression engaged.", "amber");

  noiseCtx = new (window.AudioContext || window.webkitAudioContext)();
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
  gain.gain.value = 0.045;

  src.connect(filter);
  filter.connect(gain);
  gain.connect(noiseCtx.destination);
  src.start();
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
    ? "subtile-4d p-2.5 rounded-2xl border-cyan-400/25 ml-4"
    : "subtile-4d p-2.5 rounded-2xl border-emerald-400/35 bg-emerald-950/35 mr-4";

  const label = role === "user"
    ? `<span class="text-[10px] font-bold uppercase text-cyan-300">🚚 Raju (Field Driver)</span>`
    : `<span class="text-[10px] font-bold uppercase text-emerald-300">🤖 DeliverEx Live AI</span>`;

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
  div.innerHTML = `<span class="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-400/45 shadow-sm shadow-amber-500/20">⚡ Mid-Sentence Interruption (Barge-In) — AI Audio Flushed</span>`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function addSystemBanner(text) {
  const feed = document.getElementById("transcriptFeed");
  if (feed.children.length === 1 && feed.firstElementChild.textContent.includes("Start a Live Call")) {
    feed.innerHTML = "";
  }
  const div = document.createElement("div");
  div.className = "text-[11px] text-cyan-100 bg-cyan-500/15 border border-cyan-400/30 rounded-xl px-2.5 py-1.5 backdrop-blur-sm";
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function logToolCall(name, args, status, elapsedMs) {
  if (status !== "RUNNING") toolCallCount += 1;
  const box = document.getElementById("toolLog");
  if (box.children.length === 1 && box.firstElementChild.textContent.includes("Waiting for spoken")) {
    box.innerHTML = "";
  }
  const row = document.createElement("div");
  const color = status === "ESCALATED" || status === "HANDOFF"
    ? "border-amber-400/40 bg-amber-500/10 text-amber-100"
    : "border-emerald-400/35 bg-emerald-500/10 text-emerald-100";
  row.className = `subtile-4d p-2.5 rounded-xl border ${color}`;
  const timeTxt = elapsedMs != null ? `${elapsedMs}ms` : "running...";
  row.innerHTML = `
    <div class="flex items-center justify-between font-bold">
      <span>⚙ ${name}()</span>
      <span class="text-[10px] px-2 py-0.5 rounded-full bg-black/50 border border-white/10">${status} • ${timeTxt}</span>
    </div>
    <div class="text-[10px] text-slate-300 mt-1 truncate">${escapeHtml(JSON.stringify(args || {}))}</div>
  `;
  box.prepend(row);
  updateRoleStatusDashboard();
  updateRouteRadarMap(cachedErpState);
}

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
        <div class="subtile-4d p-2.5 rounded-xl border transition ${
          active
            ? "bg-cyan-500/15 border-cyan-400/60 shadow-[0_0_20px_rgba(34,211,238,0.2)]"
            : "border-white/10"
        }">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold ${active ? "text-cyan-200" : "text-slate-100"}">${p.id}: ${p.title}</span>
            ${active ? `<span class="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded-full bg-cyan-400 text-slate-950">GROUNDED</span>` : ""}
          </div>
          <p class="text-[11px] text-slate-300/85 mt-1 leading-snug">${p.rule}</p>
        </div>
      `;
    })
    .join("");
}

// --- WORKING LEDGER FILTERS ---
function setLedgerFilter(filterMode) {
  activeLedgerFilter = filterMode;
  ["ALL", "SETTLED", "PENDING"].forEach((mode) => {
    const btn = document.getElementById(`filterLedger${mode}`);
    if (!btn) return;
    btn.className =
      mode === filterMode
        ? "px-2 py-0.5 rounded font-bold bg-emerald-500/25 text-emerald-200"
        : "px-2 py-0.5 rounded font-semibold text-slate-400 hover:text-white";
  });
  applyLedgerFilters();
}

function applyLedgerFilters() {
  if (!cachedErpState) return;
  renderLedgerTable(cachedErpState.ledger || []);
}

function renderLedgerTable(ledger) {
  const q = (document.getElementById("ledgerSearchInput")?.value || "").trim().toLowerCase();
  const filtered = ledger.filter((r) => {
    const matchesSearch =
      !q ||
      r.customer_name.toLowerCase().includes(q) ||
      r.invoice_id.toLowerCase().includes(q) ||
      r.entry_id.toLowerCase().includes(q);
    if (!matchesSearch) return false;
    if (activeLedgerFilter === "SETTLED") return !r.tally_status.includes("PENDING") && !r.tally_status.includes("REJECTED");
    if (activeLedgerFilter === "PENDING") return r.tally_status.includes("PENDING");
    return true;
  });

  const shouldFlash = ledger.length > lastLedgerCount;
  lastLedgerCount = ledger.length;
  const tbody = document.getElementById("ledgerTableBody");

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="py-4 text-center text-xs text-slate-400">No ledger entries match this filter yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((r, idx) => {
      const badgeColor = r.tally_status.includes("PENDING")
        ? "bg-amber-500/20 text-amber-200 border border-amber-400/35"
        : r.tally_status.includes("REJECTED")
        ? "bg-rose-500/20 text-rose-200 border border-rose-400/35"
        : "bg-emerald-500/20 text-emerald-200 border border-emerald-400/35";
      return `
        <tr class="${shouldFlash && idx === 0 ? "flash-row" : ""} hover:bg-white/5 transition">
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
            <span class="text-[9px] font-bold px-2 py-0.5 rounded-full ${badgeColor}">${r.tally_status.replaceAll("_", " ")}</span>
          </td>
        </tr>
      `;
    })
    .join("");
}

function selectStoreFromDashboard(storeName) {
  syncActiveStoreDropdown(storeName);
  pushAgentAction("STORE TARGETED", `Active target switched to ${storeName}.`, "cyan");
  playSpatialChime("click");
}

// --- SPATIAL SOUND FX + AR LIGHTBOX + TOASTS ---
function toggleSfxMode() {
  sfxEnabled = !sfxEnabled;
  const btn = document.getElementById("toggleSfxBtn");
  if (btn) {
    btn.textContent = sfxEnabled ? "🔊 SFX: ON" : "🔇 SFX: OFF";
    btn.className = sfxEnabled
      ? "btn-tactile px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-white/10 text-slate-200 border border-white/15"
      : "btn-tactile px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-900/70 text-slate-400 border border-white/10";
  }
  if (sfxEnabled) playSpatialChime("click");
}

function playSpatialChime(kind = "click") {
  if (!sfxEnabled) return;
  try {
    if (!sfxCtx) sfxCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (sfxCtx.state === "suspended") sfxCtx.resume();
    const now = sfxCtx.currentTime;
    const notes =
      kind === "approve"
        ? [523.25, 659.25, 783.99]
        : kind === "bargein"
        ? [440, 311.13]
        : kind === "tool"
        ? [587.33, 880]
        : [660];
    notes.forEach((freq, idx) => {
      const osc = sfxCtx.createOscillator();
      const gain = sfxCtx.createGain();
      osc.type = kind === "bargein" ? "triangle" : "sine";
      osc.frequency.setValueAtTime(freq, now + idx * 0.055);
      gain.gain.setValueAtTime(0.001, now + idx * 0.055);
      gain.gain.exponentialRampToValueAtTime(0.045, now + idx * 0.055 + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.055 + 0.18);
      osc.connect(gain);
      gain.connect(sfxCtx.destination);
      osc.start(now + idx * 0.055);
      osc.stop(now + idx * 0.055 + 0.2);
    });
  } catch {}
}

function showGlassToast(title, detail, tone = "emerald") {
  const box = document.getElementById("toastContainer");
  if (!box) return;
  const border =
    tone === "amber"
      ? "border-amber-400/50 bg-amber-950/75"
      : tone === "rose"
      ? "border-rose-400/50 bg-rose-950/75"
      : "border-emerald-400/50 bg-emerald-950/75";
  const el = document.createElement("div");
  el.className = `toast-glass pointer-events-auto rounded-2xl border ${border} backdrop-blur-xl px-3.5 py-2.5 shadow-2xl`;
  el.innerHTML = `
    <div class="text-xs font-extrabold text-white">${escapeHtml(title)}</div>
    <div class="text-[11px] text-slate-200 mt-0.5">${escapeHtml(detail)}</div>
  `;
  box.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function openProofLightbox(src) {
  const modal = document.getElementById("visionLightbox");
  const img = document.getElementById("visionLightboxImg");
  if (!modal || !img || !src) return;
  img.src = src;
  modal.classList.remove("hidden");
  playSpatialChime("click");
}

function closeProofLightbox() {
  document.getElementById("visionLightbox")?.classList.add("hidden");
}

function updateRouteRadarMap(state) {
  const coords = {
    "Krishna Hardware": { x: 48, y: 42, route: "Route-4 • Old Delhi" },
    "Shri Ganesh Stores": { x: 162, y: 46, route: "Route-4 • Chandni Chowk" },
    "Bharat Traders": { x: 270, y: 36, route: "Route-2 • Sadar Bazar" },
    "Murugan Builders": { x: 266, y: 108, route: "Route-7 • T. Nagar Chennai" },
  };
  const activeStore = getActiveStoreName();
  const activePos = coords[activeStore] || coords["Krishna Hardware"];
  const truck = document.getElementById("mapTruckMarker");
  if (truck) truck.setAttribute("transform", `translate(${activePos.x},${activePos.y})`);
  const lbl = document.getElementById("mapActiveRouteLabel");
  if (lbl) lbl.textContent = activePos.route;

  const approvals = state?.approvals || [];
  (state?.customers || []).forEach((c) => {
    const pin = document.getElementById(`mapPin-${c.customer_id}`);
    if (!pin) return;
    const circles = pin.querySelectorAll("circle");
    const isSettled = Number(c.balance_due) === 0;
    const isPending = approvals.some((a) => a.customer_id === c.customer_id && a.status === "PENDING");
    const col = isSettled ? "#10b981" : isPending ? "#f59e0b" : "#38bdf8";
    if (circles[0]) {
      circles[0].setAttribute("stroke", col);
      circles[0].setAttribute("fill", col + "33");
    }
    if (circles[1]) circles[1].setAttribute("fill", col);
  });
}

function renderErpState(state) {
  if (!state) return;
  cachedErpState = state;

  const approvals = state.approvals || [];
  const ledger = state.ledger || [];
  const inventory = state.inventory || [];
  const customers = state.customers || [];

  // 0. Live KPI Strip Calculations
  const totalCash = ledger.reduce((sum, r) => sum + Number(r.cash_received || 0), 0);
  const totalOkBags = ledger.reduce((sum, r) => sum + Number(r.delivered_qty || 0), 0);
  const totalDmgBags = ledger.reduce((sum, r) => sum + Number(r.damaged_qty || 0), 0);
  const totalStock = inventory.reduce((sum, i) => sum + Number(i.warehouse_stock || 0), 0);
  const pendingApprovals = approvals.filter((a) => a.status === "PENDING");
  const settledCustomers = customers.filter((c) => Number(c.balance_due) === 0).length;
  const totalDue = customers.reduce((sum, c) => sum + Number(c.balance_due || 0), 0);

  const kCash = document.getElementById("kpiCashCollected");
  if (kCash) kCash.textContent = `₹${totalCash.toLocaleString("en-IN")}`;
  const kLed = document.getElementById("kpiLedgerCount");
  if (kLed) kLed.textContent = `${ledger.length} ledger ${ledger.length === 1 ? "entry" : "entries"} synced`;

  const kBags = document.getElementById("kpiBagsStats");
  if (kBags) kBags.textContent = `${totalOkBags} ok • ${totalDmgBags} dmg`;
  const kWh = document.getElementById("kpiWarehouseTotal");
  if (kWh) kWh.textContent = `${totalStock.toLocaleString("en-IN")} bags in warehouse`;

  const kPend = document.getElementById("kpiPendingHits");
  if (kPend) kPend.textContent = `${pendingApprovals.length} Pending`;
  const kTotApr = document.getElementById("kpiTotalApprovals");
  if (kTotApr) kTotApr.textContent = `${approvals.length} total exceptions`;

  const kSet = document.getElementById("kpiSettledRatio");
  if (kSet) kSet.textContent = `${settledCustomers} / ${customers.length}`;
  const kDue = document.getElementById("kpiTotalDue");
  if (kDue) kDue.textContent = `Outstanding: ₹${totalDue.toLocaleString("en-IN")}`;

  // 1. Manager Priya Approvals
  const pBadge = document.getElementById("pendingApprovalCount");
  pBadge.textContent = `${pendingApprovals.length} Pending`;
  pBadge.className = pendingApprovals.length > 0
    ? "mono text-xs font-bold px-2.5 py-0.5 rounded-full bg-amber-400 text-slate-950 animate-pulse shadow-lg shadow-amber-500/30"
    : "mono text-xs font-bold px-2.5 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/15";

  const qEl = document.getElementById("approvalQueue");
  if (approvals.length === 0) {
    qEl.innerHTML = `<div class="glass-well text-xs text-slate-400 rounded-xl p-3 text-center">No policy exceptions yet. Routine deliveries auto-sync to Tally/SAP!</div>`;
  } else {
    qEl.innerHTML = approvals
      .map((a) => {
        const isPending = a.status === "PENDING";
        const statusClass =
          a.status === "APPROVED"
            ? "bg-emerald-500/20 text-emerald-200 border-emerald-400/40"
            : a.status === "REJECTED"
            ? "bg-rose-500/20 text-rose-200 border-rose-400/40"
            : a.status === "TAKE_OVER"
            ? "bg-cyan-500/20 text-cyan-200 border-cyan-400/40"
            : "bg-amber-500/25 text-amber-200 border-amber-400/55";
        return `
          <div class="subtile-4d p-3 rounded-2xl border ${isPending ? "bg-amber-950/30 border-amber-400/55" : "border-white/10"}">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-bold text-white">${escapeHtml(a.customer_name)} <span class="mono text-[10px] text-cyan-300">(${a.policy_ref})</span></span>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${statusClass}">${a.status}</span>
            </div>
            <p class="text-[11px] text-slate-200 mt-1">${escapeHtml(a.summary)}</p>
            <div class="flex flex-wrap gap-1.5 mt-1.5 text-[10px] mono">
              ${a.discount_requested > 0 ? `<span class="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-200 border border-amber-400/30">Diff: -₹${a.discount_requested} disc</span>` : ""}
              ${a.damaged_qty > 0 ? `<span class="px-2 py-0.5 rounded-md bg-rose-500/15 text-rose-200 border border-rose-400/30">Quarantine: ${a.damaged_qty} bags</span>` : ""}
            </div>
            ${
              a.proof_image
                ? `<div onclick="openProofLightbox('${a.proof_image}')" class="mt-2 ar-scanner-wrap bg-slate-950/80 cursor-zoom-in" title="Click to inspect proof">
                     <div class="ar-corner ar-tl"></div><div class="ar-corner ar-tr"></div>
                     <div class="ar-corner ar-bl"></div><div class="ar-corner ar-br"></div>
                     <div class="ar-scanline"></div>
                     <img src="${a.proof_image}" alt="Visual proof of damage" class="w-full h-24 object-cover" />
                     <div class="px-2.5 py-1 text-[10px] text-cyan-200 flex items-center justify-between bg-black/60">
                       <span>👁️ Gemini Vision Verified (${a.damaged_qty || 2} torn bags)</span>
                       <span class="mono text-amber-300 font-bold">ZOOM 🔍</span>
                     </div>
                   </div>`
                : ""
            }
            ${
              isPending
                ? `<div class="flex gap-1.5 mt-2.5">
                     <button onclick="decideApproval('${a.approval_id}', 'APPROVED')" class="btn-tactile flex-1 py-1.5 rounded-xl bg-gradient-to-b from-emerald-400 to-emerald-500 text-slate-950 font-extrabold text-xs">✅ 1-Tap Approve</button>
                     <button onclick="decideApproval('${a.approval_id}', 'REJECTED')" class="btn-tactile px-2.5 py-1.5 rounded-xl bg-rose-500/20 text-rose-200 border border-rose-400/40 font-bold text-xs">❌ Reject</button>
                     <button onclick="decideApproval('${a.approval_id}', 'TAKE_OVER')" class="btn-tactile px-2.5 py-1.5 rounded-xl bg-cyan-500/20 text-cyan-200 border border-cyan-400/40 font-bold text-xs">📞 Take Over</button>
                   </div>`
                : `<div class="text-[10px] text-slate-400 mt-1.5">Decided by Priya Sharma &bull; ${a.decided_at || ""}</div>`
            }
          </div>
        `;
      })
      .join("");
  }

  // 2. Tally / SAP Ledger Table
  renderLedgerTable(ledger);

  // 3. Warehouse Inventory & Interactive Open Customer Invoices
  const invCustEl = document.getElementById("inventoryAndCustomers");
  const invHtml = inventory
    .map(
      (i) => `
      <div class="subtile-4d flex items-center justify-between text-[11px] px-3 py-2 rounded-xl border-white/10">
        <div>
          <span class="font-semibold text-white">${escapeHtml(i.item_name)}</span>
          <span class="mono text-[10px] text-slate-400 ml-1">(${i.sku_code})</span>
        </div>
        <div class="mono flex items-center gap-2">
          <span class="text-emerald-300 font-bold">${i.warehouse_stock} stock</span>
          <span class="text-rose-400 text-[10px]">${i.damaged_quarantine} dmg</span>
        </div>
      </div>`
    )
    .join("");

  const custHtml = customers
    .map(
      (c) => `
      <button type="button" onclick="selectStoreFromDashboard('${escapeHtml(c.name).replace(/'/g, "\\'")}')" class="subtile-4d w-full text-left flex items-center justify-between text-[11px] px-3 py-2 rounded-xl border-white/10 hover:border-cyan-400/45 cursor-pointer">
        <div>
          <span class="font-bold text-white">${escapeHtml(c.name)}</span>
          <span class="mono text-[10px] text-cyan-300/80 ml-1">${c.pending_invoice_id}</span>
        </div>
        <div class="mono flex items-center gap-2">
          <span class="${c.balance_due === 0 ? "text-emerald-400" : "text-amber-300"} font-bold">Due: ₹${Number(c.balance_due).toLocaleString("en-IN")}</span>
          <span class="text-[9px] px-2 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/10">${c.status}</span>
        </div>
      </button>`
    )
    .join("");

  invCustEl.innerHTML = `
    <div class="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Warehouse Stock</div>
    ${invHtml}
    <div class="text-[10px] uppercase tracking-wider text-slate-400 font-bold mt-1">Customer Invoices (Click to Target)</div>
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
          ? "bg-rose-500/20 text-rose-200 border-rose-400/40"
          : ins.severity === "MEDIUM"
          ? "bg-amber-500/20 text-amber-200 border-amber-400/40"
          : "bg-cyan-500/20 text-cyan-200 border-cyan-400/40";
      return `
        <div class="subtile-4d p-3.5 rounded-2xl border-white/10">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-bold text-white">${escapeHtml(ins.title)}</span>
            <span class="text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${sevColor}">${ins.severity}</span>
          </div>
          <p class="text-xs text-slate-200 mt-1.5">${escapeHtml(ins.detail)}</p>
          <div class="text-[10px] text-slate-400 mt-2 mono">${ins.route} &bull; ${ins.category} &bull; ${ins.created_at}</div>
        </div>
      `;
    })
    .join("");

  // 6. Sync WhatsApp Business Chat Feed & Workflow Stage
  renderWhatsAppMessages(state.whatsapp_messages || []);
  const wfEl = document.getElementById("waWorkflowStageBadge");
  if (wfEl && state.whatsapp_session) {
    const wf = state.whatsapp_session;
    const storeTag = wf.active_customer_name ? ` • ${wf.active_customer_name}` : "";
    wfEl.textContent = `Workflow: ${wf.workflow_stage || "IDLE"}${storeTag}`;
  }

  // 7. Render Tamper-Evident Audit Vault
  const auditSummary = state.audit_summary;
  if (auditSummary) {
    const sBadge = document.getElementById("auditStorageBadge");
    if (sBadge) sBadge.textContent = `Storage: ${(healthInfo.storage_mode || auditSummary.storage_backend || "sqlite").toUpperCase()}`;
    const cBadge = document.getElementById("auditChainBadge");
    if (cBadge) {
      const ok = Boolean(auditSummary.chain_verified);
      cBadge.textContent = ok ? `Hash Chain: Verified (${auditSummary.total_count})` : "Hash Chain: Tamper Alert!";
      cBadge.className = ok
        ? "mono text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-200 border border-emerald-400/40"
        : "mono text-xs font-bold px-3 py-1 rounded-full bg-rose-500/20 text-rose-200 border border-rose-400/40";
    }
    const auditBox = document.getElementById("auditVaultList");
    if (auditBox) {
      auditBox.innerHTML = (auditSummary.latest || []).map((a) => `
        <div class="subtile-4d p-3 rounded-2xl border-white/10">
          <div class="flex items-center justify-between gap-2">
            <span class="mono text-[11px] font-bold text-cyan-300">${escapeHtml(a.audit_id)} &bull; ${escapeHtml(a.action)}</span>
            <span class="mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-200 border border-emerald-400/30">${escapeHtml(a.role)}</span>
          </div>
          <p class="text-xs text-slate-200 mt-1">${escapeHtml(a.summary)}</p>
          <div class="text-[10px] text-slate-400 mt-1 mono truncate">Actor: ${escapeHtml(a.actor)} &bull; SHA256: ${escapeHtml((a.integrity_hash || "").slice(0, 14))}...</div>
        </div>
      `).join("");
    }
  }

  updateRoleStatusDashboard();
  updateRouteRadarMap(cachedErpState);
}

// --- TOTAL ROLE STATUS DASHBOARD SYNC ---
function updateRoleStatusDashboard() {
  const state = cachedErpState || { approvals: [], ledger: [], inventory: [], customers: [], receipts: [] };
  const approvals = state.approvals || [];
  const ledger = state.ledger || [];
  const customers = state.customers || [];
  const receipts = state.receipts || [];

  const totalCash = ledger.reduce((sum, r) => sum + Number(r.cash_received || 0), 0);
  const totalOk = ledger.reduce((sum, r) => sum + Number(r.delivered_qty || 0), 0);
  const totalDmg = ledger.reduce((sum, r) => sum + Number(r.damaged_qty || 0), 0);
  const totalDue = customers.reduce((sum, c) => sum + Number(c.balance_due || 0), 0);
  const settledCount = customers.filter((c) => Number(c.balance_due) === 0).length;
  const totalCustomers = Math.max(1, customers.length);
  const completionPct = Math.round((settledCount / totalCustomers) * 100);

  const pendingA = approvals.filter((a) => a.status === "PENDING").length;
  const approvedA = approvals.filter((a) => a.status === "APPROVED").length;
  const rejectedA = approvals.filter((a) => a.status === "REJECTED").length;
  const takeOverA = approvals.filter((a) => a.status === "TAKE_OVER").length;
  const proofCount = approvals.filter((a) => Boolean(a.proof_image)).length;
  const activeStore = getActiveStoreName();

  // Overall Progress Strip
  const ovBadge = document.getElementById("opsRoleOverallBadge");
  if (ovBadge) ovBadge.textContent = `${completionPct}% Routes Settled (${settledCount}/${customers.length})`;
  const ovBar = document.getElementById("opsRoleProgressBar");
  if (ovBar) ovBar.style.width = `${completionPct}%`;
  const boardPct = document.getElementById("rolesBoardCompletionPct");
  if (boardPct) boardPct.textContent = `${completionPct}% Settled`;

  // Role 1: Field Driver
  const driverStatus = callActive ? (liveReady ? "LIVE CALL" : "DEMO CALL") : ledger.length > 0 ? "ACTIVE ROUTE" : "STANDBY";
  const driverTone = callActive
    ? "bg-emerald-500/25 text-emerald-200 border-emerald-400/45"
    : ledger.length > 0
    ? "bg-cyan-500/20 text-cyan-200 border-cyan-400/35"
    : "bg-slate-500/20 text-slate-200 border-white/15";
  const sDrvBadge = document.getElementById("stripRoleDriverBadge");
  if (sDrvBadge) { sDrvBadge.textContent = driverStatus; sDrvBadge.className = `mono text-[9px] font-bold px-2 py-0.5 rounded-full border ${driverTone}`; }
  const sDrvMeta = document.getElementById("stripRoleDriverMeta");
  if (sDrvMeta) sDrvMeta.textContent = `${activeStore} • ${totalOk} ok, ${totalDmg} dmg • ₹${totalCash.toLocaleString("en-IN")}`;

  const cDrvBadge = document.getElementById("roleCardDriverBadge");
  if (cDrvBadge) { cDrvBadge.textContent = driverStatus; cDrvBadge.className = `mono text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${driverTone}`; }
  const cDrvTarget = document.getElementById("roleCardDriverTarget");
  if (cDrvTarget) cDrvTarget.textContent = `Target Store: ${activeStore}`;
  const cDrvBags = document.getElementById("roleCardDriverBags");
  if (cDrvBags) cDrvBags.textContent = `${totalOk} ok / ${totalDmg} dmg`;
  const cDrvCash = document.getElementById("roleCardDriverCash");
  if (cDrvCash) cDrvCash.textContent = `₹${totalCash.toLocaleString("en-IN")}`;
  const cDrvBarge = document.getElementById("roleCardDriverBarge");
  if (cDrvBarge) cDrvBarge.textContent = `Barge-Ins: ${interruptionCount}`;

  // Role 2: Gemini AI Agent
  const sAgtBadge = document.getElementById("stripRoleAgentBadge");
  if (sAgtBadge) sAgtBadge.textContent = currentAgentBadge;
  const sAgtMeta = document.getElementById("stripRoleAgentMeta");
  if (sAgtMeta) sAgtMeta.textContent = `${toolCallCount} tool calls • ${highlightedPolicyIds.size} SOPs grounded`;

  const cAgtBadge = document.getElementById("roleCardAgentBadge");
  if (cAgtBadge) cAgtBadge.textContent = currentAgentBadge;
  const cAgtTask = document.getElementById("roleCardAgentTask");
  if (cAgtTask) cAgtTask.textContent = currentAgentTask;
  const cAgtTools = document.getElementById("roleCardAgentTools");
  if (cAgtTools) cAgtTools.textContent = `${toolCallCount} calls`;
  const cAgtSops = document.getElementById("roleCardAgentSops");
  if (cAgtSops) cAgtSops.textContent = `${highlightedPolicyIds.size} / ${Math.max(4, cachedPolicies.length)}`;
  const cAgtLang = document.getElementById("roleCardAgentLang");
  if (cAgtLang) cAgtLang.textContent = `Lang: ${currentAgentLang}`;

  // Role 3: Area Manager (Priya HITL)
  const mgrStatus = pendingA > 0 ? `${pendingA} PENDING` : takeOverA > 0 ? "LIVE HANDOFF" : approvedA > 0 ? "APPROVED" : "CLEAR";
  const mgrTone = pendingA > 0
    ? "bg-amber-500/25 text-amber-200 border-amber-400/50 animate-pulse"
    : takeOverA > 0
    ? "bg-cyan-500/25 text-cyan-200 border-cyan-400/45"
    : "bg-emerald-500/20 text-emerald-200 border-emerald-400/35";
  const sMgrBadge = document.getElementById("stripRoleManagerBadge");
  if (sMgrBadge) { sMgrBadge.textContent = mgrStatus; sMgrBadge.className = `mono text-[9px] font-bold px-2 py-0.5 rounded-full border ${mgrTone}`; }
  const sMgrMeta = document.getElementById("stripRoleManagerMeta");
  if (sMgrMeta) sMgrMeta.textContent = `${pendingA} pending • ${approvedA} approved • ${takeOverA} handoffs`;

  const cMgrBadge = document.getElementById("roleCardManagerBadge");
  if (cMgrBadge) { cMgrBadge.textContent = mgrStatus; cMgrBadge.className = `mono text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${mgrTone}`; }
  const cMgrCounts = document.getElementById("roleCardManagerCounts");
  if (cMgrCounts) cMgrCounts.textContent = `${pendingA} / ${approvedA}`;
  const cMgrOther = document.getElementById("roleCardManagerOther");
  if (cMgrOther) cMgrOther.textContent = `${rejectedA} / ${takeOverA}`;
  const cMgrProofs = document.getElementById("roleCardManagerProofs");
  if (cMgrProofs) cMgrProofs.textContent = `Vision Proofs: ${proofCount}`;

  // Role 4: Tally / SAP ERP & WhatsApp Ops
  const erpStatus = pendingA > 0 ? "PENDING HITL" : ledger.length > 0 ? "AUTO-SYNCED" : "READY";
  const erpTone = pendingA > 0
    ? "bg-amber-500/20 text-amber-200 border-amber-400/40"
    : "bg-emerald-500/20 text-emerald-200 border-emerald-400/35";
  const sErpBadge = document.getElementById("stripRoleErpBadge");
  if (sErpBadge) { sErpBadge.textContent = erpStatus; sErpBadge.className = `mono text-[9px] font-bold px-2 py-0.5 rounded-full border ${erpTone}`; }
  const sErpMeta = document.getElementById("stripRoleErpMeta");
  if (sErpMeta) sErpMeta.textContent = `${settledCount}/${customers.length} settled • ${receipts.length} WA receipts`;

  const cErpBadge = document.getElementById("roleCardErpBadge");
  if (cErpBadge) { cErpBadge.textContent = erpStatus; cErpBadge.className = `mono text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${erpTone}`; }
  const cErpSettled = document.getElementById("roleCardErpSettled");
  if (cErpSettled) cErpSettled.textContent = `${settledCount} / ${customers.length}`;
  const cErpReceipts = document.getElementById("roleCardErpReceipts");
  if (cErpReceipts) cErpReceipts.textContent = String(receipts.length);
  const cErpDue = document.getElementById("roleCardErpDue");
  if (cErpDue) cErpDue.textContent = `Balance Due: ₹${totalDue.toLocaleString("en-IN")}`;

  // Full Role Board: Store & Route Ownership Table
  const matrixBody = document.getElementById("roleStoreMatrixBody");
  if (matrixBody) {
    matrixBody.innerHTML = customers
      .map((c) => {
        const custPending = approvals.some((a) => a.customer_id === c.customer_id && a.status === "PENDING");
        const isSettled = Number(c.balance_due) === 0;
        const owner = isSettled
          ? "🧾 Tally ERP & WhatsApp (Completed)"
          : custPending
          ? "👩‍💼 Manager Priya (Awaiting 1-Tap Approval)"
          : "🚚 Field Driver (Delivery / Collection)";
        const stBadge = isSettled
          ? "bg-emerald-500/20 text-emerald-200 border-emerald-400/40"
          : custPending
          ? "bg-amber-500/20 text-amber-200 border-amber-400/40"
          : "bg-cyan-500/15 text-cyan-200 border-cyan-400/35";
        return `
          <tr class="hover:bg-white/5 transition">
            <td class="py-2.5 pr-3">
              <div class="font-bold text-white">${escapeHtml(c.name)}</div>
              <div class="mono text-[10px] text-cyan-300/80">${c.pending_invoice_id} &bull; ${c.customer_id}</div>
            </td>
            <td class="py-2.5 pr-3 text-slate-300">
              <div>${escapeHtml(c.route)}</div>
              <div class="text-[10px] text-slate-400">${escapeHtml(c.location)}</div>
            </td>
            <td class="py-2.5 pr-3 mono text-slate-200">${c.expected_bags} bags</td>
            <td class="py-2.5 pr-3 mono">
              <div class="text-white">₹${Number(c.invoice_amount).toLocaleString("en-IN")}</div>
              <div class="text-[10px] ${isSettled ? "text-emerald-400" : "text-amber-300"}">Due: ₹${Number(c.balance_due).toLocaleString("en-IN")}</div>
            </td>
            <td class="py-2.5 pr-3 text-slate-200 font-medium">${owner}</td>
            <td class="py-2.5">
              <span class="mono text-[10px] font-bold px-2.5 py-0.5 rounded-full border ${stBadge}">${c.status}</span>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  // Highlight active wired flow nodes & animate connecting wires
  const activeNodeIndex = pendingA > 0 ? 3 : ledger.length > 0 && currentAgentBadge.includes("SETTLED") ? 4 : callActive ? 2 : 1;
  for (let idx = 1; idx <= 4; idx++) {
    const opsNode = document.getElementById(`opsFlowNode${idx}`);
    const boardNode = document.getElementById(`boardFlowNode${idx}`);
    [opsNode, boardNode].forEach((node) => {
      if (!node) return;
      node.classList.remove("agent-node-active", "agent-node-emerald", "agent-node-amber");
      if (idx === 3 && pendingA > 0) node.classList.add("agent-node-amber");
      else if (idx === 4 && settledCount > 0 && pendingA === 0) node.classList.add("agent-node-emerald");
      else if (idx === activeNodeIndex) node.classList.add("agent-node-active");
    });
  }
  for (let w = 1; w <= 3; w++) {
    const opsW = document.getElementById(`opsWire${w}`);
    const brdW = document.getElementById(`boardWire${w}`);
    [opsW, brdW].forEach((wire) => {
      if (!wire) return;
      const fast = callActive || pendingA > 0 || ledger.length > 0;
      wire.setAttribute("class", fast ? "wire-line-fast" : "wire-line");
    });
  }

  renderHybridCharts(state);
}

// --- HYBRID ANALYTICS CHARTS (PIE CHART + CASH BAR GRAPH + AGENT LATENCY GRAPH) ---
function renderHybridCharts(state) {
  renderPieChart("opsPieChart", "opsPieLegend", state);
  renderPieChart("boardPieChart", "boardPieLegend", state);
  renderCashBarGraph("opsCashChart", state);
  renderCashBarGraph("boardCashChart", state);
  renderAgentLatencyGraph("opsAgentGraph");
  renderAgentLatencyGraph("boardAgentGraph");
}

function renderPieChart(canvasId, legendId, state) {
  const canvas = document.getElementById(canvasId);
  const legendEl = document.getElementById(legendId);
  if (!canvas || !legendEl) return;

  const customers = state.customers || [];
  const approvals = state.approvals || [];
  const ledger = state.ledger || [];

  const settled = customers.filter((c) => Number(c.balance_due) === 0).length;
  const pendingHitl = approvals.filter((a) => a.status === "PENDING").length;
  const damagedCount = ledger.reduce((sum, r) => sum + Number(r.damaged_qty || 0), 0);
  const openRoutes = Math.max(0, customers.length - settled - pendingHitl);

  const pal = getThemePalette();
  const slices = [
    { label: "Settled Invoices", value: settled, color: pal.primary },
    { label: "Pending HITL", value: pendingHitl, color: pal.tertiary },
    { label: "Damaged Bags", value: damagedCount, color: pal.danger },
    { label: "Open Routes", value: openRoutes, color: pal.secondary },
  ];

  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const rOuter = Math.min(w, h) * 0.44;
  const rInner = rOuter * 0.58;

  ctx.clearRect(0, 0, w, h);
  const pieHits = [];
  let angle = -Math.PI / 2;
  slices.forEach((s) => {
    if (s.value <= 0) return;
    const sweep = (s.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, rOuter, angle, angle + sweep);
    ctx.arc(cx, cy, rInner, angle + sweep, angle, true);
    ctx.closePath();
    ctx.fillStyle = s.color;
    ctx.fill();
    ctx.strokeStyle = "rgba(4, 7, 17, 0.85)";
    ctx.lineWidth = 2;
    ctx.stroke();
    pieHits.push({ start: angle, end: angle + sweep, label: s.label, value: s.value, pct: Math.round((s.value / total) * 100), color: s.color });
    angle += sweep;
  });
  chartHitRegions[canvasId] = { type: "pie", cx, cy, rInner, rOuter, items: pieHits };

  const pct = customers.length ? Math.round((settled / customers.length) * 100) : 0;
  ctx.fillStyle = "#ffffff";
  ctx.font = "800 18px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(`${pct}%`, cx, cy - 6);
  ctx.fillStyle = "#94a3b8";
  ctx.font = "600 9px Inter, sans-serif";
  ctx.fillText("SETTLED", cx, cy + 12);

  legendEl.innerHTML = slices
    .map(
      (s) => `
      <div class="flex items-center justify-between gap-2">
        <span class="flex items-center gap-1.5 text-slate-200 truncate">
          <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${s.color}"></span>
          <span>${s.label}</span>
        </span>
        <span class="mono font-bold text-white">${s.value}</span>
      </div>`
    )
    .join("");
}

function renderCashBarGraph(canvasId, state) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const customers = state.customers || [];
  if (customers.length === 0) return;

  const ledger = state.ledger || [];
  const maxVal = Math.max(25000, ...customers.map((c) => Number(c.invoice_amount || 0)));
  const padL = 12;
  const padR = 12;
  const padB = 24;
  const padT = 14;
  const chartH = h - padT - padB;
  const groupW = (w - padL - padR) / customers.length;

  // Subtle horizontal grid lines
  ctx.strokeStyle = "rgba(148, 163, 184, 0.12)";
  ctx.lineWidth = 1;
  [0.25, 0.5, 0.75, 1].forEach((f) => {
    const gy = padT + chartH * (1 - f);
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(w - padR, gy);
    ctx.stroke();
  });

  const barHits = [];
  customers.forEach((c, idx) => {
    const target = Number(c.invoice_amount || 0);
    const collected = ledger
      .filter((r) => r.customer_id === c.customer_id)
      .reduce((s, r) => s + Number(r.cash_received || 0), 0);

    const xCenter = padL + idx * groupW + groupW / 2;
    const barW = Math.min(24, groupW * 0.28);

    const pal = getThemePalette();
    // Target Bar
    const tH = Math.max(4, (target / maxVal) * chartH);
    ctx.fillStyle = pal.barTarget;
    ctx.beginPath();
    ctx.roundRect(xCenter - barW - 2, padT + chartH - tH, barW, tH, 4);
    ctx.fill();

    // Collected Bar
    const cH = Math.max(3, (collected / maxVal) * chartH);
    const grad = ctx.createLinearGradient(0, padT + chartH - cH, 0, padT + chartH);
    grad.addColorStop(0, pal.secondary);
    grad.addColorStop(1, pal.primary);
    ctx.fillStyle = collected > 0 ? grad : "rgba(148, 163, 184, 0.18)";
    ctx.beginPath();
    ctx.roundRect(xCenter + 2, padT + chartH - cH, barW, cH, 4);
    ctx.fill();

    barHits.push({ x1: padL + idx * groupW, x2: padL + (idx + 1) * groupW, name: c.name, target, collected });

    // Store short label
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "600 10px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(c.name.split(" ")[0], xCenter, h - 8);
  });
  chartHitRegions[canvasId] = { type: "bar", items: barHits };
}

function initChartTooltips() {
  const tip = document.getElementById("chartTooltip");
  if (!tip) return;
  ["opsPieChart", "boardPieChart", "opsCashChart", "boardCashChart"].forEach((id) => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    canvas.addEventListener("mousemove", (e) => {
      const reg = chartHitRegions[id];
      if (!reg) return;
      const rect = canvas.getBoundingClientRect();
      const sx = (e.clientX - rect.left) * (canvas.width / rect.width);
      const sy = (e.clientY - rect.top) * (canvas.height / rect.height);
      let html = "";
      if (reg.type === "pie") {
        const dx = sx - reg.cx;
        const dy = sy - reg.cy;
        const dist = Math.hypot(dx, dy);
        if (dist >= reg.rInner && dist <= reg.rOuter) {
          let ang = Math.atan2(dy, dx);
          if (ang < -Math.PI / 2) ang += Math.PI * 2;
          const hit = reg.items.find((it) => ang >= it.start && ang <= it.end);
          if (hit) html = `<strong style="color:${hit.color}">${hit.label}</strong>: ${hit.value} (${hit.pct}%)`;
        }
      } else if (reg.type === "bar") {
        const hit = reg.items.find((it) => sx >= it.x1 && sx <= it.x2);
        if (hit) html = `<strong>${escapeHtml(hit.name)}</strong><br/>Target: ₹${hit.target.toLocaleString("en-IN")} &bull; Collected: <span class="text-emerald-300">₹${hit.collected.toLocaleString("en-IN")}</span>`;
      }
      if (html) {
        tip.innerHTML = html;
        tip.style.left = `${e.clientX + 12}px`;
        tip.style.top = `${e.clientY - 28}px`;
        tip.classList.remove("hidden");
      } else {
        tip.classList.add("hidden");
      }
    });
    canvas.addEventListener("mouseleave", () => tip.classList.add("hidden"));
  });
}

function renderAgentLatencyGraph(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const pts = latencyHistory.length > 0 ? latencyHistory : [380, 410, 340, 360];
  const padL = 14;
  const padR = 14;
  const padT = 18;
  const padB = 24;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;
  const maxMs = Math.max(800, ...pts);

  // Grid lines
  ctx.strokeStyle = "rgba(148, 163, 184, 0.12)";
  ctx.lineWidth = 1;
  [0.33, 0.66, 1].forEach((f) => {
    const gy = padT + chartH * (1 - f);
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(w - padR, gy);
    ctx.stroke();
  });

  const coords = pts.map((v, i) => ({
    x: padL + (pts.length === 1 ? chartW / 2 : (i / (pts.length - 1)) * chartW),
    y: padT + chartH - (v / maxMs) * chartH,
    v,
  }));

  const pal = getThemePalette();
  // Gradient fill area
  const grad = ctx.createLinearGradient(0, padT, 0, padT + chartH);
  grad.addColorStop(0, pal.areaFillTop);
  grad.addColorStop(1, "rgba(16, 185, 129, 0.02)");

  ctx.beginPath();
  ctx.moveTo(coords[0].x, padT + chartH);
  coords.forEach((p) => ctx.lineTo(p.x, p.y));
  ctx.lineTo(coords[coords.length - 1].x, padT + chartH);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Stroke line
  ctx.beginPath();
  coords.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
  ctx.strokeStyle = latencyHistory.length > 0 ? pal.primary : "rgba(148, 163, 184, 0.45)";
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // Dots + latest value label
  coords.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = latencyHistory.length > 0 ? pal.secondary : "#64748b";
    ctx.fill();
  });

  ctx.fillStyle = latencyHistory.length > 0 ? pal.secondary : "#94a3b8";
  ctx.font = "700 10px JetBrains Mono, monospace";
  ctx.textAlign = "left";
  const label = latencyHistory.length > 0
    ? `Latest TTFA: ${pts[pts.length - 1]}ms • Tool Calls: ${toolCallCount}`
    : `Baseline Target (<450ms) • Waiting for live turns`;
  ctx.fillText(label, padL, h - 7);
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
  renderAgentLatencyGraph("opsAgentGraph");
  renderAgentLatencyGraph("boardAgentGraph");
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
    ctx.fillStyle = v < 600 ? "#34d399" : v < 900 ? "#38bdf8" : "#fbbf24";
    ctx.fillRect(i * (bw + 1) + 1, h - bh, bw, bh);
  });
}

// --- LIVE MULTIMODAL VISION PROOF-OF-DELIVERY ---
function getActiveStoreName() {
  const sel = document.getElementById("activeStoreSelect");
  return sel ? sel.value : "Krishna Hardware";
}

function syncActiveStoreDropdown(storeName) {
  const sel = document.getElementById("activeStoreSelect");
  if (!sel || !storeName) return;
  for (const opt of sel.options) {
    if (opt.value.toLowerCase() === storeName.toLowerCase()) {
      sel.value = opt.value;
      updateRouteRadarMap(cachedErpState);
      return;
    }
  }
}

async function toggleLiveCamera() {
  const btn = document.getElementById("cameraToggleBtn");
  const video = document.getElementById("cameraPreview");
  const frame = document.getElementById("visionScannerFrame");
  const badge = document.getElementById("visionStatusBadge");

  if (cameraActive) {
    cameraActive = false;
    clearInterval(cameraInterval);
    if (cameraStream) cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
    video.classList.add("hidden");
    frame?.classList.add("hidden");
    btn.textContent = "📷 Live Camera";
    badge.textContent = "Ready";
    return;
  }

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 270 } });
    video.srcObject = cameraStream;
    video.classList.remove("hidden");
    frame?.classList.remove("hidden");
    document.getElementById("proofThumbPreview").classList.add("hidden");
    cameraActive = true;
    btn.textContent = "⏹ Stop Camera";
    const storeName = getActiveStoreName();
    badge.textContent = `Streaming • ${storeName}`;
    setAgentPipeline(4, "VISION STREAM", `Analyzing live camera frames for ${storeName}...`, "cyan");
    pushAgentAction("CAMERA ACTIVE", `Streaming multimodal frames for ${storeName}`, "cyan");

    const snapAndSend = async (includePrompt) => {
      if (!video.videoWidth) return;
      const c = document.createElement("canvas");
      c.width = 480;
      c.height = 270;
      c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
      const dataUrl = c.toDataURL("image/jpeg", 0.72);
      const currentStore = getActiveStoreName();
      await dispatchProofFrame(
        dataUrl,
        `Live Camera Proof (${currentStore})`,
        includePrompt ? `Yeh dekho ${currentStore} pe live camera dikha raha hoon — check karo kitne bags damaged hain aur ${currentStore} ke naam se log karo!` : null,
        currentStore
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
  const wsReady = await waitForWsReady(650);
  const storeName = getActiveStoreName();
  const dataUrl = generateSampleDamageProofImage(storeName);
  const img = document.getElementById("proofThumbPreview");
  img.src = dataUrl;
  img.classList.remove("hidden");
  document.getElementById("visionScannerFrame")?.classList.remove("hidden");
  document.getElementById("cameraPreview").classList.add("hidden");
  document.getElementById("visionStatusBadge").textContent = `2 Torn Bags • ${storeName}`;
  playSpatialChime("tool");
  showGlassToast("👁️ Vision Proof Captured", `2 torn bags detected for ${storeName} — click thumbnail to zoom.`, "amber");

  setAgentPipeline(4, "VISION INSPECT", `Gemini Vision detected 2 torn bags at ${storeName} — attaching to HITL card...`, "amber");
  pushAgentAction("VISION PROOF", `2 torn bags verified (96% conf) for ${storeName}`, "amber");

  const dispatchedViaWs = await dispatchProofFrame(
    dataUrl,
    `2 Torn Cement Bags at ${storeName}`,
    `Yeh dekho ${storeName} se photo bhej diya hai — ${storeName} par 2 cement bags phate hue hain. Verify karke ${storeName} ke naam se Priya ma'am ko bhej do!`,
    storeName,
    wsReady
  );

  if (!dispatchedViaWs) {
    logToolCall("log_damaged_bags_report", { customer_name: storeName, damaged_bags: 2, visual_proof: "verified" }, "ESCALATED", 260);
    updateFrontlineHud({
      intent: "VISUAL_DAMAGE_VERIFIED",
      language: "Hinglish (HI+EN)",
      sentiment: "CONCERNED",
      coach_tip: `2 torn bags verified for ${storeName} & attached directly to Priya Sharma's 1-Tap Approval Card (SOP-5.1)!`,
      suggested_phrase: `Uncle, ${storeName} ke 2 damaged bags ki photo AI ne verify karke Priya ma'am ko bhej di hai — ab turant approval aa jayega.`,
    });
    speakDemoVoice(
      `Haan Raju bhai, camera photo mein ${storeName} ke 2 torn cement bags clear dikh rahe hain! Maine yeh visual proof seedha ${storeName} ke naam se Priya ma'am ke approval card par attach kar diya hai.`,
      310
    );
  }
}

async function dispatchProofFrame(dataUrl, caption, prompt, customerName, wsReadyOverride = null) {
  const store = customerName || getActiveStoreName();
  const canUseWs =
    wsReadyOverride !== null
      ? wsReadyOverride
      : Boolean((liveReady || wsWorkflowReady) && ws && ws.readyState === WebSocket.OPEN);

  if (canUseWs && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "video_frame",
      data_url: dataUrl,
      caption,
      prompt,
      customer_name: store,
      damaged_bags: 2,
      auto_create_approval: true,
    }));
    return true;
  }

  const res = await fetch("/api/proof-photo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data_url: dataUrl,
      caption,
      customer_name: store,
      damaged_bags: 2,
      auto_create_approval: true,
    }),
  }).then((r) => r.json());
  renderErpState(res.state);
  return false;
}

function generateSampleDamageProofImage(storeName = "Krishna Hardware") {
  const c = document.createElement("canvas");
  c.width = 480;
  c.height = 240;
  const ctx = c.getContext("2d");

  const grad = ctx.createLinearGradient(0, 0, 480, 240);
  grad.addColorStop(0, "#1e293b");
  grad.addColorStop(1, "#0f172a");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 480, 240);

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

    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x + 40, y + 60);
    ctx.lineTo(x + 75, y + 82);
    ctx.lineTo(x + 115, y + 70);
    ctx.lineTo(x + 135, y + 96);
    ctx.stroke();

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

  ctx.fillStyle = "rgba(2, 6, 23, 0.82)";
  ctx.fillRect(0, 206, 480, 34);
  ctx.fillStyle = "#34d399";
  ctx.font = "bold 11px monospace";
  ctx.fillText(`DELIVEREX CAM • ${storeName.toUpperCase()} • ${new Date().toLocaleTimeString()}`, 14, 227);

  return c.toDataURL("image/jpeg", 0.85);
}

// --- FRONTLINE UNDERSTANDING & COACH HUD ---
function updateFrontlineHud(g) {
  if (!g) return;
  document.getElementById("hudIntent").textContent = g.intent || "DELIVERY_UPDATE";
  currentAgentLang = g.language || "Hinglish (HI+EN)";
  document.getElementById("hudLanguage").textContent = currentAgentLang;
  document.getElementById("langBadge").textContent = currentAgentLang;
  document.getElementById("hudCoachTip").textContent = g.coach_tip || "";
  updateRoleStatusDashboard();

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
    CALM: "bg-emerald-500/20 text-emerald-200 border-emerald-400/35",
    POSITIVE: "bg-emerald-500/25 text-emerald-200 border-emerald-400/45",
    RESOLVED: "bg-emerald-500/30 text-emerald-100 border-emerald-300/50",
    CONCERNED: "bg-amber-500/25 text-amber-200 border-amber-400/45",
    FRUSTRATED: "bg-rose-500/25 text-rose-200 border-rose-400/50 animate-pulse",
  };
  badge.className = `text-[10px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap ${map[s] || map.CALM}`;
}

function setSpeakingIndicator(text, tone) {
  const el = document.getElementById("speakingIndicator");
  const styles = {
    emerald: "bg-emerald-500/20 text-emerald-200 border border-emerald-400/45",
    amber: "bg-amber-500/20 text-amber-200 border border-amber-400/45",
    cyan: "bg-cyan-500/20 text-cyan-200 border border-cyan-400/45",
    slate: "bg-white/10 text-slate-300 border border-white/10",
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
  clearAutopilotTimers();
  stopLiveCall();
  if (cameraActive) toggleLiveCamera();
  interruptionCount = 0;
  toolCallCount = 0;
  latencyHistory = [];
  renderLatencySparkline();
  highlightedPolicyIds.clear();
  document.getElementById("bargeInBadge").textContent = "0";
  document.getElementById("latencyBadge").textContent = "-- ms";
  document.getElementById("proofThumbPreview").classList.add("hidden");
  document.getElementById("visionScannerFrame")?.classList.add("hidden");
  document.getElementById("visionStatusBadge").textContent = "Ready";
  updateFrontlineHud({
    intent: "AWAITING_SPEECH",
    language: "Hinglish / Tanglish",
    sentiment: "CALM",
    coach_tip: "Ready — speak naturally in Hinglish or Tanglish. Show damaged bags via camera for instant verification.",
    suggested_phrase: "",
  });
  setAgentPipeline(0, "STANDBY", "Waiting for driver speech, camera frame, or field trigger...", "cyan");
  setVoiceLoopStage("standby", "Voice catcher armed — ready to catch speech, run agents & ask back.");
  document.getElementById("agentActionFeed").innerHTML = `
    <div class="flex items-center gap-2 text-slate-400">
      <span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
      <span>Gemini Live Brain armed — ready for real-time Hinglish, Tanglish &amp; Vision.</span>
    </div>
  `;
  document.getElementById("transcriptFeed").innerHTML = `<div class="text-slate-400 text-center mt-10 text-xs">Demo reset! Start a Live Call, click <strong class="text-white">Step 1</strong>, or hit <strong class="text-cyan-300">▶ Auto-Run Agent</strong>.</div>`;
  document.getElementById("toolLog").innerHTML = `<div class="text-slate-400 font-sans text-xs p-2">Waiting for spoken intent to trigger ERP actions...</div>`;
  waUnreadCount = 0;
  waInitialized = false;
  seenWaMsgIds.clear();
  waSending = false;
  const waBadge = document.getElementById("waUnreadBadge");
  if (waBadge) {
    waBadge.textContent = "0";
    waBadge.classList.add("hidden");
  }
  const waIn = document.getElementById("waChatInput");
  if (waIn) waIn.value = "";
  refreshPoliciesHighlight();

  const resp = await fetch("/api/reset", { method: "POST", headers: getOwnerHeaders() });
  if (resp.status === 401) {
    openOwnerPinModal(() => resetDemo());
    return;
  }
  const res = await resp.json();
  if (res.state) renderErpState(res.state);
}

// --- 2026 3D FLUID PLASMA ORB + LIQUID-SILK VOICE CATCHER RIBBONS ---
function drawWaveformLoop() {
  const canvas = document.getElementById("waveCanvas");
  const plasmaCanvas = document.getElementById("plasmaOrbCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const pCtx = plasmaCanvas ? plasmaCanvas.getContext("2d") : null;
  let phase = 0;
  let smoothEnergy = 0.22;
  const bars = 44;
  const peakCaps = new Array(bars).fill(6);

  function frame() {
    const w = canvas.width;
    const h = canvas.height;
    const pal = getThemePalette();
    ctx.clearRect(0, 0, w, h);

    phase += callActive ? 0.14 : 0.065;
    const rawTarget = callActive ? Math.max(0.38, currentEnergy) : 0.24;
    smoothEnergy += (rawTarget - smoothEnergy) * 0.18;
    const targetAmp = smoothEnergy;
    document.documentElement.style.setProperty("--audio-energy", targetAmp.toFixed(3));

    const dbEl = document.getElementById("voiceDbReadout");
    if (dbEl) {
      const db = Math.round(-44 + Math.min(1, callActive ? Math.max(currentEnergy, 0.2) : 0.08) * 38);
      dbEl.textContent = callActive ? `${db} dBFS • LIVE` : `${db} dBFS • READY`;
    }

    // Soft radial center glow inside Acoustic Catcher
    const bgGlow = ctx.createRadialGradient(w / 2, h / 2, 8, w / 2, h / 2, w * 0.52);
    bgGlow.addColorStop(0, pal.primary + (callActive ? "2e" : "18"));
    bgGlow.addColorStop(1, "transparent");
    ctx.fillStyle = bgGlow;
    ctx.fillRect(0, 0, w, h);

    // Subtle acoustic reference lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.055)";
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75].forEach((f) => {
      ctx.beginPath();
      ctx.moveTo(0, h * f);
      ctx.lineTo(w, h * f);
      ctx.stroke();
    });

    // Background thin glowing spectrum bars
    const barW = w / bars;
    for (let i = 0; i < bars; i++) {
      const distCenter = 1 - Math.abs((i - bars / 2) / (bars / 2));
      const harmonic =
        0.58 * Math.abs(Math.sin(phase * 1.1 + i * 0.34)) +
        0.42 * Math.abs(Math.cos(phase * 1.45 - i * 0.25));
      const barH = Math.max(8, harmonic * h * 0.88 * targetAmp * (0.35 + 0.65 * distCenter));
      if (barH > peakCaps[i]) peakCaps[i] = barH;
      else peakCaps[i] = Math.max(barH, peakCaps[i] - 0.45);

      const x = i * barW + barW * 0.28;
      const bw = Math.max(2, barW * 0.44);
      const y = (h - barH) / 2;

      const grad = ctx.createLinearGradient(x, y, x, y + barH);
      grad.addColorStop(0, pal.secondary + (callActive ? "aa" : "55"));
      grad.addColorStop(0.5, pal.primary + (callActive ? "88" : "44"));
      grad.addColorStop(1, pal.tertiary + (callActive ? "aa" : "55"));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(x, y, bw, barH, 3);
      ctx.fill();

      const capY = (h - peakCaps[i]) / 2 - 2;
      ctx.fillStyle = callActive ? pal.secondary : pal.primary + "88";
      ctx.fillRect(x, Math.max(2, capY), bw, 1.5);
    }

    // 3 Layered 2026 Liquid-Silk Harmonic Wave Ribbons (Siri/Studio style)
    const stateAccent =
      currentOrbState === "bargein"
        ? "#fb7185"
        : currentOrbState === "asking"
        ? "#34d399"
        : currentOrbState === "catching"
        ? "#38bdf8"
        : pal.primary;

    const silkWaves = [
      { freq: 2.2, speed: 1.35, ampScale: 0.42, color: stateAccent, alpha: 0.9, fillAlpha: 0.2, width: 2.2, offset: 0 },
      { freq: 3.1, speed: -1.1, ampScale: 0.32, color: pal.secondary, alpha: 0.78, fillAlpha: 0.12, width: 1.7, offset: 1.6 },
      { freq: 4.3, speed: 1.8, ampScale: 0.24, color: "#ffffff", alpha: callActive ? 0.85 : 0.48, fillAlpha: 0.0, width: 1.3, offset: 3.1 },
    ];

    silkWaves.forEach((sw) => {
      ctx.save();
      ctx.beginPath();
      for (let px = 0; px <= w; px += 3) {
        const norm = (px / w) * Math.PI * 2;
        const env = Math.pow(Math.sin((px / w) * Math.PI), 0.75);
        const yOff =
          (Math.sin(norm * sw.freq + phase * sw.speed + sw.offset) * 0.7 +
            Math.cos(norm * (sw.freq * 1.6) - phase * sw.speed * 0.8) * 0.3) *
          (h * sw.ampScale * targetAmp * env);
        const py = h / 2 + yOff;
        if (px === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = sw.color;
      ctx.globalAlpha = sw.alpha;
      ctx.lineWidth = sw.width;
      ctx.shadowColor = sw.color;
      ctx.shadowBlur = callActive ? 12 : 6;
      ctx.stroke();

      if (sw.fillAlpha > 0) {
        ctx.lineTo(w, h / 2);
        ctx.lineTo(0, h / 2);
        ctx.closePath();
        const fGrad = ctx.createLinearGradient(0, 0, 0, h);
        fGrad.addColorStop(0, sw.color);
        fGrad.addColorStop(0.5, "transparent");
        fGrad.addColorStop(1, sw.color);
        ctx.fillStyle = fGrad;
        ctx.globalAlpha = sw.fillAlpha;
        ctx.fill();
      }
      ctx.restore();
    });

    // Floating luminous crest particles riding the center wave
    for (let p = 0; p < 6; p++) {
      const px = ((p / 5) * 0.76 + 0.12) * w;
      const norm = (px / w) * Math.PI * 2;
      const env = Math.pow(Math.sin((px / w) * Math.PI), 0.75);
      const py = h / 2 + Math.sin(norm * 2.2 + phase * 1.35) * (h * 0.42 * targetAmp * env);
      ctx.beginPath();
      ctx.arc(px, py, callActive ? 2.4 : 1.6, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.globalAlpha = callActive ? 0.9 : 0.45;
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // 2026 3D Fluid Plasma & State-Morphing Voice Orb
    if (pCtx && plasmaCanvas) {
      const pw = plasmaCanvas.width;
      const ph = plasmaCanvas.height;
      const cx = pw / 2;
      const cy = ph / 2;
      pCtx.clearRect(0, 0, pw, ph);

      // State-reactive color selection
      const c1 = currentOrbState === "bargein" ? "#fb7185" : currentOrbState === "asking" ? "#34d399" : currentOrbState === "catching" ? "#38bdf8" : pal.primary;
      const c2 = currentOrbState === "working" ? "#a78bfa" : pal.secondary;
      const c3 = pal.tertiary;

      // Ambient backlight aura
      const aura = pCtx.createRadialGradient(cx, cy, 18, cx, cy, 98);
      aura.addColorStop(0, c1 + "55");
      aura.addColorStop(0.55, c2 + "22");
      aura.addColorStop(1, "transparent");
      pCtx.fillStyle = aura;
      pCtx.fillRect(0, 0, pw, ph);

      // Outward acoustic ripple rings when asking/speaking or catching
      if (callActive || currentOrbState !== "standby") {
        for (let r = 0; r < 2; r++) {
          const prog = ((phase * 0.25 + r * 0.5) % 1);
          const rr = 42 + prog * 56;
          pCtx.beginPath();
          pCtx.arc(cx, cy, rr, 0, Math.PI * 2);
          pCtx.strokeStyle = c1;
          pCtx.globalAlpha = (1 - prog) * 0.48;
          pCtx.lineWidth = 1.6;
          pCtx.stroke();
        }
        pCtx.globalAlpha = 1;
      }

      // 3 Layered Morphing Plasma Blobs (Chromatic Aberration + Liquid Mercury Surface)
      const blobLayers = [
        { rad: 54, speed: 1.0, wobble: 6 + targetAmp * 16, col: c2, alpha: 0.35, offset: 0 },
        { rad: 48, speed: -1.3, wobble: 5 + targetAmp * 14, col: c1, alpha: 0.62, offset: 2.1 },
        { rad: 42, speed: 1.7, wobble: 4 + targetAmp * 11, col: c3, alpha: 0.85, offset: 4.2 },
      ];
      blobLayers.forEach((layer) => {
        pCtx.save();
        pCtx.beginPath();
        const pts = 48;
        for (let i = 0; i <= pts; i++) {
          const ang = (i / pts) * Math.PI * 2;
          const n1 = Math.sin(ang * 3 + phase * layer.speed + layer.offset);
          const n2 = Math.cos(ang * 5 - phase * layer.speed * 1.2);
          const rr = layer.rad + (n1 * 0.6 + n2 * 0.4) * layer.wobble;
          const x = cx + Math.cos(ang) * rr;
          const y = cy + Math.sin(ang) * rr;
          if (i === 0) pCtx.moveTo(x, y);
          else pCtx.lineTo(x, y);
        }
        pCtx.closePath();
        const bg = pCtx.createRadialGradient(cx - 14, cy - 16, 6, cx, cy, layer.rad + 14);
        bg.addColorStop(0, "#ffffff");
        bg.addColorStop(0.32, layer.col);
        bg.addColorStop(1, "rgba(6, 10, 22, 0.85)");
        pCtx.fillStyle = bg;
        pCtx.globalAlpha = layer.alpha;
        pCtx.fill();
        pCtx.lineWidth = 1.2;
        pCtx.strokeStyle = "rgba(255, 255, 255, 0.38)";
        pCtx.stroke();
        pCtx.restore();
      });

      // Fast-spinning 3D Geodesic Wireframe when Agents are Working (Cognition state)
      const polySides = currentOrbState === "working" ? 6 : 8;
      const polyRot = phase * (currentOrbState === "working" ? 1.8 : 0.35);
      pCtx.save();
      pCtx.translate(cx, cy);
      pCtx.rotate(polyRot);
      pCtx.beginPath();
      for (let k = 0; k <= polySides; k++) {
        const a = (k / polySides) * Math.PI * 2;
        const rx = Math.cos(a) * (66 + targetAmp * 10);
        const ry = Math.sin(a) * (54 + targetAmp * 8);
        if (k === 0) pCtx.moveTo(rx, ry);
        else pCtx.lineTo(rx, ry);
      }
      pCtx.strokeStyle = currentOrbState === "working" ? "#fde68a" : c1;
      pCtx.globalAlpha = currentOrbState === "working" ? 0.78 : 0.3;
      pCtx.lineWidth = 1.2;
      pCtx.stroke();
      pCtx.restore();

      // Outer 36-tick radial equalizer halo
      const ticks = 36;
      const baseR = 72;
      for (let t = 0; t < ticks; t++) {
        const ang = (t / ticks) * Math.PI * 2 + phase * 0.14;
        const mag = (0.3 + 0.7 * Math.abs(Math.sin(phase * 1.7 + t * 0.52))) * (callActive ? 18 * targetAmp + 4 : 5);
        pCtx.strokeStyle = t % 2 === 0 ? c1 : c2;
        pCtx.globalAlpha = callActive ? 0.9 : 0.42;
        pCtx.lineWidth = 2.2;
        pCtx.lineCap = "round";
        pCtx.beginPath();
        pCtx.moveTo(cx + Math.cos(ang) * baseR, cy + Math.sin(ang) * baseR);
        pCtx.lineTo(cx + Math.cos(ang) * (baseR + mag), cy + Math.sin(ang) * (baseR + mag));
        pCtx.stroke();
      }
      pCtx.globalAlpha = 1;
    }

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function renderGoLiveReadiness(report) {
  if (!report) return;
  const badge = document.getElementById("goLiveScoreBadge");
  const listEl = document.getElementById("goLiveChecksList");
  const summaryEl = document.getElementById("goLiveSummaryText");

  if (badge) {
    badge.textContent = `${report.score_pct}% • ${report.counts?.pass || 0} PASS / ${report.counts?.warn || 0} WARN`;
    badge.className = report.ready_for_production_go_live
      ? "mono text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-200 border border-emerald-400/40"
      : "mono text-xs font-bold px-3 py-1 rounded-full bg-amber-500/20 text-amber-200 border border-amber-400/40";
  }
  if (summaryEl) {
    summaryEl.textContent = report.ready_for_production_go_live
      ? "All production Go-Live checks passed."
      : report.ready_for_working_model
      ? "Working model healthy (0 FAIL). Address WARN items below before full public production launch."
      : "Critical failures detected — resolve FAIL items before Go-Live.";
  }
  if (listEl) {
    listEl.innerHTML = (report.checks || [])
      .map((c) => {
        const cls =
          c.status === "PASS"
            ? "bg-emerald-500/20 text-emerald-200 border-emerald-400/40"
            : c.status === "WARN"
            ? "bg-amber-500/20 text-amber-200 border-amber-400/40"
            : "bg-rose-500/20 text-rose-200 border-rose-400/40";
        return `
          <div class="subtile-4d p-3 rounded-2xl border-white/10">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-bold text-white">${escapeHtml(c.category)}</span>
              <span class="mono text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls}">${c.status}</span>
            </div>
            <p class="text-xs text-slate-200 mt-1">${escapeHtml(c.summary)}</p>
            ${c.remediation ? `<p class="text-[11px] text-amber-200/90 mt-1">Fix: ${escapeHtml(c.remediation)}</p>` : ""}
          </div>
        `;
      })
      .join("");
  }
}

async function refreshGoLiveCheck() {
  const res = await fetch("/api/go-live-check").then((r) => r.json());
  renderGoLiveReadiness(res);
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
