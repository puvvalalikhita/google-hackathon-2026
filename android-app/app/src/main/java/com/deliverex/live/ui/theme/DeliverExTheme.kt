package com.deliverex.live.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import java.text.NumberFormat
import java.util.Locale

data class DeliverExPalette(
    val key: String,
    val label: String,
    val primary: Color,
    val secondary: Color,
    val tertiary: Color,
    val danger: Color = Color(0xFFFB7185),
    val success: Color = Color(0xFF10B981),
    val warning: Color = Color(0xFFF59E0B),
    val cyan: Color = Color(0xFF38BDF8),
    val bgDeep: Color = Color(0xFF070B14),
    val surfaceGlass: Color = Color(0xCC0F172A),
    val surfaceCard: Color = Color(0x991E293B),
    val borderGlass: Color = Color(0x33FFFFFF)
)

val DELIVEREX_PALETTES = mapOf(
    "gold" to DeliverExPalette(
        key = "gold",
        label = "Royal Gold",
        primary = Color(0xFFFBBF24),
        secondary = Color(0xFFFDE68A),
        tertiary = Color(0xFFF59E0B)
    ),
    "emerald" to DeliverExPalette(
        key = "emerald",
        label = "Emerald Ops",
        primary = Color(0xFF10B981),
        secondary = Color(0xFF38BDF8),
        tertiary = Color(0xFF818CF8)
    ),
    "sapphire" to DeliverExPalette(
        key = "sapphire",
        label = "Sapphire",
        primary = Color(0xFF60A5FA),
        secondary = Color(0xFFA78BFA),
        tertiary = Color(0xFF22D3EE)
    ),
    "ruby" to DeliverExPalette(
        key = "ruby",
        label = "Ruby Pulse",
        primary = Color(0xFFFB7185),
        secondary = Color(0xFFF472B6),
        tertiary = Color(0xFFFB923C)
    ),
    "platinum" to DeliverExPalette(
        key = "platinum",
        label = "Platinum",
        primary = Color(0xFFE2E8F0),
        secondary = Color(0xFF7DD3FC),
        tertiary = Color(0xFF94A3B8)
    ),
    "sunset" to DeliverExPalette(
        key = "sunset",
        label = "Sunset",
        primary = Color(0xFFFB923C),
        secondary = Color(0xFFFBBF24),
        tertiary = Color(0xFFFB7185)
    )
)

val LocalDeliverExPalette = staticCompositionLocalOf { DELIVEREX_PALETTES.getValue("gold") }

@Composable
fun DeliverExTheme(
    themeKey: String = "gold",
    content: @Composable () -> Unit
) {
    val palette = DELIVEREX_PALETTES[themeKey] ?: DELIVEREX_PALETTES.getValue("gold")
    val colorScheme = darkColorScheme(
        primary = palette.primary,
        onPrimary = Color(0xFF090D16),
        secondary = palette.secondary,
        onSecondary = Color(0xFF090D16),
        tertiary = palette.tertiary,
        background = palette.bgDeep,
        onBackground = Color(0xFFF1F5F9),
        surface = palette.surfaceGlass,
        onSurface = Color(0xFFF1F5F9),
        surfaceVariant = palette.surfaceCard,
        onSurfaceVariant = Color(0xFFCBD5E1),
        error = palette.danger,
        outline = palette.borderGlass
    )

    CompositionLocalProvider(LocalDeliverExPalette provides palette) {
        MaterialTheme(
            colorScheme = colorScheme,
            content = content
        )
    }
}

fun formatInr(amount: Int): String {
    val fmt = NumberFormat.getNumberInstance(Locale("en", "IN"))
    return "₹${fmt.format(amount)}"
}

fun formatInrLong(amount: Long): String {
    val fmt = NumberFormat.getNumberInstance(Locale("en", "IN"))
    return "₹${fmt.format(amount)}"
}
