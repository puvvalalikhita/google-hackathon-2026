package com.deliverex.live.ui.screens

import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deliverex.live.data.model.WhatsAppMessage
import com.deliverex.live.ui.DeliverExUiState
import com.deliverex.live.ui.components.Base64ProofImage
import com.deliverex.live.ui.components.GlassCard
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.theme.LocalDeliverExPalette

@Composable
fun WhatsAppOpsScreen(
    state: DeliverExUiState,
    onToggleVoiceRecord: () -> Unit,
    onSendWhatsApp: (String, Bitmap?) -> Unit,
    onOpenProofZoom: (String) -> Unit
) {
    val pal = LocalDeliverExPalette.current
    val context = LocalContext.current
    var inputText by remember { mutableStateOf("") }

    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            val bmp = runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    ImageDecoder.decodeBitmap(ImageDecoder.createSource(context.contentResolver, uri))
                } else {
                    @Suppress("DEPRECATION")
                    MediaStore.Images.Media.getBitmap(context.contentResolver, uri)
                }
            }.getOrNull()
            if (bmp != null) {
                onSendWhatsApp("${state.activeStore} ke damaged bags ki photo proof attach ki hai", bmp)
            }
        }
    }

    val cameraPreviewLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicturePreview()
    ) { bmp: Bitmap? ->
        if (bmp != null) {
            onSendWhatsApp("${state.activeStore} ke damaged bags ka camera photo proof", bmp)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(14.dp)) {
        GlassCard(borderColor = pal.success.copy(alpha = 0.4f)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "WHATSAPP BUSINESS FIELD OPS",
                        color = pal.success,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                    Text(
                        "Official Ops (+91-80-DELIVEREX)",
                        color = Color.White,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
                StatusPill(
                    text = state.erpState.whatsappSession?.workflowStage ?: "IDLE",
                    color = pal.cyan
                )
            }
            if (state.waSending) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = pal.success)
            }
        }

        Spacer(Modifier.height(8.dp))

        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            AssistChip(
                onClick = {
                    onSendWhatsApp(
                        "Shri Ganesh Stores pe 30 bags ACC cement deliver kar diya, 22000 cash received, koi damage nahi hai.",
                        null
                    )
                },
                label = { Text("⚡ Sample Note", fontSize = 11.sp) }
            )
            AssistChip(
                onClick = { onSendWhatsApp("${state.activeStore} ka balance kitna hai?", null) },
                label = { Text("Check Balance", fontSize = 11.sp) }
            )
            AssistChip(
                onClick = { cameraPreviewLauncher.launch(null) },
                leadingIcon = { Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(14.dp)) },
                label = { Text("Camera Proof", fontSize = 11.sp) }
            )
            AssistChip(
                onClick = { galleryLauncher.launch("image/*") },
                leadingIcon = { Icon(Icons.Default.PhotoLibrary, contentDescription = null, modifier = Modifier.size(14.dp)) },
                label = { Text("Gallery Photo", fontSize = 11.sp) }
            )
        }

        Spacer(Modifier.height(8.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(vertical = 4.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(state.erpState.whatsappMessages, key = { it.msgId }) { msg ->
                WhatsAppBubble(msg = msg, baseUrl = state.baseUrl, onOpenProofZoom = onOpenProofZoom)
            }
        }

        Spacer(Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(
                onClick = onToggleVoiceRecord,
                modifier = Modifier
                    .size(48.dp)
                    .background(
                        if (state.waRecording) pal.danger else Color(0xFF1E293B),
                        RoundedCornerShape(14.dp)
                    )
            ) {
                Icon(
                    imageVector = if (state.waRecording) Icons.Default.Stop else Icons.Default.Mic,
                    contentDescription = "Record voice note",
                    tint = Color.White
                )
            }
            Spacer(Modifier.width(8.dp))
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                placeholder = { Text("WhatsApp message in Hinglish / English...", fontSize = 13.sp) },
                modifier = Modifier.weight(1f),
                singleLine = true
            )
            Spacer(Modifier.width(8.dp))
            IconButton(
                onClick = {
                    if (inputText.isNotBlank()) {
                        onSendWhatsApp(inputText, null)
                        inputText = ""
                    }
                },
                modifier = Modifier
                    .size(48.dp)
                    .background(pal.success, RoundedCornerShape(14.dp))
            ) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send WhatsApp", tint = Color(0xFF070B14))
            }
        }
    }
}

@Composable
private fun WhatsAppBubble(
    msg: WhatsAppMessage,
    baseUrl: String,
    onOpenProofZoom: (String) -> Unit
) {
    val pal = LocalDeliverExPalette.current
    val isDriver = msg.sender == "driver"
    val isReceipt = msg.msgType == "receipt"
    val isManager = msg.sender == "manager"

    val bg = when {
        isDriver -> Color(0xFF0F3D2E)
        isReceipt -> Color(0xFF0A2E25)
        isManager -> Color(0xFF33230A)
        else -> Color(0xFF111B2E)
    }
    val border = when {
        isDriver -> pal.success.copy(alpha = 0.45f)
        isReceipt -> pal.success.copy(alpha = 0.7f)
        isManager -> pal.warning.copy(alpha = 0.5f)
        else -> pal.borderGlass
    }

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = bg,
        border = BorderStroke(1.dp, border),
        modifier = Modifier
            .fillMaxWidth()
            .padding(
                start = if (isDriver) 36.dp else 0.dp,
                end = if (isDriver) 0.dp else 20.dp
            )
    ) {
        Column(modifier = Modifier.padding(11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = when {
                        isDriver -> "🚚 ${msg.driverName}"
                        isManager -> "👩‍💼 Priya Sharma (Area Manager)"
                        else -> msg.metadata.senderLabel ?: "DeliverEx Official Ops"
                    },
                    color = when {
                        isManager -> pal.warning
                        isDriver -> pal.cyan
                        else -> pal.success
                    },
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
                if (isReceipt) {
                    StatusPill("OFFICIAL RECEIPT", pal.success)
                } else if (msg.metadata.processingMs != null) {
                    Text(
                        "⚡ ${msg.metadata.processingMs.toInt()}ms",
                        color = pal.cyan,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            if (msg.msgType == "image" && !msg.mediaDataUrl.isNullOrBlank()) {
                Base64ProofImage(
                    dataUrl = msg.mediaDataUrl,
                    baseUrl = baseUrl,
                    modifier = Modifier.fillMaxWidth().height(130.dp),
                    onClick = { onOpenProofZoom(msg.mediaDataUrl) }
                )
            }

            Text(msg.body, color = Color(0xFFF1F5F9), fontSize = 13.sp, lineHeight = 18.sp)

            Text(
                text = msg.createdAt.substringAfter(" ").take(5) + if (isDriver) "  ✓✓" else "",
                color = Color(0xFF94A3B8),
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.align(Alignment.End)
            )
        }
    }
}
