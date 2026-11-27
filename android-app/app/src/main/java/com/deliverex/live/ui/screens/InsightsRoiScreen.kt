package com.deliverex.live.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.RestartAlt
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deliverex.live.ui.DeliverExUiState
import com.deliverex.live.ui.components.GlassCard
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.theme.LocalDeliverExPalette
import com.deliverex.live.ui.theme.formatInrLong
import kotlin.math.roundToInt

@Composable
fun InsightsRoiScreen(
    state: DeliverExUiState,
    onUpdateDailyCalls: (Int) -> Unit,
    onResetDemo: () -> Unit,
    onOpenSettings: () -> Unit,
    onCheckUpdate: () -> Unit,
    onTestNotification: () -> Unit
) {
    val pal = LocalDeliverExPalette.current

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // 1. Interactive Route Map
        item {
            GlassCard(borderColor = pal.cyan.copy(alpha = 0.4f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("ROUTE MAP", color = pal.cyan, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                    StatusPill(state.activeStore, pal.primary)
                }
                Spacer(Modifier.height(10.dp))
                RouteRadarCanvas(
                    state = state,
                    modifier = Modifier.fillMaxWidth().height(145.dp)
                )
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("● Settled", color = pal.success, fontSize = 10.sp)
                    Text("● Needs Approval", color = pal.warning, fontSize = 10.sp)
                    Text("● Open Dispatch", color = pal.cyan, fontSize = 10.sp)
                }
            }
        }

        // 2. Monthly Savings Calculator
        item {
            GlassCard(borderColor = pal.primary.copy(alpha = 0.45f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("MONTHLY SAVINGS CALCULATOR", color = pal.primary, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                    StatusPill("${state.roi.roiMultiple}x ROI", pal.success)
                }
                Spacer(Modifier.height(8.dp))
                Text("Daily Driver Calls: ${state.roi.dailyCalls}", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                Slider(
                    value = state.roi.dailyCalls.toFloat(),
                    onValueChange = { onUpdateDailyCalls(it.roundToInt()) },
                    valueRange = 25f..1000f
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Manual Desk Cost", color = Color(0xFF94A3B8), fontSize = 10.sp)
                        Text("₹30.00 / call", color = pal.danger, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                    Column {
                        Text("Raju Bhai AI", color = Color(0xFF94A3B8), fontSize = 10.sp)
                        Text("₹2.20 / call", color = pal.cyan, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Monthly Savings", color = Color(0xFF94A3B8), fontSize = 10.sp)
                        Text(formatInrLong(state.roi.monthlySavingsInr), color = pal.success, fontWeight = FontWeight.ExtraBold, fontSize = 14.sp)
                    }
                }
            }
        }

        // 3. Route Alerts
        item {
            Text(
                "ROUTE ALERTS",
                color = pal.secondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.ExtraBold
            )
        }
        items(state.erpState.insights, key = { "${it.insightId}_${it.title}" }) { ins ->
            val sevColor = when (ins.severity.uppercase()) {
                "HIGH" -> pal.danger
                "MEDIUM" -> pal.warning
                else -> pal.cyan
            }
            GlassCard {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(ins.title, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp, modifier = Modifier.weight(1f))
                    StatusPill(ins.severity, sevColor)
                }
                Spacer(Modifier.height(4.dp))
                Text(ins.detail, color = Color(0xFFCBD5E1), fontSize = 12.sp, lineHeight = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text("${ins.route} • ${ins.category}", color = Color(0xFF94A3B8), fontSize = 10.sp, fontFamily = FontFamily.Monospace)
            }
        }

        // 4. Protected Records & Cloud Backup
        state.erpState.auditSummary?.let { audit ->
            item {
                GlassCard(borderColor = if (audit.chainVerified) pal.success.copy(alpha = 0.45f) else pal.danger.copy(alpha = 0.6f)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "🔒 Protected Records (Tamper-Proof)",
                            color = pal.cyan,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.ExtraBold
                        )
                        StatusPill(
                            text = if (audit.chainVerified) "All ${audit.totalCount} Verified" else "Check Needed",
                            color = if (audit.chainVerified) pal.success else pal.danger
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "All ${audit.totalCount} records verified & safely backed up (${(state.health.storageMode.ifBlank { audit.storageBackend }).uppercase()}).",
                        color = Color(0xFFE2E8F0),
                        fontSize = 12.sp
                    )
                    if (state.showDemoControls) {
                        Spacer(Modifier.height(8.dp))
                        audit.latest.take(4).forEach { entry ->
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = Color(0x550B1220),
                                border = BorderStroke(1.dp, pal.borderGlass),
                                modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)
                            ) {
                                Column(modifier = Modifier.padding(8.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text("${entry.auditId} • ${entry.action}", color = pal.cyan, fontSize = 10.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
                                        Text(entry.role, color = pal.success, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
                                    }
                                    Text(entry.summary, color = Color(0xFFE2E8F0), fontSize = 11.sp)
                                    Text("Actor: ${entry.actor} • ${entry.integrityHash.take(14)}...", color = Color(0xFF94A3B8), fontSize = 9.sp, fontFamily = FontFamily.Monospace)
                                }
                            }
                        }
                    }
                }
            }
        }

        // 5. App Connection & Controls
        item {
            GlassCard {
                Text("APP CONNECTION & SERVER", color = pal.cyan, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                Spacer(Modifier.height(6.dp))
                Text(
                    text = if (state.backendConnected) {
                        "Connected to Cloud Server (${state.health.authMode})"
                    } else {
                        "Offline Practice Mode (${state.baseUrl})"
                    },
                    color = Color(0xFFE2E8F0),
                    fontSize = 12.sp
                )
                state.goLiveCheck?.let { gl ->
                    Spacer(Modifier.height(8.dp))
                    gl.checks.forEach { chk ->
                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = Color(0x550B1220),
                            border = BorderStroke(1.dp, if (chk.ok) pal.success.copy(alpha = 0.35f) else pal.warning.copy(alpha = 0.35f)),
                            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(chk.label, color = Color.White, fontSize = 11.sp, modifier = Modifier.weight(1f))
                                StatusPill(if (chk.ok) "PASS" else "WARN", if (chk.ok) pal.success else pal.warning)
                            }
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onCheckUpdate,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text(if (state.checkingUpdate) "Checking..." else "🔄 Check Update", color = pal.cyan, fontSize = 12.sp)
                    }
                    OutlinedButton(
                        onClick = onTestNotification,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("🔔 Test Sound", color = pal.primary, fontSize = 12.sp)
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onOpenSettings,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = pal.primary, contentColor = Color(0xFF070B14)),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.Settings, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Server & Privacy", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }
                    OutlinedButton(
                        onClick = onResetDemo,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.RestartAlt, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Reset Demo", fontSize = 12.sp)
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "Raju Bhai v${com.deliverex.live.BuildConfig.VERSION_NAME} • Auto-Update Notifications Enabled",
                    color = Color(0xFF94A3B8),
                    fontSize = 10.sp
                )
            }
        }
    }
}

@Composable
private fun RouteRadarCanvas(
    state: DeliverExUiState,
    modifier: Modifier = Modifier
) {
    val pal = LocalDeliverExPalette.current
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val gridPaintColor = Color.White.copy(alpha = 0.08f)

        for (i in 1..3) {
            drawLine(gridPaintColor, Offset(0f, h * i / 4f), Offset(w, h * i / 4f), strokeWidth = 1f)
            drawLine(gridPaintColor, Offset(w * i / 4f, 0f), Offset(w * i / 4f, h), strokeWidth = 1f)
        }

        val coords = mapOf(
            "Krishna Hardware" to Offset(w * 0.18f, h * 0.34f),
            "Shri Ganesh Stores" to Offset(w * 0.48f, h * 0.38f),
            "Bharat Traders" to Offset(w * 0.80f, h * 0.28f),
            "Murugan Builders" to Offset(w * 0.78f, h * 0.78f)
        )

        val routePoints = listOf("Krishna Hardware", "Shri Ganesh Stores", "Bharat Traders", "Murugan Builders")
        for (i in 0 until routePoints.lastIndex) {
            val a = coords[routePoints[i]]!!
            val b = coords[routePoints[i + 1]]!!
            drawLine(
                color = pal.cyan.copy(alpha = 0.45f),
                start = a,
                end = b,
                strokeWidth = 3f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))
            )
        }

        state.erpState.customers.forEach { cust ->
            val pos = coords[cust.name] ?: return@forEach
            val isPending = state.erpState.approvals.any { it.customerId == cust.customerId && it.status == "PENDING" }
            val pinColor = when {
                cust.balanceDue == 0 -> pal.success
                isPending -> pal.warning
                else -> pal.cyan
            }
            drawCircle(pinColor.copy(alpha = 0.25f), radius = 22f, center = pos)
            drawCircle(pinColor, radius = 9f, center = pos)
            if (cust.name == state.activeStore) {
                drawCircle(Color.White, radius = 14f, center = pos, style = androidx.compose.ui.graphics.drawscope.Stroke(2.5f))
            }
        }
    }
}
