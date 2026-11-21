# 1-Command Google Cloud Run Deployment for DeliverEx Live
# Usage: .\deploy_cloud_run.ps1 -ProjectId "your-gcp-project" -GeminiApiKey "AIza..."

param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [Parameter(Mandatory=$true)][string]$GeminiApiKey,
  [string]$Region = "asia-south1",
  [string]$ServiceName = "deliverex-live"
)

gcloud config set project $ProjectId
gcloud run deploy $ServiceName `
  --source . `
  --region $Region `
  --allow-unauthenticated `
  --session-affinity `
  --timeout=3600 `
  --set-env-vars "GEMINI_API_KEY=$GeminiApiKey,GEMINI_LIVE_MODEL=gemini-3.8-live,GEMINI_VOICE_NOTE_MODEL=gemini-3.8-flash"

Write-Host "`nDeployed! Use the https://*.run.app URL for live demos and Meta WhatsApp Webhook (/webhook/whatsapp)." -ForegroundColor Green
