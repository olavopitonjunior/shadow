param(
  [string]$AgentBaseUrl = "http://127.0.0.1:8090",
  [string]$Token = "",
  [string]$OwnerPhone = "+5511999999999",
  [string]$EnvFile = ""
)

function Get-EnvValue {
  param(
    [string]$Key,
    [string]$Path
  )
  if (-not (Test-Path $Path)) {
    return ""
  }
  foreach ($line in Get-Content $Path) {
    if ($line -match "^\s*#") { continue }
    if ($line -match "^\s*$Key\s*=\s*(.*)\s*$") {
      $value = $Matches[1].Trim()
      if ($value.StartsWith('"') -and $value.EndsWith('"')) {
        return $value.Trim('"')
      }
      if ($value.StartsWith("'") -and $value.EndsWith("'")) {
        return $value.Trim("'")
      }
      return $value
    }
  }
  return ""
}

if ($Token -eq "") {
  $Token = $env:SHADOW_AGENT_TOKEN
}
if ($Token -eq "") {
  if ($EnvFile -eq "") {
    $EnvFile = "shadow/agent/.env"
  }
  $Token = Get-EnvValue -Key "SHADOW_AGENT_TOKEN" -Path $EnvFile
}

$headers = @{}
if ($Token -ne "") {
  $headers["Authorization"] = "Bearer $Token"
  Write-Host "[smoke] token loaded" -ForegroundColor DarkGray
} else {
  Write-Host "[smoke] no token found (set -Token or SHADOW_AGENT_TOKEN)" -ForegroundColor Yellow
}

Write-Host "[smoke] health" -ForegroundColor Cyan
Invoke-RestMethod "$AgentBaseUrl/health" -Headers $headers | Out-Host

Write-Host "[smoke] summary" -ForegroundColor Cyan
Invoke-RestMethod "$AgentBaseUrl/summary" -Headers $headers | Out-Host

Write-Host "[smoke] today" -ForegroundColor Cyan
Invoke-RestMethod "$AgentBaseUrl/today" -Headers $headers | Out-Host

Write-Host "[smoke] contacts" -ForegroundColor Cyan
Invoke-RestMethod "$AgentBaseUrl/contacts?limit=5" -Headers $headers | Out-Host

Write-Host "[smoke] timeline" -ForegroundColor Cyan
Invoke-RestMethod "$AgentBaseUrl/contacts/$OwnerPhone/timeline?limit=5" -Headers $headers | Out-Host
