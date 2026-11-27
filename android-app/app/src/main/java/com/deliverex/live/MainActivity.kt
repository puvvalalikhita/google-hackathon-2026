package com.deliverex.live

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.AdminPanelSettings
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.PhoneInTalk
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.deliverex.live.ui.DeliverExViewModel
import com.deliverex.live.ui.components.CameraCaptureDialog
import com.deliverex.live.ui.components.ExportPreviewDialog
import com.deliverex.live.ui.components.OnboardingScreen
import com.deliverex.live.ui.components.OwnerPinDialog
import com.deliverex.live.ui.components.ProofLightboxDialog
import com.deliverex.live.ui.components.RoleSwitcherBar
import com.deliverex.live.ui.components.ServerAndPrivacyDialog
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.screens.InsightsRoiScreen
import com.deliverex.live.ui.screens.LiveCallScreen
import com.deliverex.live.ui.screens.ManagerOpsScreen
import com.deliverex.live.ui.screens.WhatsAppOpsScreen
import com.deliverex.live.ui.theme.DeliverExTheme
import com.deliverex.live.ui.theme.LocalDeliverExPalette

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
        )
        setContent {
            DeliverExRootApp()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeliverExRootApp(vm: DeliverExViewModel = viewModel()) {
    val state by vm.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }

    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var showSettings by remember { mutableStateOf(false) }
    var showCameraDialog by remember { mutableStateOf(false) }
    var zoomedProofUrl by remember { mutableStateOf<String?>(null) }

    var pendingActionAfterMic by remember { mutableStateOf<(() -> Unit)?>(null) }
    var pendingActionAfterCam by remember { mutableStateOf<(() -> Unit)?>(null) }

    val micPermLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        pendingActionAfterMic?.invoke()
        pendingActionAfterMic = null
        if (!granted) {
            // Still allow interactive text/guided step mode cleanly
        }
    }

    val camPermLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            pendingActionAfterCam?.invoke()
        }
        pendingActionAfterCam = null
    }

    fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun hasCamPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    fun withMicPermission(action: () -> Unit) {
        if (hasMicPermission()) {
            action()
        } else {
            pendingActionAfterMic = action
            micPermLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    fun withCamPermission(action: () -> Unit) {
        if (hasCamPermission()) {
            action()
        } else {
            pendingActionAfterCam = action
            camPermLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    LaunchedEffect(state.toastMessage) {
        val msg = state.toastMessage
        if (!msg.isNullOrBlank()) {
            snackbarHostState.showSnackbar(msg)
            vm.clearToast()
        }
    }

    DeliverExTheme(themeKey = state.themeKey) {
        val pal = LocalDeliverExPalette.current
        val pendingApprovals = state.erpState.approvals.count { it.status == "PENDING" }

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(Color(0xFF060A13), Color(0xFF0B1426), Color(0xFF070B14))
                    )
                )
        ) {
            if (!state.onboardingCompleted) {
                OnboardingScreen(
                    initialName = state.driverName,
                    initialLanguage = state.preferredLanguage,
                    onComplete = { role, name, lang ->
                        vm.completeOnboarding(role, name, lang)
                        selectedTab = if (role == "MANAGER") 2 else 0
                    }
                )
            } else {
                Scaffold(
                    containerColor = Color.Transparent,
                    snackbarHost = { SnackbarHost(snackbarHostState) },
                    topBar = {
                        TopAppBar(
                            colors = TopAppBarDefaults.topAppBarColors(
                                containerColor = Color(0xCC09101E),
                                titleContentColor = Color.White
                            ),
                            title = {
                                Column {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text("DeliverEx Live", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
                                        Spacer(Modifier.width(8.dp))
                                        StatusPill(
                                            text = when {
                                                state.backendConnected && state.health.geminiConfigured -> "● Live AI"
                                                state.backendConnected -> "● Connected"
                                                else -> "● Practice Mode"
                                            },
                                            color = if (state.backendConnected && state.health.geminiConfigured) pal.success else pal.warning
                                        )
                                    }
                                }
                            },
                            actions = {
                                IconButton(onClick = { vm.refreshFromServer() }) {
                                    Icon(Icons.Default.Refresh, contentDescription = "Sync backend", tint = pal.cyan)
                                }
                                IconButton(onClick = { showSettings = true }) {
                                    Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Color.White)
                                }
                            }
                        )
                    },
                    bottomBar = {
                        NavigationBar(containerColor = Color(0xEE09101E)) {
                            NavigationBarItem(
                                selected = selectedTab == 0,
                                onClick = { selectedTab = 0 },
                                icon = { Icon(Icons.Default.PhoneInTalk, contentDescription = null) },
                                label = { Text("Talk", fontSize = 11.sp) }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 1,
                                onClick = { selectedTab = 1 },
                                icon = { Icon(Icons.AutoMirrored.Filled.Chat, contentDescription = null) },
                                label = { Text("WhatsApp", fontSize = 11.sp) }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 2,
                                onClick = { selectedTab = 2 },
                                icon = {
                                    BadgedBox(
                                        badge = {
                                            if (pendingApprovals > 0) {
                                                Badge { Text(pendingApprovals.toString()) }
                                            }
                                        }
                                    ) {
                                        Icon(Icons.Default.AdminPanelSettings, contentDescription = null)
                                    }
                                },
                                label = { Text("Approvals", fontSize = 11.sp) }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 3,
                                onClick = { selectedTab = 3 },
                                icon = { Icon(Icons.Default.Analytics, contentDescription = null) },
                                label = { Text("Insights", fontSize = 11.sp) }
                            )
                        }
                    }
                ) { innerPadding ->
                    Column(modifier = Modifier.fillMaxSize().padding(innerPadding)) {
                        RoleSwitcherBar(
                            activeRole = state.userRole,
                            onSelectRole = { role ->
                                vm.switchRole(role)
                                if (role == "MANAGER") selectedTab = 2 else if (role == "DRIVER") selectedTab = 0
                            }
                        )
                        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
                            when (selectedTab) {
                                0 -> LiveCallScreen(
                                    state = state,
                                    onToggleCall = { withMicPermission { vm.toggleLiveCall(hasMicPermission()) } },
                                    onToggleMute = { vm.toggleMicMute() },
                                    onEndTurn = { vm.forceEndTurn() },
                                    onToggleNoise = { vm.toggleMarketNoise() },
                                    onSelectStore = { vm.setActiveStore(it) },
                                    onSelectLanguage = { vm.setPreferredLanguage(it) },
                                    onToggleDemoControls = { vm.toggleDemoControls() },
                                    onRunGuidedStep = { step -> withMicPermission { vm.runGuidedStep(step, hasMicPermission()) } },
                                    onSendTextTurn = { text -> withMicPermission { vm.sendTextTurn(text, hasMicPermission()) } },
                                    onOpenCameraProof = { withCamPermission { showCameraDialog = true } },
                                    onSendSampleDamageProof = { vm.submitSampleTornBagsProof() }
                                )
                                1 -> WhatsAppOpsScreen(
                                    state = state,
                                    onToggleVoiceRecord = { withMicPermission { vm.toggleWhatsAppVoiceRecording() } },
                                    onSendWhatsApp = { text, bmp -> vm.sendWhatsAppText(text, bmp) },
                                    onOpenProofZoom = { zoomedProofUrl = it }
                                )
                                2 -> ManagerOpsScreen(
                                    state = state,
                                    onDecideApproval = { id, decision -> vm.decideApproval(id, decision) },
                                    onOpenProofZoom = { zoomedProofUrl = it },
                                    onSetLedgerFilter = { vm.setLedgerFilter(it) },
                                    onSetLedgerQuery = { vm.setLedgerQuery(it) },
                                    onSelectStore = {
                                        vm.setActiveStore(it)
                                        selectedTab = 0
                                    },
                                    onUnlockOwner = { vm.promptOwnerLogin() },
                                    onExportTallyXml = { vm.exportTallyXml() },
                                    onExportLedgerCsv = { vm.exportLedgerCsv() }
                                )
                                3 -> InsightsRoiScreen(
                                    state = state,
                                    onUpdateDailyCalls = { vm.updateRoi(it) },
                                    onResetDemo = { vm.resetDemo() },
                                    onOpenSettings = { showSettings = true }
                                )
                            }
                        }
                    }
                }
            }
        }

        if (showCameraDialog) {
            CameraCaptureDialog(
                storeName = state.activeStore,
                onCaptured = { bmp ->
                    showCameraDialog = false
                    vm.submitProofBitmap(
                        bitmap = bmp,
                        caption = "Field Camera POD (${state.activeStore})",
                        damagedBags = 2
                    )
                },
                onDismiss = { showCameraDialog = false }
            )
        }

        zoomedProofUrl?.let { url ->
            ProofLightboxDialog(
                dataUrl = url,
                baseUrl = state.baseUrl,
                onDismiss = { zoomedProofUrl = null }
            )
        }

        if (state.showOwnerPinDialog) {
            OwnerPinDialog(
                onUnlock = { pin -> vm.unlockOwnerWithPin(pin) },
                onDismiss = { vm.dismissOwnerPinDialog() }
            )
        }

        if (state.exportedTitle != null && state.exportedContent != null) {
            ExportPreviewDialog(
                title = state.exportedTitle!!,
                content = state.exportedContent!!,
                onDismiss = { vm.dismissExportDialog() }
            )
        }

        if (showSettings) {
            ServerAndPrivacyDialog(
                currentUrl = state.baseUrl,
                currentDriverName = state.driverName,
                offlineDemoMode = state.isOfflineDemo,
                activeThemeKey = state.themeKey,
                onSelectTheme = { vm.setTheme(it) },
                onSave = { url, driver, offline ->
                    vm.updateServerSettings(url, driver, offline)
                    showSettings = false
                },
                onDismiss = { showSettings = false }
            )
        }
    }
}
