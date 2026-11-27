package com.deliverex.live.data.local

import android.content.Context
import android.content.SharedPreferences
import com.deliverex.live.BuildConfig

class ServerPreferences(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("deliverex_prefs", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, BuildConfig.DEFAULT_BASE_URL)
            ?.trimEnd('/')
            .orEmpty()
            .ifBlank { BuildConfig.DEFAULT_BASE_URL }
        set(value) {
            prefs.edit().putString(KEY_BASE_URL, value.trim().trimEnd('/')).apply()
        }

    var themeKey: String
        get() = prefs.getString(KEY_THEME, "gold") ?: "gold"
        set(value) {
            prefs.edit().putString(KEY_THEME, value).apply()
        }

    var driverName: String
        get() = prefs.getString(KEY_DRIVER_NAME, "Raju Kumar") ?: "Raju Kumar"
        set(value) {
            prefs.edit().putString(KEY_DRIVER_NAME, value.trim().ifBlank { "Raju Kumar" }).apply()
        }

    var activeStore: String
        get() = prefs.getString(KEY_ACTIVE_STORE, "Krishna Hardware") ?: "Krishna Hardware"
        set(value) {
            prefs.edit().putString(KEY_ACTIVE_STORE, value).apply()
        }

    var offlineDemoMode: Boolean
        get() = prefs.getBoolean(KEY_OFFLINE_DEMO, false)
        set(value) {
            prefs.edit().putBoolean(KEY_OFFLINE_DEMO, value).apply()
        }

    var ownerToken: String
        get() = prefs.getString(KEY_OWNER_TOKEN, "") ?: ""
        set(value) {
            prefs.edit().putString(KEY_OWNER_TOKEN, value.trim()).apply()
        }

    var userRole: String
        get() = prefs.getString(KEY_USER_ROLE, "DRIVER") ?: "DRIVER"
        set(value) {
            prefs.edit().putString(KEY_USER_ROLE, value).apply()
        }

    var preferredLanguage: String
        get() = prefs.getString(KEY_PREFERRED_LANG, "Hinglish") ?: "Hinglish"
        set(value) {
            prefs.edit().putString(KEY_PREFERRED_LANG, value).apply()
        }

    var onboardingCompleted: Boolean
        get() = prefs.getBoolean(KEY_ONBOARDING_DONE, false)
        set(value) {
            prefs.edit().putBoolean(KEY_ONBOARDING_DONE, value).apply()
        }

    companion object {
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_THEME = "theme_key"
        private const val KEY_DRIVER_NAME = "driver_name"
        private const val KEY_ACTIVE_STORE = "active_store"
        private const val KEY_OFFLINE_DEMO = "offline_demo_mode"
        private const val KEY_OWNER_TOKEN = "owner_token"
        private const val KEY_USER_ROLE = "user_role"
        private const val KEY_PREFERRED_LANG = "preferred_language"
        private const val KEY_ONBOARDING_DONE = "onboarding_completed"
    }
}
