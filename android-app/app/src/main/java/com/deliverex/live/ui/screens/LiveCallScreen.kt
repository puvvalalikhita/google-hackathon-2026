package com.deliverex.live.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
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
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
    onEndTurn: () -> Unit,
    onToggleNoise: () -> Unit,
    onSelectStore: (String) -> Unit,
    onRunGuidedStep: (Int) -> Unit,
    onSendTextTurn: (String) -> Unit,
    onOpenCameraProof: () -> Unit,
    onSendSampleDamageProof: () -> Unit
) {
    val pal = LocalDeliverExPalette.current
    var textInput by remember { mutableStateOf("") }
    var storeDropdownExpanded by remember { mutableStateOf(false) }

    val stores = remember(state.erpState.customers) {
        state.erpState.customers.map { it.name }.ifEmpty {
            listOf("Krishna Hardware", "Shri Ganesh Stores", "Bharat Traders", "Murugan Builders")
        }
    }

    val mm = (state.callSeconds / 60).toString().padStart(2, '0')
    val ss = (state.callSeconds % 60).toString().padStart(2, '0')

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // 1. Live Voice Call Hero Card
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
                            text = if (state.callActive) state.voiceStage else "GEMINI LIVE VOICE AGENT",
                            color = if (state.callActive) pal.cyan else pal.primary,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.ExtraBold,
                            fontFamily = FontFamily.Monospace
                        )
                        Text(
                            text = "${state.driverName} • $mm:$ss",
                            color = Color.White,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    StatusPill(
                        text = "${state.noiseFloorDb} dB",
                        color = if (state.noiseFloorDb >= 70) pal.warning else pal.cyan
                    )
                }

                Spacer(Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    VoiceOrbVisualizer(
                        energy = state.voiceEnergy,
                        callActive = state.callActive,
                        stage = state.voiceStage,
                        modifier = Modifier.size(110.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            text = state.voiceStageDetail,
                            color = Color(0xFFE2E8F0),
                            fontSize = 12.sp,
                            lineHeight = 16.sp
                        )
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            StatusPill(
                                text = "TTFA ${state.latencyHistory.lastOrNull() ?: 290}ms",
                                color = pal.success
                            )
                            StatusPill(
                                text = "⚡ ${state.interruptionCount} Barge-In",
                                color = pal.warning
                            )
                        }
                        LatencySparkline(
                            values = state.latencyHistory,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(26.dp)
                        )
                    }
                }

                Spacer(Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onToggleCall,
                        modifier = Modifier.weight(1f).height(46.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (state.callActive) pal.danger else pal.success,
                            contentColor = Color(0xFF070B14)
                        ),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(
                            if (state.callActive) Icons.Default.CallEnd else Icons.Default.Call,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(
                            if (state.callActive) "End Call" else "Start Live Call",
                            fontWeight = FontWeight.ExtraBold
                        )
                    }

                    if (state.callActive && state.liveGeminiReady) {
                        OutlinedButton(
                            onClick = onEndTurn,
                            modifier = Modifier.height(46.dp),
                            shape = RoundedCornerShape(14.dp)
                        ) {
                            Icon(Icons.Default.RecordVoiceOver, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("End Turn", fontSize = 12.sp)
                        }
                    }

                    OutlinedButton(
                        onClick = onToggleNoise,
                        modifier = Modifier.height(46.dp),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(Icons.Default.GraphicEq, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(if (state.noiseFloorDb >= 70) "78dB" else "Noise", fontSize = 12.sp)
                    }
                }
            }
        }

        // 2. Active Store Selector + Camera POD Controls
        item {
            GlassCard {
                Text(
                    "TARGET STORE & VISION PROOF (SOP-5.1)",
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
                        label = { Text("Active Delivery Store") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = storeDropdownExpanded) },
                        modifier = Modifier
                            .menuAnchor()
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

                Spacer(Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onOpenCameraProof,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.cyan, contentColor = Color(0xFF070B14)),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Camera POD", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }

                    OutlinedButton(
                        onClick = onSendSampleDamageProof,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.Image, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("2 Torn Bags Demo", fontSize = 12.sp)
                    }
                }
            }
        }

        // 3. Guided Demo Triggers (Steps 1–4)
        item {
            GlassCard {
                Text(
                    "LIVE FIELD TRIGGERS (HINGLISH / TANGLISH)",
                    color = pal.primary,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(8.dp))
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

        // 4. Frontline Staff Coach HUD
        item {
            GlassCard(borderColor = pal.cyan.copy(alpha = 0.35f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "FRONTLINE STAFF COACH HUD",
                        color = pal.cyan,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        StatusPill(state.guidance.language, pal.secondary)
                        StatusPill(
                            state.guidance.sentiment,
                            when (state.guidance.sentiment.uppercase()) {
                                "FRUSTRATED" -> pal.danger
                                "CONCERNED" -> pal.warning
                                "RESOLVED" -> pal.success
                                else -> pal.cyan
                            }
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text(state.guidance.coachTip, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(6.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = pal.cyan.copy(alpha = 0.1f),
                    border = BorderStroke(1.dp, pal.cyan.copy(alpha = 0.25f))
                ) {
                    Text(
                        text = "💬 Say: \"${state.guidance.suggestedPhrase}\"",
                        color = Color(0xFFE0F2FE),
                        fontSize = 12.sp,
                        modifier = Modifier.padding(10.dp)
                    )
                }
            }
        }

        // 5. Transcript & Input Bar
        item {
            GlassCard {
                Text(
                    "LIVE CALL TRANSCRIPT",
                    color = pal.secondary,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(8.dp))

                if (state.transcripts.isEmpty()) {
                    Text(
                        "Tap Start Live Call or choose a Field Trigger above to see real-time Hinglish/Tanglish conversation & SOP grounding.",
                        color = Color(0xFF94A3B8),
                        fontSize = 12.sp
                    )
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        state.transcripts.takeLast(12).forEach { msg ->
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
                        placeholder = { Text("Speak or type Hinglish / Tanglish...", fontSize = 13.sp) },
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
                            .size(48.dp)
                            .background(pal.primary, RoundedCornerShape(14.dp))
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send turn", tint = Color(0xFF070B14))
                    }
                }
            }
        }

        // 6. Tool Execution Feed
        if (state.toolLogs.isNotEmpty()) {
            item {
                Text(
                    "RECENT AGENT TOOL CALLS",
                    color = Color(0xFF94A3B8),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
            }
            items(state.toolLogs.take(6), key = { it.id }) { log ->
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
                StatusPill(msg.text, pal.warning)
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
                    Text("🚚 RAJU (DRIVER)", color = pal.cyan, fontSize = 9.sp, fontWeight = FontWeight.Bold)
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
                    Text("🤖 DELIVEREX LIVE AI", color = pal.success, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(2.dp))
                    Text(msg.text, color = Color(0xFFECFDF5), fontSize = 13.sp, lineHeight = 18.sp)
                }
            }
        }
    }
}
