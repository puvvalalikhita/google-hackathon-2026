# 1-Command Google Cloud Run Deployment for DeliverEx Live
# Usage: .\deploy_cloud_run.ps1 -ProjectId "your-gcp-project" -GeminiApiKey "AIza..."

param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [Parameter(Mandatory=$true)][string]$GeminiApiKey,
  [string]$Region = "asia-south1",
  [string]$ServiceName = "deliverex-live",
  [string]$Environment = "production",
  [string]$LiveModel = "gemini-2.5-flash-native-audio-latest",
  [string]$VoiceNoteModel = "gemini-2.5-flash",
  [string]$AdminApiKey = "",
  [string]$CorsAllowOrigins = "*"
)

gcloud config set project $ProjectId

$envVars = @(
  "GEMINI_API_KEY=$GeminiApiKey",
  "GEMINI_LIVE_MODEL=$LiveModel",
  "GEMINI_VOICE_NOTE_MODEL=$VoiceNoteModel",
  "ENVIRONMENT=$Environment",
  "ALLOW_DEMO_RESET=false",
  "CORS_ALLOW_ORIGINS=$CorsAllowOrigins"
)
if ($AdminApiKey) {
  $envVars += "ADMIN_API_KEY=$AdminApiKey"
}

gcloud run deploy $ServiceName `
  --source . `
  --region $Region `
  --allow-unauthenticated `
  --session-affinity `
  --min-instances=1 `
  --timeout=3600 `
  --set-env-vars ($envVars -join ",")

Write-Host "`nDeployed! Use the https://*.run.app URL for live demos, /api/go-live-check, and Meta WhatsApp Webhook (/webhook/whatsapp)." -ForegroundColor Green
