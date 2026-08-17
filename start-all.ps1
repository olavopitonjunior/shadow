# Start Shadow MVP - All Services
# Usage: .\start-all.ps1
#
# Services:
#   Agent       http://localhost:8090  (background job)
#   Gateway     http://localhost:18790 (new window)
#   Admin API   http://localhost:8099  (new window)
#   Frontend    http://localhost:5173  (foreground)

Write-Host ""
Write-Host "  Shadow MVP - Starting all services" -ForegroundColor Cyan
Write-Host "  ===================================" -ForegroundColor Cyan
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentDir = Join-Path $root "shadow\agent"
$gatewayDir = Join-Path $root "shadow\gateway"
$apiDir = Join-Path $root "apps\admin-api"
$uiDir = Join-Path $root "apps\admin"
$envFile = Join-Path $root ".env"

# Load .env from root if exists
function Set-EnvFromFile {
    param([string]$filePath)
    if (-not (Test-Path $filePath)) { return }
    Get-Content $filePath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not ($line -match "=")) { return }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($key) { Set-Item -Path "Env:$key" -Value $value }
    }
}

Set-EnvFromFile $envFile

# 0. Evolution API (Docker) - only if channel enabled
if ($env:SHADOW_CHANNEL_ENABLED -eq "true" -and $env:SHADOW_CHANNEL_ADAPTER -eq "evolution") {
    Write-Host "  [0/4] Evolution API starting on :8080..." -ForegroundColor Magenta
    $running = docker ps --filter "name=shadow-evolution" --format "{{.Names}}" 2>$null
    if ($running -eq "shadow-evolution") {
        Write-Host "        Already running." -ForegroundColor DarkGray
    } else {
        $apiKey = if ($env:EVOLUTION_API_KEY) { $env:EVOLUTION_API_KEY } else { "shadow-evo-key" }
        docker run -d --name shadow-evolution `
            -p 8080:8080 `
            -e AUTHENTICATION_API_KEY=$apiKey `
            -e WEBHOOK_GLOBAL_URL=http://host.docker.internal:8090/webhook/channel `
            -e WEBHOOK_GLOBAL_ENABLED=true `
            -v "${root}\shadow\data\evolution:/evolution/store" `
            atendai/evolution-api 2>$null
        if ($LASTEXITCODE -ne 0) {
            # Container may exist but be stopped
            docker start shadow-evolution 2>$null
        }
        Write-Host "        Started. Dashboard: http://localhost:8080" -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 3
}

# 1. Agent (background job)
Write-Host "  [1/4] Agent starting on :8090..." -ForegroundColor Green
$agentJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    & ".\.venv\Scripts\python.exe" main.py
} -ArgumentList $agentDir

Start-Sleep -Seconds 2

# 2. Gateway (new window)
Write-Host "  [2/4] Gateway starting on :18790..." -ForegroundColor Green
$gwCmd = "Set-Location '$gatewayDir'; Write-Host 'Shadow Gateway' -ForegroundColor Cyan; npm start"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $gwCmd

Start-Sleep -Seconds 1

# 3. Admin API (new window)
Write-Host "  [3/4] Admin API starting on :8099..." -ForegroundColor Green
$apiCmd = "Set-Location '$apiDir'; Write-Host 'Shadow Admin API' -ForegroundColor Cyan; python -m uvicorn main:app --host 127.0.0.1 --port 8099"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

Start-Sleep -Seconds 1

# 4. Frontend (foreground)
Write-Host "  [4/4] Frontend starting on :5173..." -ForegroundColor Green
Write-Host ""
Write-Host "  All services launched. Frontend running below." -ForegroundColor Yellow
Write-Host "  Close this window to stop the frontend." -ForegroundColor Yellow
Write-Host "  Close other PowerShell windows to stop their services." -ForegroundColor Yellow
Write-Host ""

Set-Location $uiDir
if (-not (Test-Path (Join-Path $uiDir "node_modules"))) {
    npm install
}
npm run dev

# Cleanup when frontend exits
Write-Host ""
Write-Host "  Stopping agent background job..." -ForegroundColor Yellow
Stop-Job $agentJob -ErrorAction SilentlyContinue
Remove-Job $agentJob -ErrorAction SilentlyContinue
Write-Host "  Done. Close other windows manually." -ForegroundColor Yellow
