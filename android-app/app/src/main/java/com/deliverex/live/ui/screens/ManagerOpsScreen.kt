package com.deliverex.live.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deliverex.live.data.model.ApprovalItem
import com.deliverex.live.ui.DeliverExUiState
import com.deliverex.live.ui.LedgerFilter
import com.deliverex.live.ui.components.Base64ProofImage
import com.deliverex.live.ui.components.GlassCard
import com.deliverex.live.ui.components.StatusPill
import com.deliverex.live.ui.theme.LocalDeliverExPalette
import com.deliverex.live.ui.theme.formatInr

@Composable
fun ManagerOpsScreen(
    state: DeliverExUiState,
    onDecideApproval: (String, String) -> Unit,
    onOpenProofZoom: (String) -> Unit,
    onSetLedgerFilter: (LedgerFilter) -> Unit,
    onSetLedgerQuery: (String) -> Unit,
    onSelectStore: (String) -> Unit
) {
    val pal = LocalDeliverExPalette.current
    val erp = state.erpState
    val totalCash = erp.ledger.sumOf { it.cashReceived }
    val totalOk = erp.ledger.sumOf { it.deliveredQty }
    val totalDmg = erp.ledger.sumOf { it.damagedQty }
    val pendingCount = erp.approvals.count { it.status == "PENDING" }
    val settledCount = erp.customers.count { it.balanceDue == 0 }

    val filteredLedger = erp.ledger.filter { entry ->
        val q = state.ledgerQuery.trim().lowercase()
        val matchesText = q.isBlank() ||
            entry.customerName.lowercase().contains(q) ||
            entry.invoiceId.lowercase().contains(q) ||
            entry.entryId.lowercase().contains(q)
        val matchesFilter = when (state.ledgerFilter) {
            LedgerFilter.ALL -> true
            LedgerFilter.SETTLED -> !entry.tallyStatus.contains("PENDING") && !entry.tallyStatus.contains("REJECTED")
            LedgerFilter.PENDING -> entry.tallyStatus.contains("PENDING")
        }
        matchesText && matchesFilter
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // 1. Live KPI Strip
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                KpiMiniCard("CASH SYNCED", formatInr(totalCash), "${erp.ledger.size} entries", pal.success, Modifier.weight(1f))
                KpiMiniCard("BAGS", "$totalOk ok • $totalDmg dmg", "${erp.inventory.sumOf { it.warehouseStock }} wh", pal.cyan, Modifier.weight(1f))
                KpiMiniCard("HITL / SETTLED", "$pendingCount Pend", "$settledCount/${erp.customers.size} paid", if (pendingCount > 0) pal.warning else pal.primary, Modifier.weight(1f))
            }
        }

        // 2. Latest Official Receipt
        state.latestReceipt?.let { rcpt ->
            item {
                GlassCard(borderColor = pal.success.copy(alpha = 0.55f), backgroundColor = Color(0xCC06281F)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("OFFICIAL WHATSAPP RECEIPT", color = pal.success, fontSize = 10.sp, fontWeight = FontWeight.ExtraBold, fontFamily = FontFamily.Monospace)
                        StatusPill(rcpt.receiptId, pal.success)
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(rcpt.messageText, color = Color(0xFFECFDF5), fontSize = 12.sp, lineHeight = 17.sp)
                }
            }
        }

        // 3. Manager Priya's 1-Tap Approval Queue
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "PRIYA'S 1-TAP APPROVAL QUEUE",
                    color = pal.primary,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.ExtraBold,
                    fontFamily = FontFamily.Monospace
                )
                StatusPill("$pendingCount Pending", if (pendingCount > 0) pal.warning else pal.cyan)
            }
        }

        if (erp.approvals.isEmpty()) {
            item {
                GlassCard {
                    Text(
                        "No policy exceptions yet. Routine deliveries auto-sync to Tally/SAP under SOP-2.3.",
                        color = Color(0xFF94A3B8),
                        fontSize = 12.sp
                    )
                }
            }
        } else {
            items(erp.approvals, key = { it.approvalId }) { apr ->
                ApprovalCard(
                    apr = apr,
                    onDecide = { decision -> onDecideApproval(apr.approvalId, decision) },
                    onZoomProof = { url -> onOpenProofZoom(url) }
                )
            }
        }

        // 4. Grounded Company SOP Policies
        item {
            GlassCard {
                Text(
                    "COMPANY SOP KNOWLEDGE BASE",
                    color = pal.cyan,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.ExtraBold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(8.dp))
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    state.policies.forEach { p ->
                        val active = state.highlightedPolicyIds.contains(p.id)
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (active) pal.cyan.copy(alpha = 0.14f) else Color(0x660B1220),
                            border = BorderStroke(1.dp, if (active) pal.cyan.copy(alpha = 0.65f) else pal.borderGlass)
                        ) {
                            Column(modifier = Modifier.padding(10.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text("${p.id}: ${p.title}", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                    if (active) StatusPill("GROUNDED", pal.cyan)
                                }
                                Spacer(Modifier.height(4.dp))
                                Text(p.rule, color = Color(0xFFCBD5E1), fontSize = 11.sp, lineHeight = 15.sp)
                            }
                        }
                    }
                }
            }
        }

        // 5. Tally / SAP Ledger Table
        item {
            GlassCard {
                Text(
                    "TALLY / SAP LIVE LEDGER",
                    color = pal.primary,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.ExtraBold,
                    fontFamily = FontFamily.Monospace
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = state.ledgerQuery,
                    onValueChange = onSetLedgerQuery,
                    placeholder = { Text("Search store, invoice, or entry ID...", fontSize = 12.sp) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LedgerFilter.entries.forEach { mode ->
                        FilterChip(
                            selected = state.ledgerFilter == mode,
                            onClick = { onSetLedgerFilter(mode) },
                            label = { Text(mode.name, fontSize = 11.sp) }
                        )
                    }
                }
                Spacer(Modifier.height(8.dp))
                if (filteredLedger.isEmpty()) {
                    Text("No ledger entries match this filter.", color = Color(0xFF94A3B8), fontSize = 12.sp)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        filteredLedger.forEach { entry ->
                            val badgeColor = when {
                                entry.tallyStatus.contains("PENDING") -> pal.warning
                                entry.tallyStatus.contains("REJECTED") -> pal.danger
                                else -> pal.success
                            }
                            Surface(
                                shape = RoundedCornerShape(12.dp),
                                color = Color(0x660B1220),
                                border = BorderStroke(1.dp, pal.borderGlass)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(10.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(entry.customerName, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                        Text("${entry.entryId} • ${entry.invoiceId}", color = Color(0xFF94A3B8), fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                                        Text("${entry.deliveredQty} ok • ${entry.damagedQty} dmg • ${formatInr(entry.cashReceived)}", color = pal.cyan, fontSize = 11.sp)
                                    }
                                    StatusPill(entry.tallyStatus.replace("_", " "), badgeColor)
                                }
                            }
                        }
                    }
                }
            }
        }

        // 6. Warehouse Stock & Open Customer Invoices
        item {
            GlassCard {
                Text("WAREHOUSE INVENTORY", color = pal.secondary, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold, fontFamily = FontFamily.Monospace)
                Spacer(Modifier.height(6.dp))
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    erp.inventory.forEach { inv ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("${inv.itemName} (${inv.skuCode})", color = Color.White, fontSize = 12.sp, modifier = Modifier.weight(1f))
                            Text("${inv.warehouseStock} ok • ${inv.damagedQuarantine} dmg", color = pal.success, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
                Text("CUSTOMER OPEN INVOICES (TAP TO TARGET)", color = pal.secondary, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold, fontFamily = FontFamily.Monospace)
                Spacer(Modifier.height(6.dp))
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    erp.customers.forEach { c ->
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (c.name == state.activeStore) pal.cyan.copy(alpha = 0.14f) else Color(0x660B1220),
                            border = BorderStroke(1.dp, if (c.name == state.activeStore) pal.cyan else pal.borderGlass),
                            modifier = Modifier.fillMaxWidth().clickable { onSelectStore(c.name) }
                        ) {
                            Row(
                                modifier = Modifier.padding(10.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(c.name, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                    Text("${c.pendingInvoiceId} • ${c.route}", color = Color(0xFF94A3B8), fontSize = 10.sp)
                                }
                                Column(horizontalAlignment = Alignment.End) {
                                    Text(
                                        "Due: ${formatInr(c.balanceDue)}",
                                        color = if (c.balanceDue == 0) pal.success else pal.warning,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp,
                                        fontFamily = FontFamily.Monospace
                                    )
                                    Text(c.status, color = Color(0xFFCBD5E1), fontSize = 9.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun KpiMiniCard(
    label: String,
    value: String,
    sub: String,
    accent: Color,
    modifier: Modifier = Modifier
) {
    GlassCard(modifier = modifier, borderColor = accent.copy(alpha = 0.4f)) {
        Text(label, color = Color(0xFF94A3B8), fontSize = 9.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
        Spacer(Modifier.height(2.dp))
        Text(value, color = accent, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold)
        Text(sub, color = Color(0xFFCBD5E1), fontSize = 10.sp)
    }
}

@Composable
private fun ApprovalCard(
    apr: ApprovalItem,
    onDecide: (String) -> Unit,
    onZoomProof: (String) -> Unit
) {
    val pal = LocalDeliverExPalette.current
    val isPending = apr.status == "PENDING"
    val statusColor = when (apr.status) {
        "APPROVED" -> pal.success
        "REJECTED" -> pal.danger
        "TAKE_OVER" -> pal.cyan
        else -> pal.warning
    }

    GlassCard(
        borderColor = if (isPending) pal.warning.copy(alpha = 0.65f) else pal.borderGlass,
        backgroundColor = if (isPending) Color(0xCC241908) else pal.surfaceGlass
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "${apr.customerName} (${apr.policyRef})",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                modifier = Modifier.weight(1f)
            )
            StatusPill(apr.status, statusColor)
        }
        Spacer(Modifier.height(6.dp))
        Text(apr.summary, color = Color(0xFFE2E8F0), fontSize = 12.sp, lineHeight = 17.sp)

        if (apr.discountRequested > 0 || apr.damagedQty > 0) {
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (apr.discountRequested > 0) StatusPill("Disc: -${formatInr(apr.discountRequested)}", pal.warning)
                if (apr.damagedQty > 0) StatusPill("Quarantine: ${apr.damagedQty} bags", pal.danger)
            }
        }

        if (!apr.proofImage.isNullOrBlank()) {
            Spacer(Modifier.height(8.dp))
            Base64ProofImage(
                dataUrl = apr.proofImage,
                modifier = Modifier.fillMaxWidth().height(120.dp),
                onClick = { onZoomProof(apr.proofImage) }
            )
            Text("Tap photo to zoom • Gemini Vision Verified", color = pal.cyan, fontSize = 10.sp, modifier = Modifier.padding(top = 4.dp))
        }

        if (isPending) {
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Button(
                    onClick = { onDecide("APPROVED") },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = pal.success, contentColor = Color(0xFF070B14)),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text("✅ Approve", fontWeight = FontWeight.ExtraBold, fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { onDecide("REJECTED") },
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text("❌ Reject", color = pal.danger, fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { onDecide("TAKE_OVER") },
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text("📞 Take Over", color = pal.cyan, fontSize = 12.sp)
                }
            }
        } else {
            Spacer(Modifier.height(6.dp))
            Text("Decided by Priya Sharma • ${apr.decidedAt.orEmpty()}", color = Color(0xFF94A3B8), fontSize = 10.sp)
        }
    }
}
