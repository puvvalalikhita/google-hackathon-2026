package com.deliverex.live.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deliverex.live.data.model.TranscriptMessage
import com.deliverex.live.ui.DeliverExUiState
import com.deliverex.live.ui.components.GlassCard
import com.deliverex.live.ui.components.LatencySparkline
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.components.VoiceOrbVisualizer
import com.deliverex.live.ui.theme.LocalDeliverExPalette

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveCallScreen(
    state: DeliverExUiState,
    onToggleCall: () -> Unit,
    onToggleMute: () -> Unit,
    onEndTurn: () -> Unit,
    onToggleNoise: () -> Unit,
    onSelectStore: (String) -> Unit,
    onSelectLanguage: (String) -> Unit,
    onToggleDemoControls: () -> Unit,
    onRunGuidedStep: (Int) -> Unit,
    onSendTextTurn: (String) -> Unit,
    onOpenCameraProof: () -> Unit,
    onOpenGalleryProof: () -> Unit,
    onOpenProofZoom: (String) -> Unit,
    onSendSampleDamageProof: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var textInput by remember { mutableStateOf("") }
    var storeDropdownExpanded by remember { mutableStateOf(false) }

    val languages = listOf("Hinglish", "हिंदी", "Tanglish", "తెలుగు", "English")
    val stores = remember(state.erpState.customers) {
        state.erpState.customers.map { it.name }.ifEmpty {
            listOf("Krishna Hardware", "Shri Ganesh Stores", "Bharat Traders", "Murugan Builders")
        }
    }

    val mm = (state.callSeconds / 60).toString().padStart(2, '0')
    val ss = (state.callSeconds % 60).toString().padStart(2, '0')

    val friendlyStatus = when {
        !state.callActive -> "Tap Start Call & speak in ${state.preferredLanguage}"
        state.micMuted -> "🔇 Mic muted — tap Unmute to speak"
        state.voiceStage.contains("SPEAK", ignoreCase = true) -> "🔊 AI Speaking — speak anytime to interrupt"
        state.voiceStage.contains("BARGE", ignoreCase = true) -> "⚡ Caught your interruption — listening"
        else -> "🎙️ Listening — speak naturally in ${state.preferredLanguage}"
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // 1. Language Selector Chips
        item {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                languages.forEach { lang ->
                    val selected = state.preferredLanguage == lang
                    Surface(
                        onClick = { onSelectLanguage(lang) },
                        shape = RoundedCornerShape(50),
                        color = if (selected) pal.cyan.copy(alpha = 0.22f) else Color(0x66111B2E),
                        border = BorderStroke(1.dp, if (selected) pal.cyan else pal.borderGlass)
                    ) {
                        Text(
                            text = lang,
                            color = if (selected) Color.White else Color(0xFFCBD5E1),
                            fontSize = 11.sp,
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                        )
                    }
                }
            }
        }

        // 2. Hero Voice Call Card (Clean, thumb-friendly 54dp buttons)
        item {
            GlassCard(
                borderColor = if (state.callActive) pal.cyan.copy(alpha = 0.55f) else pal.borderGlass
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (state.callActive) "VOICE CALL LIVE • $mm:$ss" else "DELIVERY VOICE ASSISTANT",
                            color = if (state.callActive) pal.success else pal.primary,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.ExtraBold,
                            fontFamily = FontFamily.Monospace
                        )
                        Text(
                            text = "${state.driverName} • ${state.activeStore}",
                            color = Color.White,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    if (state.showDemoControls) {
                        StatusPill(
                            text = "${state.noiseFloorDb} dB",
                            color = if (state.noiseFloorDb >= 70) pal.warning else pal.cyan
                        )
                    }
                }

                Spacer(Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    VoiceOrbVisualizer(
                        energy = if (state.micMuted) 0.02f else state.voiceEnergy,
                        callActive = state.callActive,
                        stage = state.voiceStage,
                        modifier = Modifier.size(96.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            text = friendlyStatus,
                            color = Color.White,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            lineHeight = 18.sp
                        )
                        if (state.showDemoControls) {
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                StatusPill("TTFA ${state.latencyHistory.lastOrNull() ?: 290}ms", pal.success)
                                StatusPill("⚡ ${state.interruptionCount} Barge-In", pal.warning)
                            }
                            LatencySparkline(
                                values = state.latencyHistory,
                                modifier = Modifier.fillMaxWidth().height(22.dp)
                            )
                        } else {
                            Text(
                                text = "Tell me shop name, bags delivered, damaged bags, or cash collected.",
                                color = Color(0xFF94A3B8),
                                fontSize = 11.sp,
                                lineHeight = 15.sp
                            )
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onToggleCall,
                        modifier = Modifier.weight(1f).height(54.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (state.callActive) pal.danger else pal.success,
                            contentColor = Color(0xFF070B14)
                        ),
                        shape = RoundedCornerShape(16.dp)
                    ) {
                        Icon(
                            if (state.callActive) Icons.Default.CallEnd else Icons.Default.Call,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (state.callActive) "End Call" else "Start Voice Call",
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 15.sp
                        )
                    }

                    if (state.callActive) {
                        OutlinedButton(
                            onClick = onToggleMute,
                            modifier = Modifier.height(54.dp),
                            shape = RoundedCornerShape(16.dp)
                        ) {
                            Icon(
                                if (state.micMuted) Icons.Default.MicOff else Icons.Default.Mic,
                                contentDescription = "Mute toggle",
                                tint = if (state.micMuted) pal.danger else Color.White,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }

                    if (state.callActive && state.liveGeminiReady && state.showDemoControls) {
                        OutlinedButton(
                            onClick = onEndTurn,
                            modifier = Modifier.height(54.dp),
                            shape = RoundedCornerShape(16.dp)
                        ) {
                            Icon(Icons.Default.RecordVoiceOver, contentDescription = null, modifier = Modifier.size(18.dp))
                        }
                    }

                    if (state.showDemoControls) {
                        OutlinedButton(
                            onClick = onToggleNoise,
                            modifier = Modifier.height(54.dp),
                            shape = RoundedCornerShape(16.dp)
                        ) {
                            Icon(Icons.Default.GraphicEq, contentDescription = null, modifier = Modifier.size(18.dp))
                        }
                    }
                }
            }
        }

        // 3. Shop Selection & Damaged Bag Photo
        item {
            GlassCard {
                Text(
                    "SHOP & DAMAGED BAG PHOTO",
                    color = pal.secondary,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(6.dp))
                ExposedDropdownMenuBox(
                    expanded = storeDropdownExpanded,
                    onExpandedChange = { storeDropdownExpanded = !storeDropdownExpanded }
                ) {
                    OutlinedTextField(
                        value = state.activeStore,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Select Delivery Shop") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = storeDropdownExpanded) },
                        modifier = Modifier
                            .menuAnchor(MenuAnchorType.PrimaryNotEditable, enabled = true)
                            .fillMaxWidth(),
                        singleLine = true
                    )
                    ExposedDropdownMenu(
                        expanded = storeDropdownExpanded,
                        onDismissRequest = { storeDropdownExpanded = false }
                    ) {
                        stores.forEach { store ->
                            DropdownMenuItem(
                                text = { Text(store) },
                                onClick = {
                                    onSelectStore(store)
                                    storeDropdownExpanded = false
                                }
                            )
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onOpenCameraProof,
                        enabled = !state.photoUploading,
                        modifier = Modifier.weight(1f).height(50.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.cyan, contentColor = Color(0xFF070B14)),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Take Photo", fontWeight = FontWeight.ExtraBold, fontSize = 13.sp)
                    }

                    OutlinedButton(
                        onClick = onOpenGalleryProof,
                        enabled = !state.photoUploading,
                        modifier = Modifier.weight(1f).height(50.dp),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(Icons.Default.Image, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Gallery", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }

                if (state.userRole == "DEMO") {
                    Spacer(Modifier.height(6.dp))
                    OutlinedButton(
                        onClick = onSendSampleDamageProof,
                        enabled = !state.photoUploading,
                        modifier = Modifier.fillMaxWidth().height(42.dp),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("🧪 Send Sample Torn Bag Photo (Demo)", fontSize = 12.sp)
                    }
                }

                if (state.photoUploading) {
                    Spacer(Modifier.height(8.dp))
                    androidx.compose.material3.LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth(),
                        color = pal.cyan
                    )
                    Spacer(Modifier.height(4.dp))
                    Text("⏳ Uploading torn bag photo to Priya...", color = pal.cyan, fontSize = 11.sp)
                }

                state.lastUploadedProofUrl?.let { uploadedUrl ->
                    Spacer(Modifier.height(10.dp))
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = pal.success.copy(alpha = 0.12f),
                        border = BorderStroke(1.dp, pal.success.copy(alpha = 0.45f))
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            com.deliverex.live.ui.components.Base64ProofImage(
                                dataUrl = uploadedUrl,
                                baseUrl = state.baseUrl,
                                modifier = Modifier.size(56.dp),
                                onClick = { onOpenProofZoom(uploadedUrl) }
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text("✅ Photo Uploaded", color = pal.success, fontWeight = FontWeight.ExtraBold, fontSize = 12.sp)
                                Text("Sent to Priya for ${state.activeStore}. Tap thumbnail to preview.", color = Color(0xFFCBD5E1), fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        }

        // 4. Helpful Tip Card (Plain Language)
        item {
            GlassCard(borderColor = pal.cyan.copy(alpha = 0.35f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "💡 HELPFUL TIP FOR YOU",
                        color = pal.cyan,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                    StatusPill(state.guidance.language, pal.secondary)
                }
                Spacer(Modifier.height(6.dp))
                Text(state.guidance.coachTip, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                if (state.guidance.suggestedPhrase.isNotBlank()) {
                    Spacer(Modifier.height(8.dp))
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = pal.cyan.copy(alpha = 0.1f),
                        border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.25f))
                    ) {
                        Text(
                            text = "💬 Tell shopkeeper: \"${state.guidance.suggestedPhrase}\"",
                            color = Color(0xFFE0F2FE),
                            fontSize = 12.sp,
                            modifier = Modifier.padding(10.dp)
                        )
                    }
                }
            }
        }

        // 5. Conversation & Type Message Box
        item {
            GlassCard {
                Text(
                    "CONVERSATION",
                    color = pal.secondary,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(8.dp))

                if (state.transcripts.isEmpty()) {
                    Text(
                        "Your voice conversation or typed delivery updates will appear here.",
                        color = Color(0xFF94A3B8),
                        fontSize = 12.sp
                    )
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        state.transcripts.takeLast(10).forEach { msg ->
                            TranscriptBubble(msg)
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = textInput,
                        onValueChange = { textInput = it },
                        placeholder = { Text("Type update in ${state.preferredLanguage}...", fontSize = 13.sp) },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    Spacer(Modifier.width(6.dp))
                    IconButton(
                        onClick = {
                            if (textInput.isNotBlank()) {
                                onSendTextTurn(textInput)
                                textInput = ""
                            }
                        },
                        modifier = Modifier
                            .size(50.dp)
                            .background(pal.primary, RoundedCornerShape(14.dp))
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send update", tint = Color(0xFF070B14))
                    }
                }
            }
        }

        // 6. Demo / Judge Shortcuts (Shown ONLY in Hackathon Demo login)
        if (state.userRole == "DEMO") {
            item {
                GlassCard(backgroundColor = Color(0x880B1220)) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onToggleDemoControls() },
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "🧪 Demo & Test Shortcuts",
                            color = pal.primary,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Icon(
                            if (state.showDemoControls) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                            contentDescription = null,
                            tint = Color.White
                        )
                    }

                    if (state.showDemoControls) {
                        Spacer(Modifier.height(10.dp))
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            GuidedStepChip("1. Deliver 20 Bags", pal.success) { onRunGuidedStep(1) }
                            GuidedStepChip("2. ⚡ Interrupt (2 Torn + ₹500)", pal.warning) { onRunGuidedStep(2) }
                            GuidedStepChip("3. Escalate Priya", pal.danger) { onRunGuidedStep(3) }
                            GuidedStepChip("4. Chennai Tanglish", pal.cyan) { onRunGuidedStep(4) }
                        }
                    }
                }
            }
        }

        if (state.showDemoControls && state.toolLogs.isNotEmpty()) {
            item {
                Text(
                    "RECENT AGENT TOOL CALLS",
                    color = Color(0xFF94A3B8),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
            }
            items(state.toolLogs.take(5), key = { it.id }) { log ->
                GlassCard(backgroundColor = Color(0xAA0B1324)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("⚙ ${log.name}()", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        StatusPill(
                            text = if (log.elapsedMs != null) "${log.status} • ${log.elapsedMs.toInt()}ms" else log.status,
                            color = if (log.status == "ESCALATED") pal.warning else pal.success
                        )
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(log.argsSummary, color = Color(0xFF94A3B8), fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                }
            }
        }
    }
}

@Composable
private fun GuidedStepChip(
    label: String,
    accent: Color,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(12.dp),
        color = accent.copy(alpha = 0.16f),
        border = BorderStroke(1.dp, accent.copy(alpha = 0.45f))
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Default.FlashOn, contentDescription = null, tint = accent, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(4.dp))
            Text(label, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun TranscriptBubble(msg: TranscriptMessage) {
    val pal = LocalDeliverExPalette.current
    when (msg.role) {
        "barge_in" -> {
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                StatusPill("⚡ You interrupted — AI updated", pal.warning)
            }
        }
        "system" -> {
            Surface(
                shape = RoundedCornerShape(10.dp),
                color = pal.cyan.copy(alpha = 0.12f),
                border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.25f))
            ) {
                Text(
                    msg.text,
                    color = Color(0xFFBAE6FD),
                    fontSize = 11.sp,
                    modifier = Modifier.padding(8.dp)
                )
            }
        }
        "user" -> {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = Color(0xFF16243D),
                border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.35f)),
                modifier = Modifier.fillMaxWidth().padding(start = 24.dp)
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Text("🚚 YOU", color = pal.cyan, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(2.dp))
                    Text(msg.text, color = Color.White, fontSize = 13.sp, lineHeight = 18.sp)
                }
            }
        }
        else -> {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = Color(0xFF0A2622),
                border = BorderStroke(1.dp, pal.success.copy(alpha = 0.4f)),
                modifier = Modifier.fillMaxWidth().padding(end = 24.dp)
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Text("🤖 DELIVEREX ASSISTANT", color = pal.success, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(2.dp))
                    Text(msg.text, color = Color(0xFFECFDF5), fontSize = 13.sp, lineHeight = 18.sp)
                }
            }
        }
    }
}
