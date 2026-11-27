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
fun WorkerLogoBadge(
    size: androidx.compose.ui.unit.Dp = 34.dp,
    modifier: Modifier = Modifier
) {
    Image(
        painter = androidx.compose.ui.res.painterResource(id = R.drawable.ic_worker_logo),
        contentDescription = "Raju Bhai Worker Logo",
        modifier = modifier.size(size).clip(RoundedCornerShape(10.dp))
    )
}

@Composable
fun AppUpdateBanner(
    versionName: String,
    releaseNotes: String,
    downloadProgress: Int?,
    onUpdateClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val pal = LocalDeliverExPalette.current
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 4.dp),
        shape = RoundedCornerShape(14.dp),
        color = pal.primary.copy(alpha = 0.16f),
        border = BorderStroke(1.dp, pal.primary.copy(alpha = 0.65f))
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                    Text(
                        "🚀 Raju Bhai v$versionName Update Ready",
                        color = pal.primary,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 12.sp
                    )
                    if (releaseNotes.isNotBlank()) {
                        Text(
                            releaseNotes,
                            color = Color(0xFFE2E8F0),
                            fontSize = 11.sp,
                            maxLines = 2
                        )
                    }
                }
                Button(
                    onClick = onUpdateClick,
                    enabled = downloadProgress == null,
                    colors = ButtonDefaults.buttonColors(containerColor = pal.primary, contentColor = Color(0xFF070B14)),
                    shape = RoundedCornerShape(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = if (downloadProgress != null) "$downloadProgress%" else "Update Now",
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 11.sp
                    )
                }
            }
            if (downloadProgress != null) {
                Spacer(Modifier.height(6.dp))
                androidx.compose.material3.LinearProgressIndicator(
                    progress = { (downloadProgress.coerceIn(0, 100)) / 100f },
                    modifier = Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(4.dp)),
                    color = pal.primary,
                    trackColor = Color(0x33FFFFFF)
                )
            }
        }
    }
}

fun createTempCameraUri(context: android.content.Context): android.net.Uri {
    val dir = java.io.File(context.cacheDir, "camera").apply { mkdirs() }
    val file = java.io.File(dir, "proof_${System.currentTimeMillis()}.jpg")
    return androidx.core.content.FileProvider.getUriForFile(
        context,
        "${context.packageName}.fileprovider",
        file
    )
}

fun decodeBitmapFromUri(context: android.content.Context, uri: android.net.Uri): Bitmap? = runCatching {
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
        android.graphics.ImageDecoder.decodeBitmap(
            android.graphics.ImageDecoder.createSource(context.contentResolver, uri)
        ) { decoder, info, _ ->
            val maxDim = 1024
            val w = info.size.width
            val h = info.size.height
            if (w > maxDim || h > maxDim) {
                val scale = maxDim.toFloat() / maxOf(w, h).toFloat()
                decoder.setTargetSize((w * scale).toInt().coerceAtLeast(1), (h * scale).toInt().coerceAtLeast(1))
            }
            decoder.isMutableRequired = true
        }
    } else {
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) }
    }
}.getOrNull()

@Composable
fun DamagePhotoConfirmDialog(
    storeName: String,
    bitmap: Bitmap,
    uploading: Boolean,
    onConfirmUpload: (damagedBags: Int) -> Unit,
    onRetake: () -> Unit,
    onDismiss: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var damagedCount by remember { mutableStateOf(2) }

    Dialog(
        onDismissRequest = { if (!uploading) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(22.dp),
            color = Color(0xFF0C1426),
            border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.5f))
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Confirm Torn Bag Photo", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                        Text("Shop: $storeName", color = pal.cyan, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                    if (!uploading) {
                        IconButton(onClick = onDismiss) {
                            Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                        }
                    }
                }

                Image(
                    bitmap = bitmap.asImageBitmap(),
                    contentDescription = "Damaged bags preview",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(220.dp)
                        .clip(RoundedCornerShape(16.dp))
                        .border(1.dp, pal.borderGlass, RoundedCornerShape(16.dp))
                )

                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = Color(0xFF111C33),
                    border = BorderStroke(1.dp, pal.borderGlass)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("How many torn bags?", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            OutlinedButton(
                                onClick = { if (damagedCount > 1) damagedCount-- },
                                enabled = !uploading && damagedCount > 1,
                                shape = RoundedCornerShape(10.dp),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                            ) {
                                Text("−", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                            }
                            Text(
                                "$damagedCount",
                                color = pal.primary,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.ExtraBold
                            )
                            OutlinedButton(
                                onClick = { if (damagedCount < 50) damagedCount++ },
                                enabled = !uploading,
                                shape = RoundedCornerShape(10.dp),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                            ) {
                                Text("+", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                if (uploading) {
                    androidx.compose.material3.LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(4.dp)),
                        color = pal.success
                    )
                    Text("Uploading photo to Priya...", color = pal.cyan, fontSize = 12.sp)
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onRetake,
                        enabled = !uploading,
                        modifier = Modifier.height(50.dp),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Text("Retake", fontSize = 13.sp)
                    }
                    Button(
                        onClick = { onConfirmUpload(damagedCount) },
                        enabled = !uploading,
                        modifier = Modifier.weight(1f).height(50.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.success, contentColor = Color(0xFF070B14))
                    ) {
                        Text(
                            if (uploading) "Uploading..." else "✅ Upload Photo",
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 14.sp
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun LoginScreen(
    initialName: String,
    initialLanguage: String,
    onWorkerLogin: (name: String, language: String) -> Unit,
    onManagerLogin: (pin: String, onResult: (Boolean, String?) -> Unit) -> Unit,
    onDemoLogin: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var activePortal by remember { mutableStateOf("WORKER") } // WORKER | MANAGER | DEMO
    var workerName by remember { mutableStateOf(initialName.ifBlank { "Raju Kumar" }) }
    var selectedLang by remember { mutableStateOf(initialLanguage) }
    var managerPin by remember { mutableStateOf("") }
    var managerLoading by remember { mutableStateOf(false) }
    var managerError by remember { mutableStateOf<String?>(null) }
    val languages = listOf("Hinglish", "हिंदी", "Tanglish", "తెలుగు", "English")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(Color(0xFF060A13), Color(0xFF0D172B), Color(0xFF070B14)))
            )
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Spacer(Modifier.height(14.dp))
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            WorkerLogoBadge(size = 56.dp)
            Column {
                Text("Raju Bhai", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold)
                Text("Select your account to sign in", color = Color(0xFF94A3B8), fontSize = 13.sp)
            }
        }

        // Clean 3-Portal Account Selector
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            listOf(
                Triple("WORKER", "🚚 Worker", pal.success),
                Triple("MANAGER", "👩‍💼 Priya", pal.primary),
                Triple("DEMO", "🏆 Demo", pal.cyan)
            ).forEach { (id, label, accent) ->
                val sel = activePortal == id
                Surface(
                    onClick = {
                        activePortal = id
                        managerError = null
                    },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(14.dp),
                    color = if (sel) accent.copy(alpha = 0.22f) else Color(0x88111B2E),
                    border = BorderStroke(1.5.dp, if (sel) accent else pal.borderGlass)
                ) {
                    Box(
                        modifier = Modifier.padding(vertical = 12.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            label,
                            color = if (sel) Color.White else Color(0xFF94A3B8),
                            fontSize = 13.sp,
                            fontWeight = if (sel) FontWeight.ExtraBold else FontWeight.Medium
                        )
                    }
                }
            }
        }

        when (activePortal) {
            "WORKER" -> {
                GlassCard(borderColor = pal.success.copy(alpha = 0.5f)) {
                    Text("🚚 Delivery Worker Login", color = pal.success, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Simple voice call, torn bag photo upload, and WhatsApp updates — no manager clutter.",
                        color = Color(0xFFCBD5E1),
                        fontSize = 12.sp
                    )
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(
                        value = workerName,
                        onValueChange = { workerName = it },
                        label = { Text("Worker Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(12.dp))
                    Text("Voice Language", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Spacer(Modifier.height(6.dp))
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
                    Spacer(Modifier.height(16.dp))
                    Button(
                        onClick = { onWorkerLogin(workerName, selectedLang) },
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.success, contentColor = Color(0xFF070B14))
                    ) {
                        Text("Sign In as Worker →", fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                    }
                }
            }

            "MANAGER" -> {
                var pinVisible by remember { mutableStateOf(false) }
                var failedAttempts by remember { mutableStateOf(0) }
                var lockedUntilMs by remember { mutableStateOf(0L) }

                GlassCard(borderColor = pal.primary.copy(alpha = 0.55f)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text("🔒", fontSize = 16.sp)
                        Text("Priya Sharma • Secure Manager Login", color = pal.primary, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Authorized access only. Review driver damage photos, approve discounts, and download Tally / CSV reports.",
                        color = Color(0xFFCBD5E1),
                        fontSize = 12.sp
                    )
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(
                        value = managerPin,
                        onValueChange = { next ->
                            if (next.length <= 8 && next.all { it.isDigit() }) {
                                managerPin = next
                                managerError = null
                            }
                        },
                        label = { Text("Enter Manager PIN") },
                        singleLine = true,
                        visualTransformation = if (pinVisible) {
                            androidx.compose.ui.text.input.VisualTransformation.None
                        } else {
                            androidx.compose.ui.text.input.PasswordVisualTransformation()
                        },
                        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                            keyboardType = androidx.compose.ui.text.input.KeyboardType.NumberPassword
                        ),
                        trailingIcon = {
                            IconButton(onClick = { pinVisible = !pinVisible }) {
                                Text(if (pinVisible) "🙈" else "👁️", fontSize = 15.sp)
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    managerError?.let { err ->
                        Spacer(Modifier.height(6.dp))
                        Text(err, color = pal.danger, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                    Spacer(Modifier.height(14.dp))
                    Button(
                        onClick = {
                            val now = System.currentTimeMillis()
                            if (now < lockedUntilMs) {
                                val secs = ((lockedUntilMs - now) / 1000L).coerceAtLeast(1L)
                                managerError = "🔒 Too many wrong PINs. Try again in ${secs}s."
                                return@Button
                            }
                            if (managerPin.length < 4) {
                                managerError = "Please enter your 4+ digit Manager PIN."
                                return@Button
                            }
                            managerLoading = true
                            managerError = null
                            onManagerLogin(managerPin) { ok, err ->
                                managerLoading = false
                                if (!ok) {
                                    failedAttempts += 1
                                    managerPin = ""
                                    if (failedAttempts >= 5) {
                                        lockedUntilMs = System.currentTimeMillis() + 30_000L
                                        failedAttempts = 0
                                        managerError = "🔒 Too many wrong attempts. Locked for 30 seconds."
                                    } else {
                                        managerError = "${err ?: "Invalid Manager PIN"} (${5 - failedAttempts} tries left)"
                                    }
                                } else {
                                    failedAttempts = 0
                                }
                            }
                        },
                        enabled = !managerLoading,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.primary, contentColor = Color(0xFF070B14))
                    ) {
                        Text(
                            if (managerLoading) "Verifying PIN..." else "🔐 Unlock Manager Portal →",
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 15.sp
                        )
                    }
                }
            }

            else -> {
                GlassCard(borderColor = pal.cyan.copy(alpha = 0.55f)) {
                    Text("🏆 Hackathon Demo / Judge Preview", color = pal.cyan, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Watch every feature in one view: Live Gemini Voice Call, WhatsApp Ops, Priya's 1-Tap Approvals, Tally Export, Route Map, ROI Calculator & Guided Demo Steps.",
                        color = Color(0xFFCBD5E1),
                        fontSize = 12.sp,
                        lineHeight = 18.sp
                    )
                    Spacer(Modifier.height(16.dp))
                    Button(
                        onClick = onDemoLogin,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.cyan, contentColor = Color(0xFF070B14))
                    ) {
                        Text("Enter Hackathon Demo →", fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                    }
                }
            }
        }

        GlassCard(backgroundColor = Color(0xFF0E182B)) {
            Text(
                "🔒 Separate accounts keep Worker and Manager views clean. You can sign out & switch accounts anytime from the top bar.",
                color = Color(0xFFBAE6FD),
                fontSize = 11.sp,
                lineHeight = 16.sp
            )
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
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            WorkerLogoBadge(size = 48.dp)
            Column {
                Text("Namaste! 👋", color = pal.primary, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                Text("Welcome to Raju Bhai", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold)
            }
        }
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

private fun saveExportToDownloads(
    context: android.content.Context,
    fileName: String,
    mimeType: String,
    content: String
): Result<String> = runCatching {
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Downloads.DISPLAY_NAME, fileName)
            put(android.provider.MediaStore.Downloads.MIME_TYPE, mimeType)
            put(android.provider.MediaStore.Downloads.RELATIVE_PATH, android.os.Environment.DIRECTORY_DOWNLOADS)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("Could not create file in Downloads")
        resolver.openOutputStream(uri)?.use { out ->
            out.write(content.toByteArray(Charsets.UTF_8))
        } ?: error("Could not write file")
        fileName
    } else {
        @Suppress("DEPRECATION")
        val dir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
        dir.mkdirs()
        val file = java.io.File(dir, fileName)
        file.writeText(content, Charsets.UTF_8)
        file.name
    }
}

private fun shareExportedFile(
    context: android.content.Context,
    fileName: String,
    mimeType: String,
    content: String
) {
    runCatching {
        val dir = java.io.File(context.cacheDir, "exports").apply { mkdirs() }
        val file = java.io.File(dir, fileName)
        file.writeText(content, Charsets.UTF_8)
        val uri = androidx.core.content.FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file
        )
        val sendIntent = Intent(Intent.ACTION_SEND).apply {
            type = mimeType
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, fileName)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(sendIntent, "Share $fileName"))
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
    val isXml = title.contains("XML", ignoreCase = true) || content.trimStart().startsWith("<")
    val ext = if (isXml) "xml" else "csv"
    val mime = if (isXml) "application/xml" else "text/csv"
    val stamp = java.text.SimpleDateFormat("yyyyMMdd_HHmm", java.util.Locale.US).format(java.util.Date())
    val fileName = "RajuBhai_Ledger_$stamp.$ext"
    var downloadStatus by remember { mutableStateOf<String?>(null) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 28.dp),
            shape = RoundedCornerShape(20.dp),
            color = Color(0xFF0C1426),
            border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.45f))
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(title, color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                        Text(fileName, color = pal.cyan, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }

                // Scrollable both vertically AND horizontally so wide CSV columns stay crisp & un-zoomed
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(290.dp),
                    shape = RoundedCornerShape(12.dp),
                    color = Color(0xFF060A13),
                    border = BorderStroke(1.dp, pal.borderGlass)
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState())
                            .horizontalScroll(rememberScrollState())
                            .padding(10.dp)
                    ) {
                        Text(
                            text = content,
                            color = Color(0xFFBAE6FD),
                            fontSize = 10.sp,
                            lineHeight = 15.sp,
                            softWrap = false,
                            fontFamily = FontFamily.Monospace
                        )
                    }
                }

                downloadStatus?.let { status ->
                    Text(status, color = pal.success, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = {
                            saveExportToDownloads(context, fileName, mime, content)
                                .onSuccess { saved ->
                                    downloadStatus = "✅ Saved to Downloads/$saved"
                                    com.deliverex.live.update.AppNotificationManager.playInAppChime(context)
                                }
                                .onFailure { err ->
                                    downloadStatus = "Save failed: ${err.message}"
                                }
                        },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.success, contentColor = Color(0xFF070B14))
                    ) {
                        Text("⬇️ Download", fontWeight = FontWeight.ExtraBold, fontSize = 13.sp)
                    }
                    OutlinedButton(
                        onClick = { shareExportedFile(context, fileName, mime, content) },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.Share, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Share File", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }
            }
        }
    }
}
