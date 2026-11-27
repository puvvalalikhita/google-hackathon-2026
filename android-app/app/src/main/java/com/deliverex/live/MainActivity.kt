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
import androidx.compose.material.icons.automirrored.filled.Logout
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
import com.deliverex.live.ui.components.AppUpdateBanner
import com.deliverex.live.ui.components.DamagePhotoConfirmDialog
import com.deliverex.live.ui.components.ExportPreviewDialog
import com.deliverex.live.ui.components.LoginScreen
import com.deliverex.live.ui.components.OwnerPinDialog
import com.deliverex.live.ui.components.ProofLightboxDialog
import com.deliverex.live.ui.components.ServerAndPrivacyDialog
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.components.WorkerLogoBadge
import com.deliverex.live.ui.components.createTempCameraUri
import com.deliverex.live.ui.components.decodeBitmapFromUri
import com.deliverex.live.update.AppNotificationManager
import com.deliverex.live.ui.screens.InsightsRoiScreen
import com.deliverex.live.ui.screens.LiveCallScreen
import com.deliverex.live.ui.screens.ManagerOpsScreen
import com.deliverex.live.ui.screens.WhatsAppOpsScreen
import com.deliverex.live.ui.theme.DeliverExTheme
import com.deliverex.live.ui.theme.LocalDeliverExPalette

class MainActivity : ComponentActivity() {
    private var triggerUpdateOnLaunch by mutableStateOf(false)
    private var updateUrlFromNotif by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleUpdateIntent(intent)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
        )
        setContent {
            DeliverExRootApp(
                triggerUpdateOnLaunch = triggerUpdateOnLaunch,
                updateUrlFromNotif = updateUrlFromNotif,
                onConsumedUpdateIntent = {
                    triggerUpdateOnLaunch = false
                    updateUrlFromNotif = null
                }
            )
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleUpdateIntent(intent)
    }

    private fun handleUpdateIntent(intent: android.content.Intent?) {
        if (intent?.getBooleanExtra(AppNotificationManager.EXTRA_TRIGGER_UPDATE, false) == true) {
            triggerUpdateOnLaunch = true
            updateUrlFromNotif = intent.getStringExtra(AppNotificationManager.EXTRA_UPDATE_APK_URL)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeliverExRootApp(
    vm: DeliverExViewModel = viewModel(),
    triggerUpdateOnLaunch: Boolean = false,
    updateUrlFromNotif: String? = null,
    onConsumedUpdateIntent: () -> Unit = {}
) {
    val state by vm.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }

    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var showSettings by remember { mutableStateOf(false) }
    var pendingCameraUri by remember { mutableStateOf<android.net.Uri?>(null) }
    var pendingProofBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var zoomedProofUrl by remember { mutableStateOf<String?>(null) }

    var pendingActionAfterMic by remember { mutableStateOf<(() -> Unit)?>(null) }
    var pendingActionAfterCam by remember { mutableStateOf<(() -> Unit)?>(null) }

    val nativeCameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { ok ->
        val uri = pendingCameraUri
        if (ok && uri != null) {
            pendingProofBitmap = decodeBitmapFromUri(context, uri)
        }
    }

    val galleryProofLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            pendingProofBitmap = decodeBitmapFromUri(context, uri)
        }
    }

    fun launchNativeCamera() {
        val uri = createTempCameraUri(context)
        pendingCameraUri = uri
        nativeCameraLauncher.launch(uri)
    }

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

    val notifPermLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> }

    LaunchedEffect(state.onboardingCompleted) {
        if (state.onboardingCompleted && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (!AppNotificationManager.hasNotificationPermission(context)) {
                notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    val lifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current
    androidx.compose.runtime.DisposableEffect(lifecycleOwner) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME) {
                vm.checkForAppUpdate(silent = true)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(triggerUpdateOnLaunch) {
        if (triggerUpdateOnLaunch) {
            vm.downloadAndInstallUpdate(updateUrlFromNotif)
            onConsumedUpdateIntent()
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
                LoginScreen(
                    initialName = state.driverName,
                    initialLanguage = state.preferredLanguage,
                    onWorkerLogin = { name, lang ->
                        vm.loginAsWorker(name, lang)
                        selectedTab = 0
                    },
                    onManagerLogin = { pin, onResult ->
                        vm.loginAsManager(pin) { ok, err ->
                            if (ok) selectedTab = 2
                            onResult(ok, err)
                        }
                    },
                    onDemoLogin = {
                        vm.loginAsDemo()
                        selectedTab = 0
                    }
                )
            } else {
                // Keep selectedTab valid for current role
                LaunchedEffect(state.userRole) {
                    when (state.userRole) {
                        "DRIVER" -> if (selectedTab !in listOf(0, 1)) selectedTab = 0
                        "MANAGER" -> if (selectedTab !in listOf(2, 3)) selectedTab = 2
                    }
                }

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
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    WorkerLogoBadge(size = 32.dp)
                                    Spacer(Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            text = when (state.userRole) {
                                                "MANAGER" -> "Priya • Manager"
                                                "DEMO" -> "Raju Bhai • Demo"
                                                else -> "Raju Bhai"
                                            },
                                            fontWeight = FontWeight.ExtraBold,
                                            fontSize = 16.sp
                                        )
                                        Text(
                                            text = when {
                                                state.backendConnected && state.health.geminiConfigured -> "● Live AI Ready"
                                                state.backendConnected -> "● Connected"
                                                else -> "● Practice Mode"
                                            },
                                            color = if (state.backendConnected && state.health.geminiConfigured) pal.success else pal.warning,
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.SemiBold
                                        )
                                    }
                                }
                            },
                            actions = {
                                IconButton(onClick = { vm.refreshFromServer() }) {
                                    Icon(Icons.Default.Refresh, contentDescription = "Sync", tint = pal.cyan)
                                }
                                IconButton(onClick = { showSettings = true }) {
                                    Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Color.White)
                                }
                                IconButton(onClick = { vm.logout() }) {
                                    Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Switch Account", tint = pal.warning)
                                }
                            }
                        )
                    },
                    bottomBar = {
                        NavigationBar(containerColor = Color(0xEE09101E)) {
                            if (state.userRole == "DRIVER" || state.userRole == "DEMO") {
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
                                    label = { Text("Ops Chat", fontSize = 11.sp) }
                                )
                            }
                            if (state.userRole == "MANAGER" || state.userRole == "DEMO") {
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
                    }
                ) { innerPadding ->
                    Column(modifier = Modifier.fillMaxSize().padding(innerPadding)) {
                        state.availableUpdate?.let { upd ->
                            AppUpdateBanner(
                                versionName = upd.latestVersionName,
                                releaseNotes = upd.releaseNotes,
                                downloadProgress = state.updateDownloadProgress,
                                onUpdateClick = { vm.downloadAndInstallUpdate() }
                            )
                        }
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
                                    onOpenCameraProof = { withCamPermission { launchNativeCamera() } },
                                    onOpenGalleryProof = { galleryProofLauncher.launch("image/*") },
                                    onOpenProofZoom = { zoomedProofUrl = it },
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
                                        if (state.userRole == "DEMO") selectedTab = 0
                                    },
                                    onUnlockOwner = { vm.promptOwnerLogin() },
                                    onExportTallyXml = { vm.exportTallyXml() },
                                    onExportLedgerCsv = { vm.exportLedgerCsv() },
                                    onPushLedgerToOps = { vm.pushLedgerToOps() },
                                    onPushReceiptToOps = { title, msg -> vm.pushReceiptToOps(title, msg) }
                                )
                                3 -> InsightsRoiScreen(
                                    state = state,
                                    onUpdateDailyCalls = { vm.updateRoi(it) },
                                    onResetDemo = { vm.resetDemo() },
                                    onOpenSettings = { showSettings = true },
                                    onCheckUpdate = { vm.checkForAppUpdate(silent = false) },
                                    onTestNotification = { vm.sendTestNotification() }
                                )
                            }
                        }
                    }
                }
            }
        }

        pendingProofBitmap?.let { previewBmp ->
            DamagePhotoConfirmDialog(
                storeName = state.activeStore,
                bitmap = previewBmp,
                uploading = state.photoUploading,
                onConfirmUpload = { bags ->
                    pendingProofBitmap = null
                    vm.submitProofBitmap(
                        bitmap = previewBmp,
                        caption = "Torn Bags Photo (${state.activeStore})",
                        damagedBags = bags
                    )
                },
                onRetake = {
                    pendingProofBitmap = null
                    withCamPermission { launchNativeCamera() }
                },
                onDismiss = { pendingProofBitmap = null }
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
