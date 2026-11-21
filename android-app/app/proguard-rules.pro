# DeliverEx Live — Play Store R8 / ProGuard Rules

-keepattributes Signature
-keepattributes *Annotation*

# Kotlinx Serialization
-keepattributes RuntimeVisibleAnnotations,AnnotationDefault
-keepclassmembers class kotlinx.serialization.json.** { *; }
-dontwarn kotlinx.serialization.**

-keep,includedescriptorclasses class com.deliverex.live.data.model.** { *; }
-keepclassmembers class com.deliverex.live.data.model.**$Companion {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keepnames class okhttp3.internal.publicsuffix.PublicSuffixDatabase

# CameraX
-keep class androidx.camera.** { *; }
