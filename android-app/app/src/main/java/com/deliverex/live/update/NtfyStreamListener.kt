package com.deliverex.live.update

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Real-time open-source push notification listener powered by ntfy (https://github.com/binwiederhier/ntfy).
 * Streams instant ledger pushes, receipts, approvals, and app update alerts directly to the phone.
 */
object NtfyStreamListener {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var listenJob: Job? = null
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val streamClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // Long-lived streaming SSE/JSON connection
        .retryOnConnectionFailure(true)
        .build()

    fun start(
        context: Context,
        topicUrl: String = "https://ntfy.sh/rajubhai-ops-353183969363",
        onUpdatePush: () -> Unit
    ) {
        val cleanUrl = topicUrl.trim().trimEnd('/')
        if (cleanUrl.isBlank()) return
        if (listenJob?.isActive == true) return

        val appCtx = context.applicationContext
        listenJob = scope.launch {
            while (isActive) {
                runCatching {
                    val req = Request.Builder()
                        .url("$cleanUrl/json?since=now")
                        .get()
                        .build()
                    streamClient.newCall(req).execute().use { resp ->
                        if (!resp.isSuccessful) {
                            delay(10_000)
                            return@use
                        }
                        val source = resp.body?.source() ?: return@use
                        while (isActive && !source.exhausted()) {
                            val line = source.readUtf8Line() ?: break
                            if (line.isBlank()) continue
                            handleNtfyJsonLine(appCtx, line, onUpdatePush)
                        }
                    }
                }
                delay(5_000)
            }
        }
    }

    private fun handleNtfyJsonLine(
        context: Context,
        line: String,
        onUpdatePush: () -> Unit
    ) {
        runCatching {
            val obj = json.parseToJsonElement(line).jsonObject
            val event = obj["event"]?.jsonPrimitive?.content.orEmpty()
            if (event != "message") return
            val title = obj["title"]?.jsonPrimitive?.content ?: "Raju Bhai Ops"
            val message = obj["message"]?.jsonPrimitive?.content.orEmpty()
            val tags = obj["tags"]?.jsonArray?.mapNotNull { it.jsonPrimitive.content }.orEmpty()

            if (tags.contains("raju-update")) {
                onUpdatePush()
            } else if (message.isNotBlank()) {
                AppNotificationManager.notifyOpsAlert(
                    context = context,
                    title = title,
                    message = message
                )
            }
        }
    }
}
