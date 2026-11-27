package com.deliverex.live.update

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.deliverex.live.MainActivity
import com.deliverex.live.R

object AppNotificationManager {
    const val CHANNEL_UPDATES = "raju_bhai_updates_chime_v1"
    const val CHANNEL_ALERTS = "raju_bhai_alerts_chime_v1"
    const val EXTRA_TRIGGER_UPDATE = "extra_trigger_update"
    const val EXTRA_UPDATE_APK_URL = "extra_update_apk_url"
    const val NOTIF_ID_UPDATE = 9101

    private fun chimeUri(context: Context): Uri =
        Uri.parse("android.resource://${context.packageName}/${R.raw.raju_notify}")

    fun ensureChannels(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return
        val audioAttrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        val soundUri = chimeUri(context)

        val updateChannel = NotificationChannel(
            CHANNEL_UPDATES,
            "Raju Bhai App Updates",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Direct push notifications when a new Raju Bhai app update is available."
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 180, 90, 180)
            setSound(soundUri, audioAttrs)
        }

        val alertsChannel = NotificationChannel(
            CHANNEL_ALERTS,
            "Raju Bhai Approvals & Receipts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Instant sound alerts for manager approvals, delivery receipts, and order updates."
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 140, 80, 140)
            setSound(soundUri, audioAttrs)
        }

        nm.createNotificationChannel(updateChannel)
        nm.createNotificationChannel(alertsChannel)
    }

    fun hasNotificationPermission(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
    }

    fun playInAppChime(context: Context) {
        runCatching {
            val mp = MediaPlayer.create(context.applicationContext, R.raw.raju_notify)
            mp?.setOnCompletionListener { it.release() }
            mp?.setOnErrorListener { player, _, _ ->
                player.release()
                true
            }
            mp?.start()
        }
    }

    fun notifyUpdateAvailable(
        context: Context,
        versionName: String,
        releaseNotes: String,
        apkUrl: String
    ) {
        ensureChannels(context)
        if (!hasNotificationPermission(context)) return

        val openIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_TRIGGER_UPDATE, true)
            putExtra(EXTRA_UPDATE_APK_URL, apkUrl)
        }
        val pi = PendingIntent.getActivity(
            context,
            NOTIF_ID_UPDATE,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_UPDATES)
            .setSmallIcon(R.drawable.ic_worker_logo)
            .setContentTitle("🚀 Raju Bhai v$versionName Update Ready")
            .setContentText(releaseNotes.ifBlank { "Tap to download & install the latest Raju Bhai update directly." })
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("${releaseNotes.ifBlank { "New update available for Raju Bhai." }}\nTap to download & install now.")
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .addAction(0, "Install Update", pi)
            .build()

        runCatching {
            NotificationManagerCompat.from(context).notify(NOTIF_ID_UPDATE, notification)
        }
    }

    fun notifyOpsAlert(
        context: Context,
        title: String,
        message: String,
        notificationId: Int = (System.currentTimeMillis() % 100000).toInt() + 1000
    ) {
        ensureChannels(context)
        if (!hasNotificationPermission(context)) {
            playInAppChime(context)
            return
        }

        val openIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pi = PendingIntent.getActivity(
            context,
            notificationId,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_worker_logo)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        runCatching {
            NotificationManagerCompat.from(context).notify(notificationId, notification)
        }
    }
}
