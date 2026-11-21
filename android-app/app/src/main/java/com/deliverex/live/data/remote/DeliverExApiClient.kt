package com.deliverex.live.data.remote

import com.deliverex.live.data.model.AgentWorkflowResponse
import com.deliverex.live.data.model.ApprovalDecisionResponse
import com.deliverex.live.data.model.ErpState
import com.deliverex.live.data.model.GoLiveCheckResponse
import com.deliverex.live.data.model.HealthResponse
import com.deliverex.live.data.model.StateEnvelope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.concurrent.TimeUnit

class DeliverExApiClient(
    private val baseUrlProvider: () -> String
) {
    val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    val httpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .writeTimeout(25, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun url(path: String): String = "${baseUrlProvider().trimEnd('/')}$path"

    suspend fun fetchHealth(): HealthResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url("/api/health")).get().build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.decodeFromString<HealthResponse>(body)
        }
    }

    suspend fun fetchState(): StateEnvelope = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url("/api/state")).get().build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.decodeFromString<StateEnvelope>(body)
        }
    }

    suspend fun fetchGoLiveCheck(): GoLiveCheckResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url("/api/go-live-check")).get().build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            val root = json.parseToJsonElement(body).jsonObject
            val checks = root["checks"]?.jsonArray?.mapNotNull { el ->
                val obj = el.jsonObject
                com.deliverex.live.data.model.GoLiveCheckItem(
                    label = obj["name"]?.jsonPrimitive?.content
                        ?: obj["label"]?.jsonPrimitive?.content ?: "Check",
                    ok = obj["ok"]?.jsonPrimitive?.booleanOrNull
                        ?: (obj["status"]?.jsonPrimitive?.content == "PASS"),
                    detail = obj["detail"]?.jsonPrimitive?.content
                        ?: obj["message"]?.jsonPrimitive?.content ?: ""
                )
            } ?: emptyList()
            val ready = root["ready_for_production"]?.jsonPrimitive?.booleanOrNull
                ?: root["ready"]?.jsonPrimitive?.booleanOrNull ?: false
            val score = root["score"]?.jsonPrimitive?.doubleOrNull?.toInt()
                ?: if (checks.isEmpty()) 0 else ((checks.count { it.ok } * 100) / checks.size)
            GoLiveCheckResponse(readyForProduction = ready, score = score, checks = checks)
        }
    }

    suspend fun resetDemo(): ErpState = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url(url("/api/reset"))
            .post("{}".toRequestBody(jsonMedia))
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            val obj = json.parseToJsonElement(body).jsonObject
            json.decodeFromJsonElement(ErpState.serializer(), obj["state"]!!)
        }
    }

    suspend fun sendAgentTurn(
        text: String,
        driverName: String,
        activeStore: String?
    ): AgentWorkflowResponse = withContext(Dispatchers.IO) {
        val payload = buildJsonObject {
            put("text", text)
            put("driver_name", driverName)
            if (!activeStore.isNullOrBlank()) put("active_store", activeStore)
            put("channel", "GEMINI_LIVE_VOICE")
        }.toString()
        val req = Request.Builder()
            .url(url("/api/agent/turn"))
            .post(payload.toRequestBody(jsonMedia))
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.decodeFromString<AgentWorkflowResponse>(body)
        }
    }

    suspend fun runGuidedStep(step: Int): AgentWorkflowResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url(url("/api/agent/guided/$step"))
            .post("{}".toRequestBody(jsonMedia))
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.decodeFromString<AgentWorkflowResponse>(body)
        }
    }

    suspend fun uploadProofPhoto(
        dataUrl: String,
        caption: String,
        customerName: String?,
        damagedBags: Int,
        driverName: String
    ): ErpState = withContext(Dispatchers.IO) {
        val payload = buildJsonObject {
            put("data_url", dataUrl)
            put("caption", caption)
            if (!customerName.isNullOrBlank()) put("customer_name", customerName)
            put("damaged_bags", damagedBags)
            put("auto_create_approval", true)
            put("driver_name", driverName)
        }.toString()
        val req = Request.Builder()
            .url(url("/api/proof-photo"))
            .post(payload.toRequestBody(jsonMedia))
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            val obj = json.parseToJsonElement(body).jsonObject
            json.decodeFromJsonElement(ErpState.serializer(), obj["state"]!!)
        }
    }

    suspend fun decideApproval(
        approvalId: String,
        decision: String
    ): ApprovalDecisionResponse = withContext(Dispatchers.IO) {
        val payload = buildJsonObject {
            put("decision", decision)
        }.toString()
        val req = Request.Builder()
            .url(url("/api/approvals/$approvalId/decide"))
            .post(payload.toRequestBody(jsonMedia))
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.decodeFromString<ApprovalDecisionResponse>(body)
        }
    }

    suspend fun uploadWhatsAppVoiceNote(
        audioFile: File? = null,
        text: String? = null,
        imageDataUrl: String? = null,
        activeStore: String? = null,
        driverName: String = "Raju Kumar"
    ): JsonObject = withContext(Dispatchers.IO) {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("driver_name", driverName)
        if (!text.isNullOrBlank()) builder.addFormDataPart("text", text)
        if (!imageDataUrl.isNullOrBlank()) builder.addFormDataPart("image_data_url", imageDataUrl)
        if (!activeStore.isNullOrBlank()) builder.addFormDataPart("active_store", activeStore)
        if (audioFile != null && audioFile.exists()) {
            builder.addFormDataPart(
                "file",
                audioFile.name,
                audioFile.asRequestBody("audio/mp4".toMediaType())
            )
        }
        val req = Request.Builder()
            .url(url("/api/whatsapp/voice-note"))
            .post(builder.build())
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("HTTP ${resp.code}: $body")
            json.parseToJsonElement(body).jsonObject
        }
    }
}
