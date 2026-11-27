package com.deliverex.live.ui.components

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.PrivacyTip
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.deliverex.live.R
import com.deliverex.live.ui.theme.DELIVEREX_PALETTES
import com.deliverex.live.ui.theme.LocalDeliverExPalette
import kotlin.math.sin

@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    borderColor: Color? = null,
    backgroundColor: Color? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    val pal = LocalDeliverExPalette.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = backgroundColor ?: pal.surfaceGlass,
        border = BorderStroke(1.dp, borderColor ?: pal.borderGlass),
        tonalElevation = 2.dp
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            content = content
        )
    }
}

@Composable
fun StatusPill(
    text: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.16f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.45f))
    ) {
        Text(
            text = text,
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
        )
    }
}

@Composable
fun VoiceOrbVisualizer(
    energy: Float,
    callActive: Boolean,
    stage: String,
    modifier: Modifier = Modifier
) {
    val pal = LocalDeliverExPalette.current
    val transition = rememberInfiniteTransition(label = "orb")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = (Math.PI * 2).toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(2200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "phase"
    )

    val orbColor = when {
        stage.contains("BARGE", ignoreCase = true) -> pal.warning
        stage.contains("SPEAK", ignoreCase = true) -> pal.success
        callActive -> pal.cyan
        else -> pal.primary
    }

    Canvas(modifier = modifier) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        val baseRadius = size.minDimension * 0.28f
        val boost = energy.coerceIn(0f, 1f) * (size.minDimension * 0.16f)

        // Outer ambient halo
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(orbColor.copy(alpha = 0.38f), Color.Transparent),
                center = Offset(cx, cy),
                radius = baseRadius * 2.1f + boost
            ),
            radius = baseRadius * 2.1f + boost,
            center = Offset(cx, cy)
        )

        // Animated pulse rings
        drawCircle(
            color = orbColor.copy(alpha = 0.35f),
            radius = baseRadius * 1.35f + boost + sin(phase.toDouble()).toFloat() * 4f,
            center = Offset(cx, cy),
            style = Stroke(width = 2.5f)
        )

        // Core sphere
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color.White.copy(alpha = 0.9f), orbColor, orbColor.copy(alpha = 0.4f)),
                center = Offset(cx - baseRadius * 0.25f, cy - baseRadius * 0.25f),
                radius = baseRadius * 1.25f
            ),
            radius = baseRadius + boost * 0.35f,
            center = Offset(cx, cy)
        )

        // Live waveform bars across bottom of canvas
        val barCount = 18
        val barWidth = size.width / (barCount * 1.8f)
        val startX = cx - (barCount * barWidth * 1.5f) / 2f
        for (i in 0 until barCount) {
            val wave = kotlin.math.abs(sin((phase + i * 0.55f).toDouble())).toFloat()
            val barHeight = (6f + wave * 28f * (0.25f + energy * 1.4f)).coerceAtMost(size.height * 0.35f)
            val x = startX + i * barWidth * 1.5f
            drawLine(
                color = orbColor.copy(alpha = 0.85f),
                start = Offset(x, size.height - barHeight),
                end = Offset(x, size.height),
                strokeWidth = barWidth.coerceAtLeast(3f)
            )
        }
    }
}

@Composable
fun LatencySparkline(
    values: List<Int>,
    modifier: Modifier = Modifier
) {
    val pal = LocalDeliverExPalette.current
    Canvas(modifier = modifier) {
        if (values.size < 2) return@Canvas
        val minV = (values.minOrNull() ?: 150).toFloat()
        val maxV = (values.maxOrNull() ?: 450).coerceAtLeast(minV.toInt() + 50).toFloat()
        val stepX = size.width / (values.size - 1).coerceAtLeast(1)

        val path = Path()
        values.forEachIndexed { idx, v ->
            val x = idx * stepX
            val norm = (v - minV) / (maxV - minV)
            val y = size.height - norm * (size.height * 0.8f) - size.height * 0.1f
            if (idx == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color = pal.cyan, style = Stroke(width = 3f))
    }
}

fun decodeDataUrlBitmap(dataUrl: String?): Bitmap? {
    if (dataUrl.isNullOrBlank()) return null
    if (dataUrl.startsWith("/") || dataUrl.startsWith("http")) return null
    val raw = if (dataUrl.contains(",")) dataUrl.substringAfter(",") else dataUrl
    return runCatching {
        val bytes = Base64.decode(raw, Base64.DEFAULT)
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }.getOrNull()
}

suspend fun loadProofBitmap(dataUrlOrPath: String, baseUrl: String): Bitmap? = withContext(Dispatchers.IO) {
    decodeDataUrlBitmap(dataUrlOrPath)?.let { return@withContext it }
    if (!dataUrlOrPath.startsWith("/") && !dataUrlOrPath.startsWith("http")) return@withContext null
    val fullUrl = if (dataUrlOrPath.startsWith("http")) dataUrlOrPath else "${baseUrl.trimEnd('/')}$dataUrlOrPath"
    runCatching {
        val conn = (URL(fullUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 5000
            readTimeout = 8000
        }
        conn.inputStream.use { BitmapFactory.decodeStream(it) }
    }.getOrNull()
}

@Composable
fun Base64ProofImage(
    dataUrl: String,
    baseUrl: String = "",
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null
) {
    var bmp by remember(dataUrl, baseUrl) { mutableStateOf(decodeDataUrlBitmap(dataUrl)) }
    LaunchedEffect(dataUrl, baseUrl) {
        if (bmp == null) {
            bmp = loadProofBitmap(dataUrl, baseUrl)
        }
    }
    bmp?.let { loaded ->
        Image(
            bitmap = loaded.asImageBitmap(),
            contentDescription = "Visual Proof of Delivery",
            contentScale = ContentScale.Crop,
            modifier = modifier
                .clip(RoundedCornerShape(12.dp))
                .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
        )
    }
}

@Composable
fun ProofLightboxDialog(
    dataUrl: String,
    baseUrl: String = "",
    onDismiss: () -> Unit
) {
    var bmp by remember(dataUrl, baseUrl) { mutableStateOf(decodeDataUrlBitmap(dataUrl)) }
    LaunchedEffect(dataUrl, baseUrl) {
        if (bmp == null) {
            bmp = loadProofBitmap(dataUrl, baseUrl)
        }
    }
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xEE050811))
                .clickable { onDismiss() }
                .padding(16.dp),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                bmp?.let { loaded ->
                    Image(
                        bitmap = loaded.asImageBitmap(),
                        contentDescription = "Zoomed Proof Photo",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f, fill = false)
                            .clip(RoundedCornerShape(16.dp))
                    )
                }
                Spacer(Modifier.height(12.dp))
                OutlinedButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Close Proof Preview")
                }
            }
        }
    }
}

@Composable
fun CameraCaptureDialog(
    storeName: String,
    onCaptured: (Bitmap) -> Unit,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val pal = LocalDeliverExPalette.current
    var imageCapture by remember { mutableStateOf<ImageCapture?>(null) }
    var captureError by remember { mutableStateOf<String?>(null) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            shape = RoundedCornerShape(22.dp),
            color = Color(0xFF0A1120),
            border = BorderStroke(1.dp, pal.borderGlass)
        ) {
            Column(modifier = Modifier.fillMaxSize().padding(14.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Field Proof Camera (SOP-5.1)", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                        Text("Target store: $storeName", color = pal.cyan, fontSize = 12.sp)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close camera", tint = Color.White)
                    }
                }

                Spacer(Modifier.height(8.dp))

                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .border(1.dp, pal.cyan.copy(alpha = 0.5f), RoundedCornerShape(16.dp))
                ) {
                    val previewView = remember { PreviewView(context) }
                    DisposableEffect(lifecycleOwner) {
                        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
                        val executor = ContextCompat.getMainExecutor(context)
                        cameraProviderFuture.addListener({
                            runCatching {
                                val provider = cameraProviderFuture.get()
                                val preview = Preview.Builder().build().also {
                                    it.surfaceProvider = previewView.surfaceProvider
                                }
                                val cap = ImageCapture.Builder()
                                    .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                                    .build()
                                imageCapture = cap
                                provider.unbindAll()
                                provider.bindToLifecycle(
                                    lifecycleOwner,
                                    CameraSelector.DEFAULT_BACK_CAMERA,
                                    preview,
                                    cap
                                )
                            }.onFailure { err ->
                                captureError = "Camera unavailable: ${err.message}"
                            }
                        }, executor)
                        onDispose {
                            runCatching { cameraProviderFuture.get().unbindAll() }
                        }
                    }

                    AndroidView(
                        factory = { previewView },
                        modifier = Modifier.fillMaxSize()
                    )
                }

                captureError?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(it, color = pal.danger, fontSize = 12.sp)
                }

                Spacer(Modifier.height(12.dp))

                Button(
                    onClick = {
                        val cap = imageCapture ?: return@Button
                        val executor = ContextCompat.getMainExecutor(context)
                        cap.takePicture(executor, object : ImageCapture.OnImageCapturedCallback() {
                            override fun onCaptureSuccess(image: ImageProxy) {
                                val bmp = imageProxyToBitmap(image)
                                image.close()
                                if (bmp != null) {
                                    onCaptured(bmp)
                                } else {
                                    captureError = "Could not decode captured photo"
                                }
                            }

                            override fun onError(exception: ImageCaptureException) {
                                captureError = "Capture failed: ${exception.message}"
                            }
                        })
                    },
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = pal.primary)
                ) {
                    Icon(Icons.Default.CameraAlt, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Capture & Verify Damage Proof", fontWeight = FontWeight.ExtraBold)
                }
            }
        }
    }
}

private fun imageProxyToBitmap(image: ImageProxy): Bitmap? {
    val buffer = image.planes.firstOrNull()?.buffer ?: return null
    val bytes = ByteArray(buffer.remaining())
    buffer.get(bytes)
    val raw = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return null
    val rot = image.imageInfo.rotationDegrees
    if (rot == 0) return raw
    val matrix = Matrix().apply { postRotate(rot.toFloat()) }
    return Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true)
}

fun shareTextToWhatsApp(context: android.content.Context, text: String) {
    val waIntent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        setPackage("com.whatsapp")
        putExtra(Intent.EXTRA_TEXT, text)
    }
    runCatching {
        context.startActivity(waIntent)
    }.onFailure {
        val fallback = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        context.startActivity(Intent.createChooser(fallback, "Share Receipt"))
    }
}

@Composable
fun RoleSwitcherBar(
    activeRole: String,
    onSelectRole: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val pal = LocalDeliverExPalette.current
    val roles = listOf(
        Triple("DRIVER", "🚚 Driver", pal.success),
        Triple("MANAGER", "👩‍💼 Manager", pal.primary),
        Triple("DEMO", "🧪 Demo Mode", pal.cyan)
    )
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        roles.forEach { (key, label, accent) ->
            val selected = activeRole == key
            Surface(
                onClick = { onSelectRole(key) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(12.dp),
                color = if (selected) accent.copy(alpha = 0.22f) else Color(0x66111B2E),
                border = BorderStroke(1.dp, if (selected) accent else pal.borderGlass)
            ) {
                Box(
                    modifier = Modifier.padding(vertical = 8.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = label,
                        color = if (selected) Color.White else Color(0xFFCBD5E1),
                        fontSize = 11.sp,
                        fontWeight = if (selected) FontWeight.ExtraBold else FontWeight.Medium
                    )
                }
            }
        }
    }
}

@Composable
fun OnboardingScreen(
    initialName: String,
    initialLanguage: String,
    onComplete: (role: String, name: String, language: String) -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var selectedRole by remember { mutableStateOf("DRIVER") }
    var nameInput by remember { mutableStateOf(initialName) }
    var selectedLang by remember { mutableStateOf(initialLanguage) }
    val languages = listOf("Hinglish", "हिंदी", "Tanglish", "తెలుగు", "English")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(Color(0xFF060A13), Color(0xFF0D172B), Color(0xFF070B14)))
            )
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Spacer(Modifier.height(12.dp))
        Text("Namaste! 👋", color = pal.primary, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        Text("Welcome to DeliverEx Live", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.ExtraBold)
        Text(
            "Choose how you are using this phone today. You can switch anytime.",
            color = Color(0xFFCBD5E1),
            fontSize = 13.sp,
            lineHeight = 19.sp
        )

        listOf(
            Triple("DRIVER", "🚚 Field Driver (Raju)", "Talk in your language, report deliveries & snap damaged bag photos."),
            Triple("MANAGER", "👩‍💼 Manager / Owner (Priya)", "Approve discounts in 1 tap, track cash & export to Tally."),
            Triple("DEMO", "🧪 Judge / Demo Explorer", "Show guided demo triggers, live latency & full system telemetry.")
        ).forEach { (roleKey, title, desc) ->
            val selected = selectedRole == roleKey
            Surface(
                onClick = {
                    selectedRole = roleKey
                    if (roleKey == "MANAGER" && nameInput == "Raju Kumar") nameInput = "Priya Sharma"
                    if (roleKey == "DRIVER" && nameInput == "Priya Sharma") nameInput = "Raju Kumar"
                },
                shape = RoundedCornerShape(18.dp),
                color = if (selected) pal.primary.copy(alpha = 0.16f) else pal.surfaceGlass,
                border = BorderStroke(if (selected) 2.dp else 1.dp, if (selected) pal.primary else pal.borderGlass)
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(title, color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                    Spacer(Modifier.height(4.dp))
                    Text(desc, color = Color(0xFFCBD5E1), fontSize = 12.sp, lineHeight = 17.sp)
                }
            }
        }

        OutlinedTextField(
            value = nameInput,
            onValueChange = { nameInput = it },
            label = { Text("Your Name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        Text("Preferred Voice Language", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            languages.forEach { lang ->
                val sel = selectedLang == lang
                Surface(
                    onClick = { selectedLang = lang },
                    shape = RoundedCornerShape(50),
                    color = if (sel) pal.cyan.copy(alpha = 0.22f) else Color(0x66111B2E),
                    border = BorderStroke(1.dp, if (sel) pal.cyan else pal.borderGlass)
                ) {
                    Text(
                        lang,
                        color = if (sel) Color.White else Color(0xFFCBD5E1),
                        fontSize = 12.sp,
                        fontWeight = if (sel) FontWeight.Bold else FontWeight.Normal,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                    )
                }
            }
        }

        GlassCard(backgroundColor = Color(0xFF0E182B)) {
            Text(
                "🎙️ Mic & 📷 Camera are only used when you tap Start Call, Voice Note, or Damaged Bag Photo. Your records are encrypted and backed up safely.",
                color = Color(0xFFBAE6FD),
                fontSize = 11.sp,
                lineHeight = 16.sp
            )
        }

        Button(
            onClick = { onComplete(selectedRole, nameInput, selectedLang) },
            modifier = Modifier.fillMaxWidth().height(54.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = pal.primary, contentColor = Color(0xFF070B14))
        ) {
            Text("Continue to App →", fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
fun ServerAndPrivacyDialog(
    currentUrl: String,
    currentDriverName: String,
    offlineDemoMode: Boolean,
    activeThemeKey: String,
    onSelectTheme: (String) -> Unit,
    onSave: (url: String, driverName: String, offlineDemo: Boolean) -> Unit,
    onDismiss: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var urlInput by remember(currentUrl) { mutableStateOf(currentUrl) }
    var driverInput by remember(currentDriverName) { mutableStateOf(currentDriverName) }
    var offlineToggle by remember(offlineDemoMode) { mutableStateOf(offlineDemoMode) }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(22.dp),
            color = Color(0xFF0C1426),
            border = BorderStroke(1.dp, pal.borderGlass)
        ) {
            Column(
                modifier = Modifier
                    .padding(18.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text("App & Server Settings", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)

                OutlinedTextField(
                    value = urlInput,
                    onValueChange = { urlInput = it },
                    label = { Text("Server Address (Cloud Run / Local)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                OutlinedTextField(
                    value = driverInput,
                    onValueChange = { driverInput = it },
                    label = { Text("Your Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Offline Practice Mode", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                        Text("Try workflows locally without internet", color = Color(0xFF94A3B8), fontSize = 11.sp)
                    }
                    Switch(checked = offlineToggle, onCheckedChange = { offlineToggle = it })
                }

                Text("Color Theme", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    DELIVEREX_PALETTES.values.forEach { p ->
                        val selected = p.key == activeThemeKey
                        Box(
                            modifier = Modifier
                                .size(34.dp)
                                .clip(CircleShape)
                                .background(p.primary)
                                .border(
                                    width = if (selected) 3.dp else 1.dp,
                                    color = if (selected) Color.White else Color.White.copy(alpha = 0.25f),
                                    shape = CircleShape
                                )
                                .clickable { onSelectTheme(p.key) }
                        )
                    }
                }

                GlassCard(backgroundColor = Color(0xFF111C33)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.PrivacyTip, contentDescription = null, tint = pal.cyan, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(
                            text = stringResource(R.string.privacy_policy_title),
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = stringResource(R.string.privacy_policy_summary),
                        color = Color(0xFFCBD5E1),
                        fontSize = 11.sp,
                        lineHeight = 16.sp
                    )
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    OutlinedButton(onClick = onDismiss) {
                        Text("Cancel")
                    }
                    Spacer(Modifier.width(8.dp))
                    Button(
                        onClick = { onSave(urlInput, driverInput, offlineToggle) },
                        colors = ButtonDefaults.buttonColors(containerColor = pal.primary)
                    ) {
                        Text("Save & Sync", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
fun OwnerPinDialog(
    onUnlock: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var pin by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(22.dp),
            color = Color(0xFF0C1426),
            border = BorderStroke(1.dp, pal.borderGlass)
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Lock, contentDescription = null, tint = pal.primary, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Owner Auth (Priya Sharma)", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                }
                Text(
                    "Authenticate to authorize 1-Tap Approvals, export TallyPrime XML vouchers, and view Audit Vault hashes.",
                    color = Color(0xFFCBD5E1),
                    fontSize = 12.sp
                )
                OutlinedTextField(
                    value = pin,
                    onValueChange = { pin = it },
                    label = { Text("Owner PIN (demo: 4242)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = { onUnlock("4242") },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Demo PIN (4242)", fontSize = 11.sp)
                    }
                    Button(
                        onClick = { if (pin.isNotBlank()) onUnlock(pin) },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.primary)
                    ) {
                        Text("Unlock", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
fun ExportPreviewDialog(
    title: String,
    content: String,
    onDismiss: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    val context = LocalContext.current

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier.fillMaxSize().padding(16.dp),
            shape = RoundedCornerShape(22.dp),
            color = Color(0xFF0C1426),
            border = BorderStroke(1.dp, pal.borderGlass)
        ) {
            Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(title, color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }
                Spacer(Modifier.height(8.dp))
                Surface(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    color = Color(0xFF060A13),
                    border = BorderStroke(1.dp, pal.borderGlass)
                ) {
                    Text(
                        text = content,
                        color = Color(0xFFBAE6FD),
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.padding(12.dp).verticalScroll(rememberScrollState())
                    )
                }
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = {
                        val sendIntent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_SUBJECT, title)
                            putExtra(Intent.EXTRA_TEXT, content)
                        }
                        context.startActivity(Intent.createChooser(sendIntent, "Share $title"))
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = pal.cyan, contentColor = Color(0xFF070B14))
                ) {
                    Icon(Icons.Default.Share, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Share / Export File", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
