# Start Shadow MVP - Agent + Gateway
# Usage: .\start-shadow.ps1

Write-Host "Starting Shadow MVP..." -ForegroundColor Cyan

# Start Agent in background
$agentJob = Start-Job -ScriptBlock {
    Set-Location "c:\Users\User\OneDrive\Desktop\Projetos Web\shadow_mvp\shadow\agent"
    & ".\.venv\Scripts\python.exe" main.py
}

Write-Host "Agent starting..." -ForegroundColor Green

# Wait a bit for agent to be ready
Start-Sleep -Seconds 2

# Start Gateway in foreground (shows QR code)
Set-Location "c:\Users\User\OneDrive\Desktop\Projetos Web\shadow_mvp\shadow\gateway"
Write-Host "Gateway starting (QR code will appear)..." -ForegroundColor Green
npm start

# When gateway exits, stop agent
Stop-Job $agentJob
Remove-Job $agentJob
