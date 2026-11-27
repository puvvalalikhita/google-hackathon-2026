package com.deliverex.live.ui

import android.app.Application
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.util.Base64
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.deliverex.live.audio.LiveAudioEngine
import com.deliverex.live.data.local.OfflineDemoEngine
import com.deliverex.live.data.local.ServerPreferences
import com.deliverex.live.data.model.ErpState
import com.deliverex.live.data.model.FrontlineGuidance
import com.deliverex.live.data.model.GoLiveCheckResponse
import com.deliverex.live.data.model.HealthResponse
import com.deliverex.live.data.model.PolicyItem
import com.deliverex.live.data.model.ReceiptItem
import com.deliverex.live.data.model.ToolLogEntry
import com.deliverex.live.data.model.TranscriptMessage
import com.deliverex.live.data.remote.DeliverExApiClient
import com.deliverex.live.data.remote.LiveCallWebSocketClient
import com.deliverex.live.data.remote.LiveWsEvent
import com.deliverex.live.data.remote.OwnerAuthRequiredException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonPrimitive
import java.io.ByteArrayOutputStream
import java.util.UUID

enum class LedgerFilter { ALL, SETTLED, PENDING }

data class RoiCalculation(
    val dailyCalls: Int = 250,
    val aiCostPerCall: Double = 2.20,
    val humanCostPerCall: Double = 30.0,
    val monthlySavingsInr: Long = ((30.0 - 2.20) * 250 * 30).toLong(),
    val roiMultiple: Double = 13.6
)

data class DeliverExUiState(
    val baseUrl: String = "",
    val themeKey: String = "gold",
    val driverName: String = "Raju Kumar",
    val activeStore: String = "Krishna Hardware",
    val backendConnected: Boolean = false,
    val isOfflineDemo: Boolean = true,
    val health: HealthResponse = HealthResponse(),
    val goLiveCheck: GoLiveCheckResponse? = null,
    val erpState: ErpState = ErpState(),
    val policies: List<PolicyItem> = emptyList(),
    val highlightedPolicyIds: Set<String> = emptySet(),
    val guidance: FrontlineGuidance = FrontlineGuidance(),
    val callActive: Boolean = false,
    val liveGeminiReady: Boolean = false,
    val callSeconds: Int = 0,
    val voiceEnergy: Float = 0.04f,
    val voiceStage: String = "STANDBY",
    val voiceStageDetail: String = "Tap Start Live Call for Hinglish / Tanglish voice & vision ops",
    val noiseFloorDb: Int = 42,
    val interruptionCount: Int = 0,
    val latencyHistory: List<Int> = listOf(295, 270, 310),
    val transcripts: List<TranscriptMessage> = emptyList(),
    val toolLogs: List<ToolLogEntry> = emptyList(),
    val latestReceipt: ReceiptItem? = null,
    val ledgerFilter: LedgerFilter = LedgerFilter.ALL,
    val ledgerQuery: String = "",
    val waRecording: Boolean = false,
    val waSending: Boolean = false,
    val roi: RoiCalculation = RoiCalculation(),
    val ownerAuthenticated: Boolean = false,
    val ownerAuthEnforced: Boolean = false,
    val ownerActor: String = "Priya Sharma",
    val showOwnerPinDialog: Boolean = false,
    val exportedTitle: String? = null,
    val exportedContent: String? = null,
    val userRole: String = "DRIVER", // DRIVER | MANAGER | DEMO
    val preferredLanguage: String = "Hinglish",
    val onboardingCompleted: Boolean = false,
    val showDemoControls: Boolean = false,
    val micMuted: Boolean = false,
    val availableUpdate: com.deliverex.live.update.AppUpdateInfo? = null,
    val updateDownloadProgress: Int? = null,
    val checkingUpdate: Boolean = false,
    val toastMessage: String? = null,
    val isRefreshing: Boolean = false
)

class DeliverExViewModel(application: Application) : AndroidViewModel(application) {
    private val prefs = ServerPreferences(application)
    private val offlineEngine = OfflineDemoEngine()
    private val apiClient = DeliverExApiClient(
        baseUrlProvider = { prefs.baseUrl },
        ownerTokenProvider = { prefs.ownerToken }
    )
    private var pendingOwnerAction: (() -> Unit)? = null
    private val wsClient = LiveCallWebSocketClient(apiClient.httpClient, apiClient.json)
    private val audioEngine = LiveAudioEngine(application)

    private val _uiState = MutableStateFlow(
        DeliverExUiState(
            baseUrl = prefs.baseUrl,
            themeKey = prefs.themeKey,
            driverName = prefs.driverName,
            activeStore = prefs.activeStore,
            userRole = prefs.userRole,
            preferredLanguage = prefs.preferredLanguage,
            onboardingCompleted = prefs.onboardingCompleted,
            showDemoControls = prefs.userRole == "DEMO",
            erpState = offlineEngine.snapshot(),
            policies = offlineEngine.policies
        )
    )
    val uiState: StateFlow<DeliverExUiState> = _uiState.asStateFlow()

    private var callTimerJob: Job? = null
    private var openStreamBubbleId: String? = null
    private var openStreamRole: String? = null

    init {
        com.deliverex.live.update.AppNotificationManager.ensureChannels(application)
        com.deliverex.live.update.AppUpdateManager.schedulePeriodicUpdateCheck(application)
        refreshFromServer()
        checkForAppUpdate(silent = true)
    }

    fun checkForAppUpdate(silent: Boolean = false) {
        viewModelScope.launch {
            if (!silent) _uiState.update { it.copy(checkingUpdate = true) }
            val info = com.deliverex.live.update.AppUpdateManager.fetchLatestVersion(prefs.baseUrl)
            if (info != null && com.deliverex.live.update.AppUpdateManager.isNewerVersion(info)) {
                _uiState.update {
                    it.copy(
                        availableUpdate = info,
                        checkingUpdate = false,
                        toastMessage = if (!silent) "🚀 Raju Bhai v${info.latestVersionName} update is available!" else it.toastMessage
                    )
                }
                val ctx = getApplication<Application>()
                if (!silent || com.deliverex.live.update.AppUpdateManager.lastNotifiedVersion(ctx) < info.latestVersionCode) {
                    com.deliverex.live.update.AppNotificationManager.notifyUpdateAvailable(
                        context = ctx,
                        versionName = info.latestVersionName,
                        releaseNotes = info.releaseNotes,
                        apkUrl = info.apkUrl
                    )
                    com.deliverex.live.update.AppUpdateManager.markVersionNotified(ctx, info.latestVersionCode)
                }
            } else {
                _uiState.update {
                    it.copy(
                        availableUpdate = null,
                        checkingUpdate = false,
                        toastMessage = if (!silent) "✅ Raju Bhai v${com.deliverex.live.BuildConfig.VERSION_NAME} is up to date!" else it.toastMessage
                    )
                }
            }
        }
    }

    fun downloadAndInstallUpdate(apkUrlOverride: String? = null) {
        val url = apkUrlOverride?.takeIf { it.isNotBlank() } ?: _uiState.value.availableUpdate?.apkUrl.orEmpty()
        if (url.isBlank()) {
            checkForAppUpdate(silent = false)
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(updateDownloadProgress = 1, toastMessage = "⬇️ Downloading Raju Bhai update...") }
            val result = com.deliverex.live.update.AppUpdateManager.downloadAndInstallApk(
                context = getApplication(),
                apkUrl = url,
                onProgress = { pct -> _uiState.update { it.copy(updateDownloadProgress = pct) } }
            )
            result.onSuccess {
                _uiState.update { it.copy(updateDownloadProgress = null, toastMessage = "📦 Opening installer for Raju Bhai update...") }
            }.onFailure { err ->
                _uiState.update { it.copy(updateDownloadProgress = null, toastMessage = "Update download failed: ${err.message}") }
            }
        }
    }

    fun sendTestNotification() {
        val ctx = getApplication<Application>()
        com.deliverex.live.update.AppNotificationManager.notifyOpsAlert(
            context = ctx,
            title = "🔔 Raju Bhai Alerts Active",
            message = "Push notifications & chime sound are working loud and clear!"
        )
        com.deliverex.live.update.AppNotificationManager.playInAppChime(ctx)
        _uiState.update { it.copy(toastMessage = "🔔 Test notification & chime sound played!") }
    }

    fun refreshFromServer() {
        viewModelScope.launch {
            _uiState.update { it.copy(isRefreshing = true) }
            if (prefs.offlineDemoMode) {
                applyOfflineSnapshot("Offline Preview Mode enabled")
                return@launch
            }

            runCatching {
                val health = apiClient.fetchHealth()
                val env = apiClient.fetchState()
                val goLive = runCatching { apiClient.fetchGoLiveCheck() }.getOrNull()
                val authSession = runCatching { apiClient.fetchAuthSession() }.getOrNull()
                listOf(health, env, goLive, authSession)
            }.onSuccess { results ->
                val health = results[0] as HealthResponse
                val env = results[1] as com.deliverex.live.data.model.StateEnvelope
                val goLive = results[2] as GoLiveCheckResponse?
                val authSession = results[3] as com.deliverex.live.data.model.AuthSessionResponse?
                _uiState.update {
                    it.copy(
                        backendConnected = true,
                        isOfflineDemo = false,
                        health = health,
                        erpState = env.state,
                        policies = env.policies,
                        goLiveCheck = goLive,
                        latestReceipt = env.state.receipts.firstOrNull(),
                        ownerAuthenticated = authSession?.tokenValid == true,
                        ownerAuthEnforced = authSession?.authEnforced ?: health.managerAuthEnforced,
                        ownerActor = authSession?.actor ?: "Priya Sharma",
                        isRefreshing = false
                    )
                }
            }.onFailure {
                applyOfflineSnapshot("Backend unreachable — running built-in Interactive Demo Engine")
            }
        }
    }

    private fun applyOfflineSnapshot(banner: String) {
        val snap = offlineEngine.snapshot()
        _uiState.update {
            it.copy(
                backendConnected = false,
                isOfflineDemo = true,
                erpState = snap,
                policies = offlineEngine.policies,
                latestReceipt = snap.receipts.firstOrNull(),
                isRefreshing = false,
                toastMessage = banner
            )
        }
    }

    fun updateServerSettings(newUrl: String, newDriverName: String, forceOffline: Boolean) {
        prefs.baseUrl = newUrl
        prefs.driverName = newDriverName
        prefs.offlineDemoMode = forceOffline
        _uiState.update {
            it.copy(
                baseUrl = prefs.baseUrl,
                driverName = prefs.driverName,
                isOfflineDemo = forceOffline
            )
        }
        refreshFromServer()
    }

    fun setTheme(themeKey: String) {
        prefs.themeKey = themeKey
        _uiState.update { it.copy(themeKey = themeKey) }
    }

    fun setActiveStore(storeName: String) {
        prefs.activeStore = storeName
        _uiState.update { it.copy(activeStore = storeName) }
    }

    fun toggleMarketNoise() {
        _uiState.update { state ->
            val nextDb = if (state.noiseFloorDb >= 70) 42 else 78
            state.copy(
                noiseFloorDb = nextDb,
                toastMessage = if (nextDb == 78) "78 dB Busy Mandi noise floor simulated (AEC/NS active)" else "Ambient noise floor normal (42 dB)"
            )
        }
    }

    fun toggleLiveCall(hasMicPermission: Boolean) {
        if (_uiState.value.callActive) {
            stopLiveCall()
        } else {
            startLiveCall(hasMicPermission)
        }
    }

    private fun startLiveCall(hasMicPermission: Boolean) {
        _uiState.update {
            it.copy(
                callActive = true,
                callSeconds = 0,
                voiceStage = "CONNECTING",
                voiceStageDetail = if (it.backendConnected) "Opening real-time bridge to DeliverEx Live..." else "Interactive Demo Call Active — tap Step 1–4 or speak/type!",
                transcripts = if (it.transcripts.isEmpty()) {
                    listOf(
                        TranscriptMessage(
                            id = UUID.randomUUID().toString(),
                            role = "system",
                            text = if (it.backendConnected) "Connected to DeliverEx Live Server (${it.baseUrl})" else "Offline Interactive Demo Call active — full SOP & ERP workflows ready!"
                        )
                    )
                } else it.transcripts
            )
        }

        callTimerJob?.cancel()
        callTimerJob = viewModelScope.launch {
            while (isActive) {
                delay(1000)
                _uiState.update { it.copy(callSeconds = it.callSeconds + 1) }
            }
        }

        if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
            wsClient.connect(_uiState.value.baseUrl) { event ->
                viewModelScope.launch { handleWsEvent(event, hasMicPermission) }
            }
        } else {
            _uiState.update {
                it.copy(
                    voiceStage = "DEMO READY",
                    voiceStageDetail = "Tap Guided Step 1 → Step 2 (Interrupt!) or send a Hinglish/Tanglish turn."
                )
            }
        }
    }

    fun stopLiveCall() {
        callTimerJob?.cancel()
        callTimerJob = null
        wsClient.disconnect()
        audioEngine.stopMicCapture()
        audioEngine.flushPlayback()
        openStreamBubbleId = null
        openStreamRole = null
        _uiState.update {
            it.copy(
                callActive = false,
                liveGeminiReady = false,
                micMuted = false,
                callSeconds = 0,
                voiceEnergy = 0.04f,
                voiceStage = "STANDBY",
                voiceStageDetail = "Call ended — ready for next route delivery check-in."
            )
        }
    }

    private fun handleWsEvent(event: LiveWsEvent, hasMicPermission: Boolean) {
        when (event) {
            is LiveWsEvent.Status -> {
                _uiState.update {
                    it.copy(
                        liveGeminiReady = event.connected,
                        voiceStage = if (event.connected) "LIVE LISTENING" else "WORKFLOW READY",
                        voiceStageDetail = event.message
                    )
                }
                if (event.connected && hasMicPermission) {
                    audioEngine.startMicCapture(
                        onAudioChunk = { b64, rms, speaking ->
                            if (_uiState.value.micMuted) return@startMicCapture
                            val energy = (rms * 18f).coerceIn(0.05f, 1f)
                            _uiState.update { s -> s.copy(voiceEnergy = energy) }
                            wsClient.sendAudioChunk(b64, speaking)
                        },
                        onError = { err ->
                            appendTranscript("system", err, true)
                        }
                    )
                }
            }

            is LiveWsEvent.AudioOut -> {
                val energy = audioEngine.playPcm24kBase64(event.base64Pcm24k)
                _uiState.update {
                    it.copy(
                        voiceEnergy = energy,
                        voiceStage = "AI SPEAKING",
                        voiceStageDetail = "Gemini Live speaking — interrupt anytime!"
                    )
                }
            }

            is LiveWsEvent.Latency -> {
                _uiState.update {
                    it.copy(latencyHistory = (it.latencyHistory + event.ttfaMs).takeLast(14))
                }
            }

            is LiveWsEvent.Interrupted -> {
                audioEngine.flushPlayback()
                openStreamBubbleId = null
                openStreamRole = null
                appendTranscript("barge_in", "⚡ Mid-Sentence Barge-In — AI Audio Flushed", true)
                _uiState.update {
                    it.copy(
                        interruptionCount = event.count,
                        voiceStage = "BARGE-IN",
                        voiceStageDetail = "Interrupted mid-sentence — adapting to driver correction!"
                    )
                }
            }

            is LiveWsEvent.Transcript -> {
                appendTranscript(event.role, event.text, event.isFinal)
            }

            is LiveWsEvent.TurnComplete -> {
                openStreamBubbleId = null
                openStreamRole = null
                _uiState.update {
                    it.copy(
                        voiceEnergy = 0.05f,
                        voiceStage = "LISTENING",
                        voiceStageDetail = "Turn complete — listening for next update."
                    )
                }
            }

            is LiveWsEvent.ToolCallStart -> {
                val entry = ToolLogEntry(
                    id = UUID.randomUUID().toString(),
                    name = event.name,
                    argsSummary = event.argsSummary,
                    status = "RUNNING"
                )
                _uiState.update {
                    it.copy(
                        toolLogs = (listOf(entry) + it.toolLogs).take(30),
                        voiceStage = "TOOL RUNNING",
                        voiceStageDetail = "Executing ${event.name}()..."
                    )
                }
            }

            is LiveWsEvent.ToolCallResult -> {
                val entry = ToolLogEntry(
                    id = UUID.randomUUID().toString(),
                    name = event.name,
                    argsSummary = event.argsSummary,
                    status = event.status,
                    elapsedMs = event.elapsedMs
                )
                _uiState.update { state ->
                    val nextPolicies = state.highlightedPolicyIds + event.matchedPolicyIds
                    state.copy(
                        toolLogs = (listOf(entry) + state.toolLogs).take(30),
                        highlightedPolicyIds = nextPolicies,
                        guidance = event.guidance ?: state.guidance,
                        activeStore = event.customerName ?: state.activeStore
                    )
                }
            }

            is LiveWsEvent.WorkflowReply -> {
                appendTranscript("assistant", event.text, true)
                audioEngine.speakTts(event.text)
                _uiState.update {
                    it.copy(
                        guidance = event.guidance ?: it.guidance,
                        voiceStage = event.intent,
                        voiceStageDetail = "AI replied (${event.intent})"
                    )
                }
            }

            is LiveWsEvent.ErpStateUpdate -> {
                _uiState.update {
                    it.copy(
                        erpState = event.state,
                        latestReceipt = event.state.receipts.firstOrNull() ?: it.latestReceipt
                    )
                }
            }

            is LiveWsEvent.ManagerDecision -> {
                _uiState.update {
                    it.copy(
                        latestReceipt = event.receipt ?: it.latestReceipt,
                        toastMessage = "Manager Priya ${event.decision} ${event.approval.customerName}"
                    )
                }
                appendTranscript(
                    "system",
                    "👩‍💼 Manager Priya ${event.decision} ${event.approval.customerName} (${event.approval.policyRef})",
                    true
                )
            }

            is LiveWsEvent.Error -> {
                appendTranscript("system", "⚠️ ${event.message}", true)
            }

            is LiveWsEvent.Closed -> {
                audioEngine.stopMicCapture()
            }
        }
    }

    fun forceEndTurn() {
        wsClient.sendForceEndTurn()
    }

    fun runGuidedStep(step: Int, hasMicPermission: Boolean) {
        if (!_uiState.value.callActive) {
            startLiveCall(hasMicPermission)
        }
        if (step == 2) {
            audioEngine.flushPlayback()
        }

        viewModelScope.launch {
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                wsClient.sendGuidedStep(step)
                runCatching { apiClient.runGuidedStep(step) }
                    .onSuccess { res ->
                        if (!_uiState.value.liveGeminiReady) {
                            res.userText?.let { appendTranscript("user", it, true) }
                            if (res.isBargeIn) {
                                appendTranscript("barge_in", "⚡ Barge-In Detected — Audio Flushed", true)
                            }
                            if (res.replyText.isNotBlank()) {
                                appendTranscript("assistant", res.replyText, true)
                                audioEngine.speakTts(res.replyText)
                            }
                            _uiState.update {
                                it.copy(
                                    erpState = res.state ?: it.erpState,
                                    guidance = res.guidance ?: it.guidance,
                                    interruptionCount = if (res.isBargeIn) it.interruptionCount + 1 else it.interruptionCount,
                                    latencyHistory = (it.latencyHistory + res.processingMs.toInt().coerceAtLeast(180)).takeLast(14),
                                    latestReceipt = res.state?.receipts?.firstOrNull() ?: it.latestReceipt
                                )
                            }
                        }
                    }
            } else {
                val out = offlineEngine.runGuidedStep(step, _uiState.value.driverName)
                applyOfflineTurnOutput(out)
            }
        }
    }

    fun sendTextTurn(text: String, hasMicPermission: Boolean) {
        val clean = text.trim()
        if (clean.isBlank()) return
        if (!_uiState.value.callActive) {
            startLiveCall(hasMicPermission)
        }
        viewModelScope.launch {
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                if (_uiState.value.liveGeminiReady) {
                    wsClient.sendTextTurn(clean, _uiState.value.driverName, _uiState.value.activeStore)
                } else {
                    appendTranscript("user", clean, true)
                    runCatching {
                        apiClient.sendAgentTurn(clean, _uiState.value.driverName, _uiState.value.activeStore)
                    }.onSuccess { res ->
                        if (res.isBargeIn) appendTranscript("barge_in", "⚡ Barge-In Detected", true)
                        if (res.replyText.isNotBlank()) {
                            appendTranscript("assistant", res.replyText, true)
                            audioEngine.speakTts(res.replyText)
                        }
                        _uiState.update {
                            it.copy(
                                erpState = res.state ?: it.erpState,
                                guidance = res.guidance ?: it.guidance,
                                latestReceipt = res.state?.receipts?.firstOrNull() ?: it.latestReceipt
                            )
                        }
                    }.onFailure { err ->
                        _uiState.update { it.copy(toastMessage = "Turn error: ${err.message}") }
                    }
                }
            } else {
                val out = offlineEngine.processTurn(clean, _uiState.value.driverName, _uiState.value.activeStore)
                applyOfflineTurnOutput(out)
            }
        }
    }

    private fun applyOfflineTurnOutput(out: OfflineDemoEngine.OfflineTurnOutput) {
        if (out.isBargeIn) {
            audioEngine.flushPlayback()
            appendTranscript("barge_in", "⚡ Mid-Sentence Barge-In — AI Audio Flushed", true)
        }
        appendTranscript("user", out.userText, true)
        appendTranscript("assistant", out.replyText, true)
        audioEngine.speakTts(out.replyText)
        val log = ToolLogEntry(
            id = UUID.randomUUID().toString(),
            name = "deliverex_workflow",
            argsSummary = "{\"intent\":\"${out.intent}\",\"sops\":${out.matchedPolicies}}",
            status = if (out.matchedPolicies.contains("SOP-4.2")) "ESCALATED" else "SYNCED",
            elapsedMs = 240.0
        )
        _uiState.update {
            it.copy(
                erpState = out.state,
                guidance = out.guidance,
                highlightedPolicyIds = it.highlightedPolicyIds + out.matchedPolicies,
                interruptionCount = if (out.isBargeIn) it.interruptionCount + 1 else it.interruptionCount,
                latencyHistory = (it.latencyHistory + (210..340).random()).takeLast(14),
                toolLogs = (listOf(log) + it.toolLogs).take(30),
                latestReceipt = out.receipt ?: out.state.receipts.firstOrNull() ?: it.latestReceipt,
                voiceStage = out.intent,
                voiceStageDetail = out.guidance.coachTip
            )
        }
    }

    fun submitProofBitmap(bitmap: Bitmap, caption: String, damagedBags: Int) {
        viewModelScope.launch {
            val dataUrl = withContext(Dispatchers.Default) {
                val scaled = Bitmap.createScaledBitmap(bitmap, 640, (bitmap.height * 640f / bitmap.width.coerceAtLeast(1)).toInt().coerceAtLeast(360), true)
                val out = ByteArrayOutputStream()
                scaled.compress(Bitmap.CompressFormat.JPEG, 78, out)
                "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            }
            submitProofDataUrl(dataUrl, caption, damagedBags)
        }
    }

    fun submitSampleTornBagsProof() {
        viewModelScope.launch {
            val dataUrl = withContext(Dispatchers.Default) {
                generateSampleDamageProofDataUrl(_uiState.value.activeStore)
            }
            submitProofDataUrl(
                dataUrl = dataUrl,
                caption = "Field Camera: 2 Torn UltraTech Cement Bags at ${_uiState.value.activeStore}",
                damagedBags = 2
            )
        }
    }

    private suspend fun submitProofDataUrl(dataUrl: String, caption: String, damagedBags: Int) {
        val store = _uiState.value.activeStore
        if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
            if (_uiState.value.liveGeminiReady) {
                wsClient.sendVideoFrame(
                    dataUrl = dataUrl,
                    caption = caption,
                    customerName = store,
                    damagedBags = damagedBags,
                    prompt = "Driver showed $damagedBags torn cement bags at $store on camera. Verify visually and attach proof to Manager Priya's approval card."
                )
            }
            runCatching {
                apiClient.uploadProofPhoto(dataUrl, caption, store, damagedBags, _uiState.value.driverName)
            }.onSuccess { state ->
                _uiState.update {
                    it.copy(
                        erpState = state,
                        toastMessage = "👁️ Visual proof verified & attached to Priya's 1-Tap Approval!"
                    )
                }
                com.deliverex.live.update.AppNotificationManager.notifyOpsAlert(
                    context = getApplication(),
                    title = "📷 Photo Attached — $store",
                    message = "Damaged bag proof ($damagedBags bags) sent to Priya for 1-tap approval."
                )
                appendTranscript("system", "📷 Visual proof attached for $store ($damagedBags torn bags).", true)
            }.onFailure { err ->
                _uiState.update { it.copy(toastMessage = "Photo upload failed: ${err.message}") }
            }
        } else {
            val state = offlineEngine.attachVisualProof(dataUrl, caption, store, damagedBags, _uiState.value.driverName)
            _uiState.update {
                it.copy(
                    erpState = state,
                    highlightedPolicyIds = it.highlightedPolicyIds + "SOP-5.1",
                    toastMessage = "👁️ Visual proof attached to Priya's 1-Tap Approval (SOP-5.1)!"
                )
            }
            appendTranscript("system", "📷 Visual proof attached for $store ($damagedBags torn bags).", true)
        }
    }

    fun decideApproval(approvalId: String, decision: String) {
        viewModelScope.launch {
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                runCatching { apiClient.decideApproval(approvalId, decision) }
                    .onSuccess { res ->
                        _uiState.update {
                            it.copy(
                                erpState = res.state,
                                latestReceipt = res.receipt ?: it.latestReceipt,
                                toastMessage = "Priya $decision ${res.approval.customerName}"
                            )
                        }
                        com.deliverex.live.update.AppNotificationManager.notifyOpsAlert(
                            context = getApplication(),
                            title = if (decision == "APPROVED") "✅ Approved — ${res.approval.customerName}" else "📋 Approval $decision",
                            message = if (res.receipt != null) "Official WhatsApp receipt is ready to share!" else "Priya updated approval for ${res.approval.customerName}."
                        )
                        if (decision == "APPROVED") {
                            audioEngine.speakTts("Badhiya khabar Raju bhai! Priya ma'am ne ${res.approval.customerName} ka approval de diya hai aur WhatsApp receipt bhej di gayi hai.")
                        }
                    }
                    .onFailure { err ->
                        if (err is OwnerAuthRequiredException) {
                            promptOwnerLogin { decideApproval(approvalId, decision) }
                        } else {
                            _uiState.update { it.copy(toastMessage = "Approval error: ${err.message}") }
                        }
                    }
            } else {
                val res = offlineEngine.decideApproval(approvalId, decision)
                _uiState.update {
                    it.copy(
                        erpState = res.state,
                        latestReceipt = res.receipt ?: it.latestReceipt,
                        toastMessage = "Priya $decision ${res.approval.customerName}"
                    )
                }
                if (decision == "APPROVED") {
                    audioEngine.speakTts("Badhiya khabar Raju bhai! Priya ma'am ne approval de diya hai aur WhatsApp receipt bhej di gayi hai.")
                }
            }
        }
    }

    fun toggleWhatsAppVoiceRecording() {
        if (!_uiState.value.waRecording) {
            audioEngine.startWhatsAppRecording()
                .onSuccess {
                    _uiState.update { it.copy(waRecording = true, toastMessage = "Recording WhatsApp voice note...") }
                }
                .onFailure { err ->
                    _uiState.update { it.copy(toastMessage = "Mic unavailable: ${err.message}") }
                }
        } else {
            val file = audioEngine.stopWhatsAppRecording()
            _uiState.update { it.copy(waRecording = false) }
            if (file != null) {
                viewModelScope.launch {
                    _uiState.update { it.copy(waSending = true) }
                    if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                        runCatching {
                            apiClient.uploadWhatsAppVoiceNote(
                                audioFile = file,
                                text = null,
                                activeStore = _uiState.value.activeStore,
                                driverName = _uiState.value.driverName
                            )
                        }.onSuccess { obj ->
                            val newState = obj["state"]?.let {
                                runCatching { apiClient.json.decodeFromJsonElement(ErpState.serializer(), it) }.getOrNull()
                            }
                            _uiState.update {
                                it.copy(
                                    erpState = newState ?: it.erpState,
                                    waSending = false
                                )
                            }
                        }.onFailure { err ->
                            _uiState.update { it.copy(waSending = false, toastMessage = "Voice note upload failed: ${err.message}") }
                        }
                    } else {
                        val state = offlineEngine.sendWhatsAppTurn(
                            "🎤 [Voice Note] ${_uiState.value.activeStore} pe delivery complete, cash collected.",
                            _uiState.value.driverName,
                            _uiState.value.activeStore
                        )
                        _uiState.update { it.copy(erpState = state, waSending = false) }
                    }
                    file.delete()
                }
            }
        }
    }

    fun sendWhatsAppText(text: String, imageBitmap: Bitmap? = null) {
        val clean = text.trim()
        if (clean.isBlank() && imageBitmap == null) return

        viewModelScope.launch {
            _uiState.update { it.copy(waSending = true) }
            val imageDataUrl = imageBitmap?.let { bmp ->
                withContext(Dispatchers.Default) {
                    val scaled = Bitmap.createScaledBitmap(bmp, 640, (bmp.height * 640f / bmp.width.coerceAtLeast(1)).toInt().coerceAtLeast(360), true)
                    val out = ByteArrayOutputStream()
                    scaled.compress(Bitmap.CompressFormat.JPEG, 78, out)
                    "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
                }
            }

            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                runCatching {
                    apiClient.uploadWhatsAppVoiceNote(
                        audioFile = null,
                        text = clean.ifBlank { "${_uiState.value.activeStore} ke damaged bags ki photo proof" },
                        imageDataUrl = imageDataUrl,
                        activeStore = _uiState.value.activeStore,
                        driverName = _uiState.value.driverName
                    )
                }.onSuccess { obj ->
                    val newState = obj["state"]?.let {
                        runCatching { apiClient.json.decodeFromJsonElement(ErpState.serializer(), it) }.getOrNull()
                    }
                    _uiState.update {
                        it.copy(
                            erpState = newState ?: it.erpState,
                            latestReceipt = newState?.receipts?.firstOrNull() ?: it.latestReceipt,
                            waSending = false
                        )
                    }
                }.onFailure { err ->
                    _uiState.update { it.copy(waSending = false, toastMessage = "WhatsApp send error: ${err.message}") }
                }
            } else {
                val state = offlineEngine.sendWhatsAppTurn(
                    clean.ifBlank { "${_uiState.value.activeStore} photo proof" },
                    _uiState.value.driverName,
                    _uiState.value.activeStore,
                    imageDataUrl
                )
                _uiState.update {
                    it.copy(
                        erpState = state,
                        latestReceipt = state.receipts.firstOrNull() ?: it.latestReceipt,
                        waSending = false
                    )
                }
            }
        }
    }

    fun resetDemo() {
        viewModelScope.launch {
            stopLiveCall()
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                runCatching { apiClient.resetDemo() }
                    .onSuccess { state ->
                        _uiState.update {
                            it.copy(
                                erpState = state,
                                transcripts = emptyList(),
                                toolLogs = emptyList(),
                                highlightedPolicyIds = emptySet(),
                                interruptionCount = 0,
                                latestReceipt = null,
                                guidance = FrontlineGuidance(),
                                toastMessage = "Demo reset cleanly!"
                            )
                        }
                    }
                    .onFailure { err ->
                        if (err is OwnerAuthRequiredException) {
                            promptOwnerLogin { resetDemo() }
                        } else {
                            _uiState.update { it.copy(toastMessage = "Reset failed: ${err.message}") }
                        }
                    }
            } else {
                val env = offlineEngine.reset()
                _uiState.update {
                    it.copy(
                        erpState = env.state,
                        transcripts = emptyList(),
                        toolLogs = emptyList(),
                        highlightedPolicyIds = emptySet(),
                        interruptionCount = 0,
                        latestReceipt = null,
                        guidance = FrontlineGuidance(),
                        toastMessage = "Offline demo reset!"
                    )
                }
            }
        }
    }

    fun promptOwnerLogin(onUnlocked: (() -> Unit)? = null) {
        pendingOwnerAction = onUnlocked
        _uiState.update { it.copy(showOwnerPinDialog = true) }
    }

    fun dismissOwnerPinDialog() {
        pendingOwnerAction = null
        _uiState.update { it.copy(showOwnerPinDialog = false) }
    }

    fun unlockOwnerWithPin(pin: String) {
        viewModelScope.launch {
            if (!_uiState.value.backendConnected || prefs.offlineDemoMode) {
                _uiState.update {
                    it.copy(
                        ownerAuthenticated = true,
                        ownerActor = "Priya Sharma (Demo)",
                        showOwnerPinDialog = false,
                        toastMessage = "🔓 Owner mode unlocked"
                    )
                }
                pendingOwnerAction?.invoke()
                pendingOwnerAction = null
                return@launch
            }
            runCatching { apiClient.loginOwner(pin) }
                .onSuccess { resp ->
                    prefs.ownerToken = resp.token
                    _uiState.update {
                        it.copy(
                            ownerAuthenticated = true,
                            ownerActor = resp.actor,
                            showOwnerPinDialog = false,
                            toastMessage = "🔓 ${resp.actor} verified"
                        )
                    }
                    pendingOwnerAction?.invoke()
                    pendingOwnerAction = null
                }
                .onFailure { err ->
                    _uiState.update { it.copy(toastMessage = err.message ?: "Invalid Owner PIN") }
                }
        }
    }

    fun exportTallyXml() {
        viewModelScope.launch {
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                runCatching { apiClient.exportTallyXml() }
                    .onSuccess { xml ->
                        _uiState.update { it.copy(exportedTitle = "TallyPrime XML Vouchers", exportedContent = xml) }
                        refreshFromServer()
                    }
                    .onFailure { err ->
                        if (err is OwnerAuthRequiredException) promptOwnerLogin { exportTallyXml() }
                        else _uiState.update { it.copy(toastMessage = "Tally export error: ${err.message}") }
                    }
            } else {
                _uiState.update { it.copy(exportedTitle = "TallyPrime XML Vouchers", exportedContent = offlineEngine.exportTallyXml()) }
            }
        }
    }

    fun exportLedgerCsv() {
        viewModelScope.launch {
            if (_uiState.value.backendConnected && !prefs.offlineDemoMode) {
                runCatching { apiClient.exportLedgerCsv() }
                    .onSuccess { csv ->
                        _uiState.update { it.copy(exportedTitle = "DeliverEx Ledger CSV", exportedContent = csv) }
                        refreshFromServer()
                    }
                    .onFailure { err ->
                        if (err is OwnerAuthRequiredException) promptOwnerLogin { exportLedgerCsv() }
                        else _uiState.update { it.copy(toastMessage = "CSV export error: ${err.message}") }
                    }
            } else {
                _uiState.update { it.copy(exportedTitle = "DeliverEx Ledger CSV", exportedContent = offlineEngine.exportLedgerCsv()) }
            }
        }
    }

    fun dismissExportDialog() {
        _uiState.update { it.copy(exportedTitle = null, exportedContent = null) }
    }

    fun completeOnboarding(role: String, name: String, language: String) {
        val cleanName = name.trim().ifBlank { if (role == "MANAGER") "Priya Sharma" else "Raju Kumar" }
        prefs.userRole = role
        prefs.driverName = cleanName
        prefs.preferredLanguage = language
        prefs.onboardingCompleted = true
        _uiState.update {
            it.copy(
                userRole = role,
                driverName = cleanName,
                preferredLanguage = language,
                onboardingCompleted = true,
                showDemoControls = role == "DEMO"
            )
        }
    }

    fun switchRole(role: String) {
        prefs.userRole = role
        _uiState.update {
            it.copy(
                userRole = role,
                showDemoControls = role == "DEMO"
            )
        }
    }

    fun setPreferredLanguage(language: String) {
        prefs.preferredLanguage = language
        _uiState.update { it.copy(preferredLanguage = language) }
    }

    fun toggleDemoControls() {
        _uiState.update { it.copy(showDemoControls = !it.showDemoControls) }
    }

    fun toggleMicMute() {
        _uiState.update { state ->
            val next = !state.micMuted
            state.copy(
                micMuted = next,
                voiceStageDetail = if (next) "Microphone muted — tap Unmute to speak" else "Listening — speak naturally in ${state.preferredLanguage}"
            )
        }
    }

    fun setLedgerFilter(filter: LedgerFilter) {
        _uiState.update { it.copy(ledgerFilter = filter) }
    }

    fun setLedgerQuery(query: String) {
        _uiState.update { it.copy(ledgerQuery = query) }
    }

    fun updateRoi(dailyCalls: Int) {
        val clamped = dailyCalls.coerceIn(25, 2000)
        val savings = ((30.0 - 2.20) * clamped * 30).toLong()
        _uiState.update {
            it.copy(
                roi = it.roi.copy(
                    dailyCalls = clamped,
                    monthlySavingsInr = savings,
                    roiMultiple = 13.6
                )
            )
        }
    }

    fun clearToast() {
        _uiState.update { it.copy(toastMessage = null) }
    }

    private fun appendTranscript(role: String, text: String, isFinal: Boolean) {
        _uiState.update { state ->
            val list = state.transcripts.toMutableList()
            if (!isFinal && openStreamRole == role && openStreamBubbleId != null) {
                val idx = list.indexOfFirst { it.id == openStreamBubbleId }
                if (idx >= 0) {
                    list[idx] = list[idx].copy(text = list[idx].text + text)
                    return@update state.copy(transcripts = list)
                }
            }
            val newId = UUID.randomUUID().toString()
            list.add(TranscriptMessage(id = newId, role = role, text = text, isFinal = isFinal))
            if (!isFinal) {
                openStreamBubbleId = newId
                openStreamRole = role
            } else {
                openStreamBubbleId = null
                openStreamRole = null
            }
            state.copy(transcripts = list)
        }
    }

    private fun generateSampleDamageProofDataUrl(storeName: String): String {
        val bmp = Bitmap.createBitmap(640, 380, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        canvas.drawColor(AndroidColor.rgb(18, 26, 42))

        val bagPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = AndroidColor.rgb(180, 155, 118) }
        val tearPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = AndroidColor.rgb(225, 29, 72)
            strokeWidth = 6f
            style = Paint.Style.STROKE
        }
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = AndroidColor.WHITE
            textSize = 26f
            isFakeBoldText = true
        }
        val subPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = AndroidColor.rgb(56, 189, 248)
            textSize = 20f
        }

        canvas.drawRoundRect(50f, 80f, 290f, 300f, 24f, 24f, bagPaint)
        canvas.drawRoundRect(340f, 80f, 580f, 300f, 24f, 24f, bagPaint)
        canvas.drawLine(110f, 140f, 220f, 230f, tearPaint)
        canvas.drawLine(410f, 130f, 510f, 240f, tearPaint)
        canvas.drawText("ULTRATECH 50KG • TORN", 70f, 190f, textPaint)
        canvas.drawText("PROOF: $storeName", 50f, 48f, subPaint)
        canvas.drawText("AI VISION VERIFIED: 2 DAMAGED BAGS", 50f, 348f, subPaint)

        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 82, out)
        return "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    override fun onCleared() {
        super.onCleared()
        callTimerJob?.cancel()
        wsClient.disconnect()
        audioEngine.release()
    }
}
