package com.deliverex.live.data.remote

import com.deliverex.live.data.model.ApprovalItem
import com.deliverex.live.data.model.ErpState
import com.deliverex.live.data.model.FrontlineGuidance
import com.deliverex.live.data.model.ReceiptItem
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed interface LiveWsEvent {
    data class Status(
        val mode: String,
        val connected: Boolean,
        val workflowReady: Boolean,
        val model: String?,
        val message: String
    ) : LiveWsEvent

    data class AudioOut(val base64Pcm24k: String) : LiveWsEvent
    data class Latency(val ttfaMs: Int) : LiveWsEvent
    data class Interrupted(val count: Int) : LiveWsEvent
    data class Transcript(val role: String, val text: String, val isFinal: Boolean) : LiveWsEvent
    data object TurnComplete : LiveWsEvent
    data class ToolCallStart(val name: String, val argsSummary: String) : LiveWsEvent
    data class ToolCallResult(
        val name: String,
        val argsSummary: String,
        val status: String,
        val elapsedMs: Double?,
        val matchedPolicyIds: List<String>,
        val guidance: FrontlineGuidance?,
        val customerName: String?
    ) : LiveWsEvent

    data class WorkflowReply(
        val text: String,
        val intent: String,
        val guidance: FrontlineGuidance?
    ) : LiveWsEvent

    data class ErpStateUpdate(val state: ErpState) : LiveWsEvent
    data class ManagerDecision(
        val decision: String,
        val approval: ApprovalItem,
        val receipt: ReceiptItem?
    ) : LiveWsEvent

    data class Error(val message: String) : LiveWsEvent
    data object Closed : LiveWsEvent
}

class LiveCallWebSocketClient(
    private val httpClient: OkHttpClient,
    private val json: Json
) {
    private var webSocket: WebSocket? = null

    fun connect(
        baseUrl: String,
        onEvent: (LiveWsEvent) -> Unit
    ) {
        disconnect()
        val wsUrl = baseUrl.trimEnd('/')
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://") + "/ws/live-call"

        val request = Request.Builder().url(wsUrl).build()
        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching { parseEvent(text) }
                    .onSuccess { evt -> if (evt != null) onEvent(evt) }
                    .onFailure { err -> onEvent(LiveWsEvent.Error("Parse error: ${err.message}")) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                onEvent(LiveWsEvent.Error(t.message ?: "WebSocket connection failed"))
                onEvent(LiveWsEvent.Closed)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                onEvent(LiveWsEvent.Closed)
            }
        })
    }

    fun sendAudioChunk(base64Pcm16k: String, speaking: Boolean) {
        val payload = buildJsonObject {
            put("type", "audio_chunk")
            put("data", base64Pcm16k)
            put("speaking", speaking)
        }.toString()
        webSocket?.send(payload)
    }

    fun sendVideoFrame(
        dataUrl: String,
        caption: String,
        customerName: String?,
        damagedBags: Int,
        prompt: String? = null
    ) {
        val payload = buildJsonObject {
            put("type", "video_frame")
            put("data_url", dataUrl)
            put("caption", caption)
            if (!customerName.isNullOrBlank()) put("customer_name", customerName)
            put("damaged_bags", damagedBags)
            put("auto_create_approval", true)
            if (!prompt.isNullOrBlank()) put("prompt", prompt)
        }.toString()
        webSocket?.send(payload)
    }

    fun sendGuidedStep(step: Int) {
        val payload = buildJsonObject {
            put("type", "guided_step")
            put("step", step)
        }.toString()
        webSocket?.send(payload)
    }

    fun sendTextTurn(text: String, driverName: String, activeStore: String?) {
        val payload = buildJsonObject {
            put("type", "text_turn")
            put("text", text)
            put("driver_name", driverName)
            if (!activeStore.isNullOrBlank()) put("active_store", activeStore)
        }.toString()
        webSocket?.send(payload)
    }

    fun sendForceEndTurn() {
        webSocket?.send("""{"type":"force_end_turn"}""")
    }

    fun disconnect() {
        webSocket?.close(1000, "Call ended")
        webSocket = null
    }

    private fun parseEvent(raw: String): LiveWsEvent? {
        val root = json.parseToJsonElement(raw).jsonObject
        val type = root["type"]?.jsonPrimitive?.content ?: return null

        return when (type) {
            "status" -> LiveWsEvent.Status(
                mode = root["mode"]?.jsonPrimitive?.content ?: "WORKFLOW_ENGINE",
                connected = root["connected"]?.jsonPrimitive?.booleanOrNull ?: false,
                workflowReady = root["workflow_ready"]?.jsonPrimitive?.booleanOrNull ?: false,
                model = root["model"]?.jsonPrimitive?.content,
                message = root["message"]?.jsonPrimitive?.content ?: ""
            )

            "audio_out" -> LiveWsEvent.AudioOut(
                base64Pcm24k = root["data"]?.jsonPrimitive?.content ?: ""
            )

            "latency" -> LiveWsEvent.Latency(
                ttfaMs = root["ttfa_ms"]?.jsonPrimitive?.intOrNull ?: 280
            )

            "interrupted" -> LiveWsEvent.Interrupted(
                count = root["count"]?.jsonPrimitive?.intOrNull ?: 1
            )

            "transcript" -> LiveWsEvent.Transcript(
                role = root["role"]?.jsonPrimitive?.content ?: "assistant",
                text = root["text"]?.jsonPrimitive?.content ?: "",
                isFinal = root["final"]?.jsonPrimitive?.booleanOrNull ?: false
            )

            "turn_complete" -> LiveWsEvent.TurnComplete

            "tool_call_start" -> LiveWsEvent.ToolCallStart(
                name = root["name"]?.jsonPrimitive?.content ?: "tool",
                argsSummary = root["args"]?.toString() ?: "{}"
            )

            "tool_call_result" -> parseToolCallResult(root)

            "workflow_reply" -> {
                val guidance = root["guidance"]?.let {
                    runCatching { json.decodeFromJsonElement(FrontlineGuidance.serializer(), it) }.getOrNull()
                }
                LiveWsEvent.WorkflowReply(
                    text = root["text"]?.jsonPrimitive?.content ?: "",
                    intent = root["intent"]?.jsonPrimitive?.content ?: "GENERAL",
                    guidance = guidance
                )
            }

            "erp_state" -> {
                val stateObj = root["state"] ?: return null
                LiveWsEvent.ErpStateUpdate(
                    json.decodeFromJsonElement(ErpState.serializer(), stateObj)
                )
            }

            "manager_decision_event" -> {
                val apr = json.decodeFromJsonElement(ApprovalItem.serializer(), root["approval"]!!)
                val rcpt = root["receipt"]?.let {
                    runCatching { json.decodeFromJsonElement(ReceiptItem.serializer(), it) }.getOrNull()
                }
                LiveWsEvent.ManagerDecision(
                    decision = root["decision"]?.jsonPrimitive?.content ?: "APPROVED",
                    approval = apr,
                    receipt = rcpt
                )
            }

            "error" -> LiveWsEvent.Error(
                message = root["message"]?.jsonPrimitive?.content ?: "Unknown server error"
            )

            else -> null
        }
    }

    private fun parseToolCallResult(root: JsonObject): LiveWsEvent.ToolCallResult {
        val name = root["name"]?.jsonPrimitive?.content ?: "tool"
        val argsSummary = root["args"]?.toString() ?: "{}"
        val metaObj = root["meta"]?.jsonObject
        val status = metaObj?.get("status")?.jsonPrimitive?.content ?: "OK"
        val elapsed = metaObj?.get("elapsed_ms")?.jsonPrimitive?.doubleOrNull
        val guidance = metaObj?.get("guidance")?.let {
            runCatching { json.decodeFromJsonElement(FrontlineGuidance.serializer(), it) }.getOrNull()
        }
        val resObj = root["result"]?.jsonObject
        val policyIds = resObj?.get("matched_policies")?.jsonArray?.mapNotNull {
            it.jsonObject["id"]?.jsonPrimitive?.content
        } ?: emptyList()
        val custName = resObj?.get("customer_name")?.jsonPrimitive?.content
            ?: resObj?.get("name")?.jsonPrimitive?.content

        return LiveWsEvent.ToolCallResult(
            name = name,
            argsSummary = argsSummary,
            status = status,
            elapsedMs = elapsed,
            matchedPolicyIds = policyIds,
            guidance = guidance,
            customerName = custName
        )
    }
}
