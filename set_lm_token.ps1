# set_lm_token.ps1 - paste your LM Studio API key once and wire SentinelAI
param([string]$Token)
if (-not $Token) { Write-Host "Usage: .\set_lm_token.ps1 <paste-your-token-here>"; exit 1 }
[Environment]::SetEnvironmentVariable("LM_STUDIO_API_KEY",$Token,"User")
$env:LM_STUDIO_API_KEY=$Token
Write-Host "Set LM_STUDIO_API_KEY for current user (persists after restart)."
Write-Host "Testing LM Studio..."
try {
  $h=@{"Authorization"="Bearer $Token"; "Content-Type"="application/json"}
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:1234/v1/models" -Headers $h -TimeoutSec 5 -UseBasicParsing
  Write-Host "SUCCESS: LM Studio accepted token ($($r.StatusCode))"
  $r.Content | ConvertFrom-Json | ConvertTo-Json -Depth 2 | Select-Object -First 20
} catch { Write-Host "FAIL: $($_.Exception.Message)"; if ($_.ErrorDetails.Message){ $_.ErrorDetails.Message } }
