# Setup Evolution API for Shadow Channel
# Usage: .\setup-evolution.ps1
#
# This script:
#   1. Starts Evolution API via Docker
#   2. Creates the "shadow" instance
#   3. Prints the QR code URL for phone linking
#   4. Updates .env with channel settings

param(
    [string]$ApiKey = "shadow-evo-key",
    [string]$InstanceName = "shadow",
    [int]$Port = 8080
)

Write-Host ""
Write-Host "  Shadow - Evolution API Setup" -ForegroundColor Cyan
Write-Host "  ============================" -ForegroundColor Cyan
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root ".env"

# --- Step 1: Check Docker ---
Write-Host "  [1/5] Checking Docker..." -ForegroundColor Green
$dockerVersion = docker --version 2>$null
if (-not $dockerVersion) {
    Write-Host "  ERROR: Docker is not installed or not in PATH." -ForegroundColor Red
    Write-Host "  Install Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}
Write-Host "        $dockerVersion" -ForegroundColor DarkGray

# --- Step 2: Start container ---
Write-Host "  [2/5] Starting Evolution API container..." -ForegroundColor Green
$running = docker ps --filter "name=shadow-evolution" --format "{{.Names}}" 2>$null
if ($running -eq "shadow-evolution") {
    Write-Host "        Already running on port $Port." -ForegroundColor DarkGray
} else {
    # Remove stopped container if exists
    docker rm shadow-evolution 2>$null | Out-Null

    $dataDir = Join-Path $root "shadow\data\evolution"
    if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }

    docker run -d --name shadow-evolution `
        -p "${Port}:8080" `
        -e "AUTHENTICATION_API_KEY=$ApiKey" `
        -e "WEBHOOK_GLOBAL_URL=http://host.docker.internal:8090/webhook/channel" `
        -e "WEBHOOK_GLOBAL_ENABLED=true" `
        -e "WEBHOOK_GLOBAL_WEBHOOK_BY_EVENTS=false" `
        -v "${dataDir}:/evolution/store" `
        atendai/evolution-api

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Failed to start container." -ForegroundColor Red
        exit 1
    }
    Write-Host "        Container started." -ForegroundColor DarkGray
}

# --- Step 3: Wait for API to be ready ---
Write-Host "  [3/5] Waiting for API to be ready..." -ForegroundColor Green
$maxAttempts = 30
$attempt = 0
$ready = $false
while ($attempt -lt $maxAttempts) {
    $attempt++
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$Port" -Method GET -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Write-Host "  ERROR: Evolution API did not start within 60 seconds." -ForegroundColor Red
    Write-Host "  Check logs: docker logs shadow-evolution" -ForegroundColor Yellow
    exit 1
}
Write-Host "        API is ready." -ForegroundColor DarkGray

# --- Step 4: Create instance ---
Write-Host "  [4/5] Creating instance '$InstanceName'..." -ForegroundColor Green
$headers = @{
    "apikey" = $ApiKey
    "Content-Type" = "application/json"
}
$body = @{
    instanceName = $InstanceName
    integration = "WHATSAPP-BAILEYS"
    qrcode = $true
} | ConvertTo-Json

try {
    $result = Invoke-RestMethod -Uri "http://localhost:$Port/instance/create" `
        -Method POST -Headers $headers -Body $body -ErrorAction Stop

    if ($result.qrcode) {
        Write-Host ""
        Write-Host "  QR Code ready! Scan it to connect your phone:" -ForegroundColor Yellow
        Write-Host "  http://localhost:$Port/instance/connect/$InstanceName" -ForegroundColor Cyan
        Write-Host ""
        if ($result.qrcode.base64) {
            Write-Host "  Or open this in your browser to see the QR code:" -ForegroundColor Yellow
            Write-Host "  http://localhost:$Port/instance/connect/$InstanceName" -ForegroundColor Cyan
        }
    } else {
        Write-Host "        Instance created. Connect at:" -ForegroundColor DarkGray
        Write-Host "        http://localhost:$Port/instance/connect/$InstanceName" -ForegroundColor Cyan
    }
} catch {
    $err = $_.Exception.Message
    if ($err -match "already" -or $err -match "exists") {
        Write-Host "        Instance '$InstanceName' already exists." -ForegroundColor DarkGray
        Write-Host "        Connect at: http://localhost:$Port/instance/connect/$InstanceName" -ForegroundColor Cyan
    } else {
        Write-Host "  WARNING: Could not create instance: $err" -ForegroundColor Yellow
        Write-Host "  You can create it manually via the API." -ForegroundColor Yellow
    }
}

# --- Step 5: Update .env ---
Write-Host ""
Write-Host "  [5/5] Updating .env..." -ForegroundColor Green

function Set-EnvVar {
    param([string]$file, [string]$key, [string]$value)
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        if ($content -match "(?m)^$key=") {
            $content = $content -replace "(?m)^$key=.*$", "$key=$value"
        } else {
            $content = $content.TrimEnd() + "`n$key=$value`n"
        }
        Set-Content -Path $file -Value $content -NoNewline
    } else {
        "$key=$value`n" | Out-File -FilePath $file -Encoding utf8
    }
}

Set-EnvVar $envFile "SHADOW_CHANNEL_ENABLED" "true"
Set-EnvVar $envFile "SHADOW_CHANNEL_ADAPTER" "evolution"
Set-EnvVar $envFile "EVOLUTION_API_URL" "http://localhost:$Port"
Set-EnvVar $envFile "EVOLUTION_API_KEY" $ApiKey
Set-EnvVar $envFile "EVOLUTION_INSTANCE" $InstanceName

Write-Host "        .env updated with channel settings." -ForegroundColor DarkGray

# --- Done ---
Write-Host ""
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1. Scan the QR code at http://localhost:$Port/instance/connect/$InstanceName" -ForegroundColor White
Write-Host "    2. Run .\start-all.ps1 to start Shadow with channel enabled" -ForegroundColor White
Write-Host "    3. Send a WhatsApp message to the connected number" -ForegroundColor White
Write-Host ""
