# Start Shadow Admin (API + UI)
# Usage: .\start-admin.ps1

Write-Host "Starting Shadow Admin..." -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiDir = Join-Path $root "apps\admin-api"
$uiDir = Join-Path $root "apps\admin"
$envFile = Join-Path $root ".env"

function Set-EnvFromFile {
    param([string]$filePath)
    if (-not (Test-Path $filePath)) {
        return
    }
    Get-Content $filePath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }
        if (-not ($line -match "=")) { return }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($key) {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

Set-EnvFromFile $envFile

# Start Admin API in a separate PowerShell window for visibility
$apiCmd = "Set-Location '$apiDir'; $env:ADMIN_API_TOKEN=''; python -m pip install -r requirements.txt; python -m uvicorn main:app --host 127.0.0.1 --port 8099"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

Write-Host "Admin API starting on http://localhost:8099" -ForegroundColor Green

# Start Admin UI in foreground
Set-Location $uiDir
$env:VITE_ADMIN_API_TOKEN = ""
if (-not (Test-Path (Join-Path $uiDir "node_modules"))) {
    npm install
}
Write-Host "Admin UI starting on http://localhost:5173" -ForegroundColor Green
npm run dev
