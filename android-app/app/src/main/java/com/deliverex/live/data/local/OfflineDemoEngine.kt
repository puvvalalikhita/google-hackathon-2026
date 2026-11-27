package com.deliverex.live.data.local

import com.deliverex.live.data.model.ApprovalDecisionResponse
import com.deliverex.live.data.model.ApprovalItem
import com.deliverex.live.data.model.AuditLogEntry
import com.deliverex.live.data.model.AuditSummary
import com.deliverex.live.data.model.Customer
import com.deliverex.live.data.model.ErpState
import com.deliverex.live.data.model.FrontlineGuidance
import com.deliverex.live.data.model.InsightItem
import com.deliverex.live.data.model.InventoryItem
import com.deliverex.live.data.model.LedgerEntry
import com.deliverex.live.data.model.PolicyItem
import com.deliverex.live.data.model.ReceiptItem
import com.deliverex.live.data.model.StateEnvelope
import com.deliverex.live.data.model.WhatsAppMessage
import com.deliverex.live.data.model.WhatsAppMetadata
import com.deliverex.live.data.model.WhatsAppSession
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.UUID

/**
 * Self-contained offline simulation mirroring DeliverEx Live's SQLite + SOP workflow engine.
 * Ensures the app remains immediately usable and testable when no backend server is reachable
 * (including during Google Play Store app review).
 */
class OfflineDemoEngine {
    private val timeFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    private var customers = mutableListOf<Customer>()
    private var inventory = mutableListOf<InventoryItem>()
    private var ledger = mutableListOf<LedgerEntry>()
    private var approvals = mutableListOf<ApprovalItem>()
    private var receipts = mutableListOf<ReceiptItem>()
    private var insights = mutableListOf<InsightItem>()
    private var whatsappMessages = mutableListOf<WhatsAppMessage>()
    private var activeCustomerName: String? = null
    private var workflowStage: String = "IDLE"

    val policies: List<PolicyItem> = listOf(
        PolicyItem(
            id = "SOP-4.2",
            title = "Spot Discount & Settlement Authority",
            category = "discount",
            keywords = listOf("discount", "500", "200", "settle"),
            rule = "Field delivery agents may auto-approve spot cash discounts up to Rs 200 per invoice. Any discount above Rs 200 MUST be escalated to Area Manager Priya Sharma for 1-tap approval before closing the invoice in Tally/SAP.",
            autoLimitInr = 200,
            escalationOwner = "Priya Sharma (Area Manager)"
        ),
        PolicyItem(
            id = "SOP-5.1",
            title = "Damaged Goods & Short Delivery Protocol",
            category = "damage",
            keywords = listOf("damage", "torn", "phate", "phata", "short"),
            rule = "If 1 or more bags are damaged/torn during transit, log only intact delivered bags against the customer invoice, move damaged bags to Warehouse Quarantine stock, and trigger a Manager Approval & Quality Insight flag for Route QA.",
            escalationOwner = "Priya Sharma (Area Manager)"
        ),
        PolicyItem(
            id = "SOP-2.3",
            title = "Cash Collection & Ledger Posting",
            category = "cash",
            keywords = listOf("cash", "payment", "tally", "sap"),
            rule = "Cash collections up to Rs 50,000 that match or partially settle an open invoice are posted immediately to Tally/SAP Ledger. An official WhatsApp confirmation receipt must be sent within 10 seconds.",
            autoLimitInr = 50000,
            escalationOwner = "Accounts Desk"
        ),
        PolicyItem(
            id = "SOP-6.0",
            title = "Live Human Handoff & Dispute Escalation",
            category = "handoff",
            keywords = listOf("dispute", "angry", "manager", "handoff"),
            rule = "If a shop owner disputes pricing, refuses payment, or sounds frustrated, immediately offer a warm handoff to Area Manager Priya Sharma with full call summary attached.",
            escalationOwner = "Priya Sharma (Area Manager)"
        )
    )

    init {
        reset()
    }

    private fun nowStr(): String = "2026-11-21 ${LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))}"

    fun reset(): StateEnvelope {
        customers = mutableListOf(
            Customer("CUST-104", "Krishna Hardware", "krishna", "Old Delhi Wholesale Market", "Route-4 (Old Delhi)", "+91-98110-10401", "INV-8841", 15500, 20, "SKU-CEM-50", 15500, 50000, "OUT_FOR_DELIVERY"),
            Customer("CUST-108", "Shri Ganesh Stores", "ganesh", "Chandni Chowk Bazaar", "Route-4 (Old Delhi)", "+91-98110-10802", "INV-8845", 22000, 30, "SKU-ACC-50", 22000, 75000, "OUT_FOR_DELIVERY"),
            Customer("CUST-112", "Bharat Traders", "bharat", "Sadar Bazar Mandi", "Route-2 (Central)", "+91-98110-11203", "INV-8850", 14500, 10, "SKU-TMT-12", 14500, 40000, "PENDING_DISPATCH"),
            Customer("CUST-115", "Murugan Builders", "murugan", "T. Nagar Market, Chennai", "Route-7 (Chennai South)", "+91-98400-11509", "INV-8862", 18400, 25, "SKU-CEM-50", 18400, 60000, "OUT_FOR_DELIVERY")
        )
        inventory = mutableListOf(
            InventoryItem("SKU-CEM-50", "UltraTech Cement (50kg Bag)", 450, 4, 775, nowStr()),
            InventoryItem("SKU-ACC-50", "ACC Gold Cement (50kg Bag)", 320, 1, 760, nowStr()),
            InventoryItem("SKU-TMT-12", "Tata Tiscon TMT 12mm Bundle", 180, 0, 1450, nowStr())
        )
        ledger = mutableListOf(
            LedgerEntry("TALLY-9001", nowStr(), "Vikram Singh", "CUST-112", "Bharat Traders", "INV-8832", "SKU-TMT-12", 12, 0, 17400, 0, "GEMINI_LIVE_VOICE", "SYNCED_TALLY", "Full cash settlement on delivery")
        )
        approvals = mutableListOf()
        receipts = mutableListOf()
        insights = mutableListOf(
            InsightItem(1, nowStr(), "Route-4 (Old Delhi)", "DAMAGED_GOODS", "MEDIUM", "Prior Torn Cement Bags on Route-4", "2 bags reported torn during unloading on Truck MH-03-AB-1254 earlier this week."),
            InsightItem(2, nowStr(), "Route-4 (Old Delhi)", "PAYMENT_FRICTION", "LOW", "Wholesale Discount Requests Trending Up", "3 Tier-2 dealers requested Rs 300-500 spot discounts during morning peak hours.")
        )
        whatsappMessages = mutableListOf(
            WhatsAppMessage(
                msgId = "WA-WELCOME-01",
                createdAt = nowStr(),
                sender = "bot",
                driverName = "DeliverEx Ops",
                msgType = "text",
                body = "Namaste Raju! Delivery complete hone par text message, photo proof, ya voice note yahan bhej do — Tally/SAP & Priya Ma'am ko auto-update ho jayega.",
                metadata = WhatsAppMetadata(senderLabel = "DeliverEx Official Ops (+91-80-DELIVEREX)", verified = true)
            )
        )
        activeCustomerName = null
        workflowStage = "IDLE"
        return StateEnvelope(state = snapshot(), policies = policies)
    }

    fun snapshot(): ErpState = ErpState(
        customers = customers.toList(),
        inventory = inventory.toList(),
        ledger = ledger.toList(),
        approvals = approvals.toList(),
        receipts = receipts.toList(),
        insights = insights.toList(),
        whatsappMessages = whatsappMessages.toList(),
        whatsappSession = WhatsAppSession(
            activeCustomerName = activeCustomerName,
            workflowStage = workflowStage
        ),
        auditSummary = AuditSummary(
            totalCount = ledger.size + approvals.size + 1,
            chainVerified = true,
            storageBackend = "offline_demo",
            latest = listOf(
                AuditLogEntry(
                    auditId = "AUD-0000${ledger.size + approvals.size + 1}",
                    seq = ledger.size + approvals.size + 1,
                    timestamp = nowStr(),
                    actor = "DeliverEx Ops",
                    role = "SYSTEM",
                    action = if (approvals.any { it.status == "APPROVED" }) "APPROVAL_DECIDED" else "DELIVERY_RECORDED",
                    targetId = ledger.firstOrNull()?.entryId ?: "deliverex-erp",
                    summary = "${ledger.size} ledger entries • ${approvals.count { it.status == "PENDING" }} pending HITL",
                    integrityHash = "sha256_demo_verified_chain"
                )
            )
        )
    )

    fun exportTallyXml(): String {
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDATA>\n")
        ledger.forEach { r ->
            sb.append("  <TALLYMESSAGE><VOUCHER VCHTYPE=\"Receipt\" ACTION=\"Create\"><VOUCHERNUMBER>${r.entryId}</VOUCHERNUMBER><PARTYLEDGERNAME>${r.customerName}</PARTYLEDGERNAME><AMOUNT>${r.cashReceived}</AMOUNT></VOUCHER></TALLYMESSAGE>\n")
        }
        sb.append("</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>")
        return sb.toString()
    }

    fun exportLedgerCsv(): String {
        val sb = StringBuilder("Entry ID,Timestamp,Driver,Customer,Invoice,Delivered,Damaged,Cash INR,Discount INR,Status\n")
        ledger.forEach { r ->
            sb.append("${r.entryId},${r.timestamp},${r.driverName},${r.customerName},${r.invoiceId},${r.deliveredQty},${r.damagedQty},${r.cashReceived},${r.discountAmount},${r.tallyStatus}\n")
        }
        return sb.toString()
    }

    data class OfflineTurnOutput(
        val userText: String,
        val replyText: String,
        val intent: String,
        val isBargeIn: Boolean,
        val matchedPolicies: List<String>,
        val guidance: FrontlineGuidance,
        val state: ErpState,
        val receipt: ReceiptItem? = null
    )

    fun runGuidedStep(step: Int, driverName: String = "Raju Kumar"): OfflineTurnOutput {
        return when (step) {
            1 -> {
                val user = "Krishna Hardware pe 20 bags cement deliver kar diya aur ₹15,000 cash mil gaya."
                processTurn(user, driverName, "Krishna Hardware", forceBargeIn = false)
            }
            2 -> {
                val user = "Ruko ruko! 20 nahi, 18 bags intact the, 2 bags damaged nikle, aur uncle ₹500 extra discount maang rahe hain!"
                processTurn(user, driverName, "Krishna Hardware", forceBargeIn = true)
            }
            3 -> {
                val user = "Uncle gussa ho rahe hain invoice balance pe, please Priya ma'am se direct baat karwa do!"
                processTurn(user, driverName, "Krishna Hardware", forceBargeIn = false)
            }
            else -> {
                val user = "Anna, T. Nagar Murugan Builders-la 25 bags cement unload pannitten, 18400 cash kedaichuduchu!"
                processTurn(user, driverName, "Murugan Builders", forceBargeIn = false)
            }
        }
    }

    fun processTurn(
        text: String,
        driverName: String = "Raju Kumar",
        activeStore: String? = null,
        forceBargeIn: Boolean = false
    ): OfflineTurnOutput {
        val lower = text.lowercase()
        val isBargeIn = forceBargeIn || lower.contains("ruko") || lower.contains("wait") || lower.contains("nahi")
        val targetCustomer = findCustomer(lower) ?: findCustomer(activeStore ?: "") ?: customers.first()
        activeCustomerName = targetCustomer.name

        val hasDamage = lower.contains("damage") || lower.contains("torn") || lower.contains("phat")
        val hasDiscount500 = lower.contains("500") || lower.contains("discount")
        val isEscalate = lower.contains("priya") || lower.contains("gussa") || lower.contains("baat") || lower.contains("manager")
        val isTamil = lower.contains("anna") || lower.contains("murugan") || lower.contains("pannitten") || lower.contains("kedaichuduchu")

        if (isEscalate) {
            val aprId = "APR-${UUID.randomUUID().toString().take(6).uppercase()}"
            approvals.add(
                0,
                ApprovalItem(
                    approvalId = aprId,
                    createdAt = nowStr(),
                    driverName = driverName,
                    customerId = targetCustomer.customerId,
                    customerName = targetCustomer.name,
                    exceptionType = "LIVE_HANDOFF",
                    policyRef = "SOP-6.0",
                    summary = "Warm handoff requested at ${targetCustomer.name} (${targetCustomer.pendingInvoiceId}) — shop owner disputing balance.",
                    status = "PENDING"
                )
            )
            return OfflineTurnOutput(
                userText = text,
                replyText = "Samajh gaya Raju bhai — main SOP-6.0 ke तहत Area Manager Priya Sharma ma'am ko live call handoff request bhej raha hoon. Unke screen par ${targetCustomer.name} ki poori invoice details aa chuki hain.",
                intent = "ESCALATE",
                isBargeIn = isBargeIn,
                matchedPolicies = listOf("SOP-6.0"),
                guidance = FrontlineGuidance(
                    intent = "LIVE_HANDOFF",
                    language = "Hinglish (HI+EN)",
                    sentiment = "FRUSTRATED",
                    coachTip = "Stay calm and hand phone/call summary to Priya Sharma (SOP-6.0).",
                    suggestedPhrase = "Uncle, main abhi hamare Area Manager Priya ma'am ko line par le raha hoon."
                ),
                state = snapshot()
            )
        }

        if (hasDamage || hasDiscount500) {
            val dmgQty = if (hasDamage) 2 else 0
            val discReq = if (hasDiscount500) 500 else 0
            val delivered = if (hasDamage) 18 else targetCustomer.expectedBags
            val cash = 15000
            val entryId = "TALLY-${9002 + ledger.size}"
            ledger.add(
                0,
                LedgerEntry(
                    entryId = entryId,
                    timestamp = nowStr(),
                    driverName = driverName,
                    customerId = targetCustomer.customerId,
                    customerName = targetCustomer.name,
                    invoiceId = targetCustomer.pendingInvoiceId,
                    skuCode = targetCustomer.skuCode,
                    deliveredQty = delivered,
                    damagedQty = dmgQty,
                    cashReceived = cash,
                    discountAmount = discReq,
                    channel = "GEMINI_LIVE_VOICE",
                    tallyStatus = "PENDING_MANAGER_APPROVAL",
                    notes = "$dmgQty torn bags quarantined; ₹$discReq discount escalated (SOP-4.2 / SOP-5.1)"
                )
            )
            updateInventory(targetCustomer.skuCode, delivered, dmgQty)
            val aprId = "APR-${UUID.randomUUID().toString().take(6).uppercase()}"
            approvals.add(
                0,
                ApprovalItem(
                    approvalId = aprId,
                    createdAt = nowStr(),
                    driverName = driverName,
                    customerId = targetCustomer.customerId,
                    customerName = targetCustomer.name,
                    entryId = entryId,
                    exceptionType = if (hasDamage && hasDiscount500) "DAMAGE_AND_DISCOUNT" else if (hasDamage) "DAMAGED_GOODS" else "DISCOUNT_OVER_CAP",
                    policyRef = if (hasDamage) "SOP-5.1 / SOP-4.2" else "SOP-4.2",
                    summary = "${targetCustomer.name}: $delivered ok bags, $dmgQty torn bags quarantined, ₹$cash cash, ₹$discReq extra discount requested (driver cap ₹200).",
                    discountRequested = discReq,
                    damagedQty = dmgQty,
                    status = "PENDING"
                )
            )
            insights.add(
                0,
                InsightItem(
                    insightId = insights.size + 1,
                    createdAt = nowStr(),
                    route = targetCustomer.route,
                    category = "DAMAGED_GOODS",
                    severity = "HIGH",
                    title = "$dmgQty Damaged Bags Flagged at ${targetCustomer.name}",
                    detail = "Moved $dmgQty bags to Warehouse Quarantine under SOP-5.1; escalated ₹$discReq settlement discount to Priya Sharma."
                )
            )
            return OfflineTurnOutput(
                userText = text,
                replyText = "Achha samajh gaya Raju bhai! 18 intact bags aur 2 damaged bags update kar diye hain. Kyunki ₹500 discount SOP-4.2 ki ₹200 driver limit se upar hai, maine Priya ma'am ko 1-Tap Approval card bhej diya hai.",
                intent = "RECORD_DELIVERY",
                isBargeIn = isBargeIn,
                matchedPolicies = listOf("SOP-4.2", "SOP-5.1"),
                guidance = FrontlineGuidance(
                    intent = "EXCEPTION_ESCALATED",
                    language = "Hinglish (HI+EN)",
                    sentiment = "CONCERNED",
                    coachTip = "Driver discount cap is ₹200 (SOP-4.2). Await Priya Sharma's 1-tap approval.",
                    suggestedPhrase = "Uncle, 2 phate bags quarantine mein mark kar diye hain — manager approval 10 second mein aa jayega."
                ),
                state = snapshot()
            )
        }

        // Standard cash delivery / Tanglish Murugan Builders settlement
        val delivered = targetCustomer.expectedBags
        val cash = if (isTamil) 18400 else targetCustomer.invoiceAmount.coerceAtMost(15000)
        val newBalance = (targetCustomer.balanceDue - cash).coerceAtLeast(0)
        updateCustomerBalance(targetCustomer.customerId, newBalance)
        updateInventory(targetCustomer.skuCode, delivered, 0)
        val entryId = "TALLY-${9002 + ledger.size}"
        ledger.add(
            0,
            LedgerEntry(
                entryId = entryId,
                timestamp = nowStr(),
                driverName = driverName,
                customerId = targetCustomer.customerId,
                customerName = targetCustomer.name,
                invoiceId = targetCustomer.pendingInvoiceId,
                skuCode = targetCustomer.skuCode,
                deliveredQty = delivered,
                damagedQty = 0,
                cashReceived = cash,
                discountAmount = 0,
                channel = "GEMINI_LIVE_VOICE",
                tallyStatus = if (newBalance == 0) "SYNCED_TALLY" else "PARTIAL_SYNCED",
                notes = "SOP-2.3 auto-settled"
            )
        )
        val receipt = createReceipt(driverName, targetCustomer, delivered, 0, cash, 0, newBalance, "GEMINI_LIVE_VOICE")
        return OfflineTurnOutput(
            userText = text,
            replyText = if (isTamil) {
                "Seri anna! ${targetCustomer.name}-la $delivered bags cement & ₹$cash cash Tally-la update aayiduchu. Official WhatsApp receipt anuppitten!"
            } else {
                "Bahut badhiya Raju bhai! ${targetCustomer.name} ke $delivered bags aur ₹$cash cash Tally/SAP mein sync ho gaye hain (SOP-2.3)."
            },
            intent = "RECORD_DELIVERY",
            isBargeIn = isBargeIn,
            matchedPolicies = listOf("SOP-2.3"),
            guidance = FrontlineGuidance(
                intent = "DELIVERY_SYNCED",
                language = if (isTamil) "Tanglish (TA+EN)" else "Hinglish (HI+EN)",
                sentiment = "RESOLVED",
                coachTip = "Invoice synced to Tally/SAP under SOP-2.3. Confirm WhatsApp receipt with dealer.",
                suggestedPhrase = if (isTamil) "Anna, WhatsApp-la official receipt vandhuruchu check pannunga!" else "Seth ji, WhatsApp par official receipt check kar lijiye."
            ),
            state = snapshot(),
            receipt = receipt
        )
    }

    fun attachVisualProof(
        dataUrl: String,
        caption: String,
        customerName: String?,
        damagedBags: Int,
        driverName: String = "Raju Kumar"
    ): ErpState {
        val cust = findCustomer(customerName ?: "") ?: customers.first()
        val existingPendingIdx = approvals.indexOfFirst { it.customerId == cust.customerId && it.status == "PENDING" }
        if (existingPendingIdx >= 0) {
            approvals[existingPendingIdx] = approvals[existingPendingIdx].copy(
                proofImage = dataUrl,
                damagedQty = damagedBags.coerceAtLeast(approvals[existingPendingIdx].damagedQty)
            )
        } else {
            approvals.add(
                0,
                ApprovalItem(
                    approvalId = "APR-${UUID.randomUUID().toString().take(6).uppercase()}",
                    createdAt = nowStr(),
                    driverName = driverName,
                    customerId = cust.customerId,
                    customerName = cust.name,
                    exceptionType = "DAMAGED_GOODS",
                    policyRef = "SOP-5.1",
                    summary = "$caption ($damagedBags damaged bags verified via Field Camera)",
                    damagedQty = damagedBags,
                    proofImage = dataUrl,
                    status = "PENDING"
                )
            )
        }
        return snapshot()
    }

    fun decideApproval(approvalId: String, decision: String): ApprovalDecisionResponse {
        val idx = approvals.indexOfFirst { it.approvalId == approvalId }
        val current = approvals.getOrNull(idx) ?: throw IllegalArgumentException("Approval not found: $approvalId")
        val updated = current.copy(status = decision, decidedAt = nowStr())
        approvals[idx] = updated

        val cust = customers.firstOrNull { it.customerId == current.customerId } ?: customers.first()
        var receipt: ReceiptItem? = null
        if (decision == "APPROVED") {
            updateCustomerBalance(cust.customerId, 0)
            current.entryId?.let { eid ->
                val lIdx = ledger.indexOfFirst { it.entryId == eid }
                if (lIdx >= 0) {
                    ledger[lIdx] = ledger[lIdx].copy(tallyStatus = "SYNCED_TALLY_APPROVED")
                }
            }
            receipt = createReceipt(
                current.driverName,
                cust,
                (cust.expectedBags - current.damagedQty).coerceAtLeast(1),
                current.damagedQty,
                (cust.invoiceAmount - current.discountRequested).coerceAtLeast(0),
                current.discountRequested,
                0,
                "MANAGER_APPROVED"
            )
        } else if (decision == "REJECTED") {
            current.entryId?.let { eid ->
                val lIdx = ledger.indexOfFirst { it.entryId == eid }
                if (lIdx >= 0) {
                    ledger[lIdx] = ledger[lIdx].copy(tallyStatus = "DISCOUNT_REJECTED")
                }
            }
        }

        return ApprovalDecisionResponse(
            decision = decision,
            approval = updated,
            receipt = receipt,
            state = snapshot()
        )
    }

    fun sendWhatsAppTurn(text: String, driverName: String, activeStore: String?, imageDataUrl: String? = null): ErpState {
        whatsappMessages.add(
            WhatsAppMessage(
                msgId = "WA-${UUID.randomUUID().toString().take(8).uppercase()}",
                createdAt = nowStr(),
                sender = "driver",
                driverName = driverName,
                msgType = if (imageDataUrl != null) "image" else "text",
                body = text,
                mediaDataUrl = imageDataUrl
            )
        )
        if (imageDataUrl != null) {
            attachVisualProof(imageDataUrl, text, activeStore, 2, driverName)
        }
        val turn = processTurn(text, driverName, activeStore)
        workflowStage = if (turn.matchedPolicies.contains("SOP-4.2")) "AWAITING_APPROVAL" else "COMPLETED"
        whatsappMessages.add(
            WhatsAppMessage(
                msgId = "WA-${UUID.randomUUID().toString().take(8).uppercase()}",
                createdAt = nowStr(),
                sender = "bot",
                driverName = "DeliverEx Ops",
                msgType = "text",
                body = turn.replyText,
                metadata = WhatsAppMetadata(senderLabel = "DeliverEx Official Ops", processingMs = 210.0)
            )
        )
        return snapshot()
    }

    private fun createReceipt(
        driverName: String,
        cust: Customer,
        delivered: Int,
        damaged: Int,
        cash: Int,
        discount: Int,
        balanceRemaining: Int,
        channel: String
    ): ReceiptItem {
        val rId = "RCPT-${UUID.randomUUID().toString().take(6).uppercase()}"
        val msg = "✅ DELIVEREX OFFICIAL RECEIPT ($rId)\nStore: ${cust.name} (${cust.pendingInvoiceId})\nDelivered: $delivered bags • Damaged: $damaged\nCash Received: ₹$cash • Discount Approved: ₹$discount\nRemaining Balance: ₹$balanceRemaining"
        val receipt = ReceiptItem(rId, nowStr(), driverName, cust.name, cust.pendingInvoiceId, delivered, damaged, cash, discount, balanceRemaining, channel, msg)
        receipts.add(0, receipt)
        whatsappMessages.add(
            WhatsAppMessage(
                msgId = "WA-${UUID.randomUUID().toString().take(8).uppercase()}",
                createdAt = nowStr(),
                sender = "bot",
                driverName = "DeliverEx Ops",
                msgType = "receipt",
                body = msg,
                metadata = WhatsAppMetadata(senderLabel = "DeliverEx Official Receipt", verified = true)
            )
        )
        return receipt
    }

    private fun updateCustomerBalance(customerId: String, newBalance: Int) {
        val idx = customers.indexOfFirst { it.customerId == customerId }
        if (idx >= 0) {
            val c = customers[idx]
            customers[idx] = c.copy(
                balanceDue = newBalance,
                status = if (newBalance == 0) "SETTLED" else "PARTIAL_PAID"
            )
        }
    }

    private fun updateInventory(skuCode: String, delivered: Int, damaged: Int) {
        val idx = inventory.indexOfFirst { it.skuCode == skuCode }
        if (idx >= 0) {
            val item = inventory[idx]
            inventory[idx] = item.copy(
                warehouseStock = (item.warehouseStock - delivered - damaged).coerceAtLeast(0),
                damagedQuarantine = item.damagedQuarantine + damaged,
                updatedAt = nowStr()
            )
        }
    }

    private fun findCustomer(query: String): Customer? {
        val q = query.trim().lowercase()
        if (q.isBlank()) return null
        return customers.firstOrNull { c ->
            q.contains(c.name.lowercase()) ||
                c.aliases.split(",").any { alias -> alias.isNotBlank() && q.contains(alias.trim().lowercase()) } ||
                q.contains(c.customerId.lowercase())
        }
    }
}
