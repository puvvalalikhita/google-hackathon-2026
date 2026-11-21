package com.deliverex.live.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class HealthResponse(
    val status: String = "ok",
    @SerialName("gemini_configured") val geminiConfigured: Boolean = false,
    @SerialName("auth_mode") val authMode: String = "workflow_offline",
    @SerialName("live_model") val liveModel: String = "gemini-3.8-live",
    @SerialName("voice_note_model") val voiceNoteModel: String = "gemini-3.8-flash",
    @SerialName("whatsapp_configured") val whatsappConfigured: Boolean = false,
    val environment: String = "development",
    @SerialName("database_ok") val databaseOk: Boolean = true
)

@Serializable
data class StateEnvelope(
    val state: ErpState = ErpState(),
    val policies: List<PolicyItem> = emptyList()
)

@Serializable
data class ErpState(
    val customers: List<Customer> = emptyList(),
    val inventory: List<InventoryItem> = emptyList(),
    val ledger: List<LedgerEntry> = emptyList(),
    val approvals: List<ApprovalItem> = emptyList(),
    val receipts: List<ReceiptItem> = emptyList(),
    val insights: List<InsightItem> = emptyList(),
    @SerialName("whatsapp_messages") val whatsappMessages: List<WhatsAppMessage> = emptyList(),
    @SerialName("whatsapp_session") val whatsappSession: WhatsAppSession? = null
)

@Serializable
data class Customer(
    @SerialName("customer_id") val customerId: String,
    val name: String,
    val aliases: String = "",
    val location: String,
    val route: String,
    val phone: String,
    @SerialName("pending_invoice_id") val pendingInvoiceId: String,
    @SerialName("invoice_amount") val invoiceAmount: Int,
    @SerialName("expected_bags") val expectedBags: Int,
    @SerialName("sku_code") val skuCode: String,
    @SerialName("balance_due") val balanceDue: Int,
    @SerialName("credit_limit") val creditLimit: Int,
    val status: String
)

@Serializable
data class InventoryItem(
    @SerialName("sku_code") val skuCode: String,
    @SerialName("item_name") val itemName: String,
    @SerialName("warehouse_stock") val warehouseStock: Int,
    @SerialName("damaged_quarantine") val damagedQuarantine: Int = 0,
    @SerialName("unit_price") val unitPrice: Int,
    @SerialName("updated_at") val updatedAt: String = ""
)

@Serializable
data class LedgerEntry(
    @SerialName("entry_id") val entryId: String,
    val timestamp: String,
    @SerialName("driver_name") val driverName: String,
    @SerialName("customer_id") val customerId: String,
    @SerialName("customer_name") val customerName: String,
    @SerialName("invoice_id") val invoiceId: String,
    @SerialName("sku_code") val skuCode: String,
    @SerialName("delivered_qty") val deliveredQty: Int,
    @SerialName("damaged_qty") val damagedQty: Int = 0,
    @SerialName("cash_received") val cashReceived: Int,
    @SerialName("discount_amount") val discountAmount: Int = 0,
    val channel: String,
    @SerialName("tally_status") val tallyStatus: String,
    val notes: String? = null
)

@Serializable
data class ApprovalItem(
    @SerialName("approval_id") val approvalId: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("decided_at") val decidedAt: String? = null,
    @SerialName("driver_name") val driverName: String,
    @SerialName("customer_id") val customerId: String,
    @SerialName("customer_name") val customerName: String,
    @SerialName("entry_id") val entryId: String? = null,
    @SerialName("exception_type") val exceptionType: String,
    @SerialName("policy_ref") val policyRef: String,
    val summary: String,
    @SerialName("discount_requested") val discountRequested: Int = 0,
    @SerialName("damaged_qty") val damagedQty: Int = 0,
    @SerialName("proof_image") val proofImage: String? = null,
    @SerialName("manager_name") val managerName: String = "Priya Sharma (Area Manager)",
    val status: String = "PENDING"
)

@Serializable
data class ReceiptItem(
    @SerialName("receipt_id") val receiptId: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("driver_name") val driverName: String,
    @SerialName("customer_name") val customerName: String,
    @SerialName("invoice_id") val invoiceId: String,
    @SerialName("delivered_qty") val deliveredQty: Int,
    @SerialName("damaged_qty") val damagedQty: Int,
    @SerialName("cash_received") val cashReceived: Int,
    @SerialName("discount_approved") val discountApproved: Int,
    @SerialName("balance_remaining") val balanceRemaining: Int,
    val channel: String,
    @SerialName("message_text") val messageText: String
)

@Serializable
data class InsightItem(
    @SerialName("insight_id") val insightId: Int = 0,
    @SerialName("created_at") val createdAt: String,
    val route: String,
    val category: String,
    val severity: String,
    val title: String,
    val detail: String
)

@Serializable
data class WhatsAppMessage(
    @SerialName("msg_id") val msgId: String,
    @SerialName("created_at") val createdAt: String,
    val sender: String,
    @SerialName("driver_name") val driverName: String = "Raju Kumar",
    @SerialName("msg_type") val msgType: String = "text",
    val body: String,
    @SerialName("media_data_url") val mediaDataUrl: String? = null,
    val metadata: WhatsAppMetadata = WhatsAppMetadata()
)

@Serializable
data class WhatsAppMetadata(
    @SerialName("sender_label") val senderLabel: String? = null,
    val verified: Boolean = false,
    @SerialName("processing_ms") val processingMs: Double? = null,
    @SerialName("used_gemini") val usedGemini: Boolean = false
)

@Serializable
data class WhatsAppSession(
    @SerialName("session_id") val sessionId: String = "default",
    @SerialName("driver_name") val driverName: String = "Raju Kumar",
    @SerialName("active_customer_id") val activeCustomerId: String? = null,
    @SerialName("active_customer_name") val activeCustomerName: String? = null,
    @SerialName("workflow_stage") val workflowStage: String = "IDLE",
    @SerialName("turn_count") val turnCount: Int = 0
)

@Serializable
data class PolicyItem(
    val id: String,
    val title: String,
    val category: String,
    val keywords: List<String> = emptyList(),
    val rule: String,
    @SerialName("auto_limit_inr") val autoLimitInr: Int? = null,
    @SerialName("escalation_owner") val escalationOwner: String = "Priya Sharma"
)

@Serializable
data class FrontlineGuidance(
    val intent: String = "READY",
    val language: String = "Hinglish / Tanglish",
    val sentiment: String = "CALM",
    @SerialName("coach_tip") val coachTip: String = "Greet store owner politely and confirm bag count before unloading.",
    @SerialName("suggested_phrase") val suggestedPhrase: String = "Namaste Seth ji, UltraTech bags check kar lijiye."
)

@Serializable
data class ApprovalDecisionResponse(
    val decision: String,
    val approval: ApprovalItem,
    val receipt: ReceiptItem? = null,
    val state: ErpState
)

@Serializable
data class AgentWorkflowResponse(
    @SerialName("user_text") val userText: String? = null,
    @SerialName("reply_text") val replyText: String = "",
    val intent: String = "GENERAL",
    @SerialName("is_barge_in") val isBargeIn: Boolean = false,
    @SerialName("processing_ms") val processingMs: Double = 280.0,
    val guidance: FrontlineGuidance? = null,
    val state: ErpState? = null,
    val result: JsonObject? = null
)

@Serializable
data class GoLiveCheckItem(
    val label: String = "",
    val ok: Boolean = false,
    val detail: String = ""
)

@Serializable
data class GoLiveCheckResponse(
    @SerialName("ready_for_production") val readyForProduction: Boolean = false,
    val score: Int = 0,
    val checks: List<GoLiveCheckItem> = emptyList()
)

data class TranscriptMessage(
    val id: String,
    val role: String, // "user", "assistant", "system", "barge_in"
    val text: String,
    val isFinal: Boolean = true,
    val timestamp: String = ""
)

data class ToolLogEntry(
    val id: String,
    val name: String,
    val argsSummary: String,
    val status: String,
    val elapsedMs: Double? = null
)
