package com.deliverex.live.update

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import com.deliverex.live.BuildConfig
import com.deliverex.live.data.local.ServerPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

@Serializable
data class AppUpdateInfo(
    @SerialName("app_name") val appName: String = "Raju Bhai",
    @SerialName("latest_version_code") val latestVersionCode: Int = BuildConfig.VERSION_CODE,
    @SerialName("latest_version_name") val latestVersionName: String = BuildConfig.VERSION_NAME,
    @SerialName("apk_url") val apkUrl: String = "",
    @SerialName("release_notes") val releaseNotes: String = "",
    @SerialName("force_update") val forceUpdate: Boolean = false
)

object AppUpdateManager {
    private const val JOB_ID_UPDATE_CHECK = 4401
    private const val PREF_NOTIFIED_VERSION = "last_notified_version_code"

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    suspend fun fetchLatestVersion(baseUrl: String): AppUpdateInfo? = withContext(Dispatchers.IO) {
        val cleanBase = baseUrl.trim().trimEnd('/')
        if (cleanBase.isBlank()) return@withContext null
        runCatching {
            val req = Request.Builder()
                .url("$cleanBase/api/app/version")
                .get()
                .build()
            httpClient.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) return@use null
                json.decodeFromString<AppUpdateInfo>(body)
            }
        }.getOrNull()
    }

    fun isNewerVersion(info: AppUpdateInfo?): Boolean {
        if (info == null || info.apkUrl.isBlank()) return false
        return info.latestVersionCode > BuildConfig.VERSION_CODE
    }

    fun markVersionNotified(context: Context, versionCode: Int) {
        context.getSharedPreferences("raju_update_prefs", Context.MODE_PRIVATE)
            .edit()
            .putInt(PREF_NOTIFIED_VERSION, versionCode)
            .apply()
    }

    fun lastNotifiedVersion(context: Context): Int =
        context.getSharedPreferences("raju_update_prefs", Context.MODE_PRIVATE)
            .getInt(PREF_NOTIFIED_VERSION, 0)

    fun schedulePeriodicUpdateCheck(context: Context) {
        val scheduler = context.getSystemService(Context.JOB_SCHEDULER_SERVICE) as? JobScheduler ?: return
        val component = ComponentName(context, UpdateCheckJobService::class.java)
        val info = JobInfo.Builder(JOB_ID_UPDATE_CHECK, component)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPeriodic(15 * 60 * 1000L)
            .setPersisted(true)
            .build()
        runCatching { scheduler.schedule(info) }
    }

    suspend fun downloadAndInstallApk(
        context: Context,
        apkUrl: String,
        onProgress: (Int) -> Unit
    ): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val req = Request.Builder().url(apkUrl).get().build()
            httpClient.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) error("Download failed (HTTP ${resp.code})")
                val body = resp.body ?: error("Empty APK response")
                val total = body.contentLength()
                val updatesDir = File(context.cacheDir, "updates").apply { mkdirs() }
                val apkFile = File(updatesDir, "Raju-Bhai-update.apk")

                body.byteStream().use { input ->
                    FileOutputStream(apkFile).use { output ->
                        val buf = ByteArray(16 * 1024)
                        var copied = 0L
                        var read: Int
                        var lastPct = -1
                        while (input.read(buf).also { read = it } != -1) {
                            output.write(buf, 0, read)
                            copied += read
                            if (total > 0) {
                                val pct = ((copied * 100L) / total).toInt().coerceIn(0, 100)
                                if (pct != lastPct) {
                                    lastPct = pct
                                    withContext(Dispatchers.Main) { onProgress(pct) }
                                }
                            }
                        }
                    }
                }

                withContext(Dispatchers.Main) {
                    onProgress(100)
                    val uri = FileProvider.getUriForFile(
                        context,
                        "${context.packageName}.fileprovider",
                        apkFile
                    )
                    val installIntent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(installIntent)
                }
            }
        }
    }
}

class UpdateCheckJobService : JobService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onStartJob(params: JobParameters?): Boolean {
        serviceScope.launch {
            runCatching {
                val prefs = ServerPreferences(applicationContext)
                val info = AppUpdateManager.fetchLatestVersion(prefs.baseUrl)
                if (info != null && AppUpdateManager.isNewerVersion(info)) {
                    if (AppUpdateManager.lastNotifiedVersion(applicationContext) < info.latestVersionCode) {
                        AppNotificationManager.notifyUpdateAvailable(
                            context = applicationContext,
                            versionName = info.latestVersionName,
                            releaseNotes = info.releaseNotes,
                            apkUrl = info.apkUrl
                        )
                        AppUpdateManager.markVersionNotified(applicationContext, info.latestVersionCode)
                    }
                }
            }
            jobFinished(params, false)
        }
        return true
    }

    override fun onStopJob(params: JobParameters?): Boolean {
        serviceScope.cancel()
        return true
    }
}
