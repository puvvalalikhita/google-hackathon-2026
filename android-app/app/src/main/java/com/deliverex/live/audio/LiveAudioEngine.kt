package com.deliverex.live.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.speech.tts.TextToSpeech
import android.util.Base64
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import java.util.Locale
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Native Android audio bridge for DeliverEx Live:
 * - Captures 16kHz PCM16 mono mic audio with AEC + NoiseSuppressor for Gemini Live API
 * - Plays 24kHz PCM16 mono audio chunks with instant flush on Barge-In interruption
 * - Provides Android TextToSpeech (en-IN) fallback for Workflow Engine / Offline Demo mode
 * - Records WhatsApp voice notes (.m4a) via MediaRecorder
 */
class LiveAudioEngine(private val context: Context) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var audioRecord: AudioRecord? = null
    private var captureJob: Job? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null

    private var audioTrack: AudioTrack? = null
    private val trackLock = Any()
    @Volatile
    private var aiSpeakingUntilMs: Long = 0L

    private var tts: TextToSpeech? = null
    @Volatile
    private var ttsReady = false

    private var mediaRecorder: MediaRecorder? = null
    private var currentVoiceNoteFile: File? = null

    init {
        tts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val res = tts?.setLanguage(Locale("en", "IN"))
                ttsReady = res != TextToSpeech.LANG_MISSING_DATA && res != TextToSpeech.LANG_NOT_SUPPORTED
                tts?.setSpeechRate(1.06f)
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun startMicCapture(
        onAudioChunk: (base64Pcm16k: String, rms: Float, speaking: Boolean) -> Unit,
        onError: (String) -> Unit
    ) {
        stopMicCapture()
        val sampleRate = 16000
        val minBuf = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(3200)

        val record = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                minBuf * 2
            )
        } catch (t: Throwable) {
            onError("Microphone unavailable: ${t.message}")
            return
        }

        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            onError("Failed to initialize microphone AudioRecord")
            return
        }

        if (AcousticEchoCanceler.isAvailable()) {
            echoCanceler = runCatching {
                AcousticEchoCanceler.create(record.audioSessionId)?.apply { enabled = true }
            }.getOrNull()
        }
        if (NoiseSuppressor.isAvailable()) {
            noiseSuppressor = runCatching {
                NoiseSuppressor.create(record.audioSessionId)?.apply { enabled = true }
            }.getOrNull()
        }

        audioRecord = record
        record.startRecording()

        captureJob = scope.launch {
            val frameSamples = 1600 // 100ms chunks at 16kHz
            val shortBuf = ShortArray(frameSamples)
            val byteBuf = ByteArray(frameSamples * 2)

            while (isActive && record.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                val read = record.read(shortBuf, 0, frameSamples)
                if (read > 0) {
                    var sumSq = 0.0
                    for (i in 0 until read) {
                        val s = shortBuf[i].toInt()
                        val norm = s / 32768.0
                        sumSq += norm * norm
                        byteBuf[i * 2] = (s and 0xFF).toByte()
                        byteBuf[i * 2 + 1] = ((s shr 8) and 0xFF).toByte()
                    }
                    val rms = sqrt(sumSq / read).toFloat()
                    val aiSpeaking = System.currentTimeMillis() < aiSpeakingUntilMs
                    if (aiSpeaking && rms < 0.085f) {
                        // Prevent acoustic echo feedback unless driver clearly barges in
                        continue
                    }
                    val b64 = Base64.encodeToString(byteBuf, 0, read * 2, Base64.NO_WRAP)
                    onAudioChunk(b64, rms, rms > 0.02f)
                } else {
                    delay(15)
                }
            }
        }
    }

    fun stopMicCapture() {
        captureJob?.cancel()
        captureJob = null
        runCatching { echoCanceler?.release() }
        echoCanceler = null
        runCatching { noiseSuppressor?.release() }
        noiseSuppressor = null
        runCatching {
            audioRecord?.stop()
            audioRecord?.release()
        }
        audioRecord = null
    }

    fun playPcm24kBase64(base64Pcm: String): Float {
        if (base64Pcm.isBlank()) return 0.05f
        val bytes = runCatching { Base64.decode(base64Pcm, Base64.DEFAULT) }.getOrNull() ?: return 0.05f
        if (bytes.isEmpty()) return 0.05f

        var energySum = 0.0
        val sampleCount = bytes.size / 2
        for (i in 0 until sampleCount) {
            val lo = bytes[i * 2].toInt() and 0xFF
            val hi = bytes[i * 2 + 1].toInt()
            val sample = (hi shl 8) or lo
            energySum += abs(sample / 32768.0)
        }
        val avgEnergy = if (sampleCount > 0) (energySum / sampleCount * 6.0).toFloat().coerceIn(0.15f, 1f) else 0.2f

        synchronized(trackLock) {
            val track = ensureAudioTrack()
            if (track.playState != AudioTrack.PLAYSTATE_PLAYING) {
                track.play()
            }
            track.write(bytes, 0, bytes.size)
            val durationMs = (sampleCount * 1000L) / 24000L
            aiSpeakingUntilMs = System.currentTimeMillis() + durationMs + 350L
        }
        return avgEnergy
    }

    private fun ensureAudioTrack(): AudioTrack {
        audioTrack?.let {
            if (it.state == AudioTrack.STATE_INITIALIZED) return it
        }
        val sampleRate = 24000
        val minBuf = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(4800)

        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(minBuf * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setSessionId(AudioManager.AUDIO_SESSION_ID_GENERATE)
            .build()

        audioTrack = track
        return track
    }

    fun flushPlayback() {
        synchronized(trackLock) {
            aiSpeakingUntilMs = 0L
            runCatching {
                audioTrack?.pause()
                audioTrack?.flush()
                audioTrack?.play()
            }
        }
        runCatching { tts?.stop() }
    }

    fun speakTts(text: String) {
        if (!ttsReady || text.isBlank()) return
        aiSpeakingUntilMs = System.currentTimeMillis() + (text.length * 55L).coerceIn(1500L, 9000L)
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "deliverex_reply_${System.currentTimeMillis()}")
    }

    fun startWhatsAppRecording(): Result<File> = runCatching {
        stopWhatsAppRecording()
        val outFile = File(context.cacheDir, "wa_voice_note_${System.currentTimeMillis()}.m4a")
        @Suppress("DEPRECATION")
        val mr = MediaRecorder().apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioSamplingRate(16000)
            setAudioEncodingBitRate(32000)
            setOutputFile(outFile.absolutePath)
            prepare()
            start()
        }
        mediaRecorder = mr
        currentVoiceNoteFile = outFile
        outFile
    }

    fun stopWhatsAppRecording(): File? {
        val file = currentVoiceNoteFile
        runCatching {
            mediaRecorder?.stop()
            mediaRecorder?.release()
        }
        mediaRecorder = null
        currentVoiceNoteFile = null
        return file?.takeIf { it.exists() && it.length() > 0L }
    }

    fun release() {
        stopMicCapture()
        flushPlayback()
        runCatching { audioTrack?.release() }
        audioTrack = null
        runCatching { tts?.shutdown() }
        tts = null
        stopWhatsAppRecording()
    }
}
