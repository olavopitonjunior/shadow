function Test-Shadow {
    param(
        [string]$TestId,
        [string]$Description,
        [string]$Message
    )
    
    Write-Host ""
    Write-Host ("=== TEST " + $TestId + " - " + $Description + " ===") -ForegroundColor Cyan
    
    $body = @{
        body = $Message
        sender_e164 = "+5511947174266"
        owner_e164 = "+5511947174266"
        is_owner = $true
        should_reply = $true
        chat_id = "5511947174266@s.whatsapp.net"
        chat_type = "direct"
    } | ConvertTo-Json
    
    try {
        $r = Invoke-RestMethod -Method Post -Uri http://localhost:8090/process -ContentType 'application/json' -Body $body -TimeoutSec 25
        Write-Host ("Reply: " + $r.reply)
        Write-Host ("Intent: " + $r.intent)
        return @{ TestId = $TestId; Status = "PASS"; Reply = $r.reply; Intent = $r.intent }
    } catch {
        Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
        return @{ TestId = $TestId; Status = "FAIL"; Error = $_.Exception.Message }
    }
}

$results = @()

# Phase 1 - Basic Flow
Write-Host ""
Write-Host "========== PHASE 1 - BASIC FLOW ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "1.1" -Description "Basic greeting - oi" -Message "oi"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "1.2" -Description "Ping" -Message "ping"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "1.3" -Description "Help - ajuda" -Message "ajuda"
Start-Sleep -Seconds 2

# Phase 2 - Tasks
Write-Host ""
Write-Host "========== PHASE 2 - TASKS ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "2.1" -Description "Create task - comprar pao amanha" -Message "criar tarefa comprar pao amanha"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "2.2" -Description "List tasks" -Message "listar tarefas"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "2.3" -Description "Complete task - comprar pao" -Message "completar tarefa comprar pao"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "2.4" -Description "List tasks after completion" -Message "listar tarefas"
Start-Sleep -Seconds 2

# Phase 3 - Appointments
Write-Host ""
Write-Host "========== PHASE 3 - APPOINTMENTS ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "3.1" -Description "Create appointment - reuniao segunda 14h" -Message "agendar reuniao segunda 14h com equipe"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "3.2" -Description "List appointments - compromissos" -Message "compromissos"
Start-Sleep -Seconds 2

# Phase 4 - Reminders
Write-Host ""
Write-Host "========== PHASE 4 - REMINDERS ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "4.1" -Description "Create reminder - 5 min beber agua" -Message "me lembre em 5 minutos de beber agua"
Start-Sleep -Seconds 2

# Phase 5 - Settings
Write-Host ""
Write-Host "========== PHASE 5 - SETTINGS ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "5.1" -Description "Get settings - minhas configuracoes" -Message "minhas configuracoes"
Start-Sleep -Seconds 2

# Phase 6 - ReAct Agent (complex queries)
Write-Host ""
Write-Host "========== PHASE 6 - REACT AGENT ==========" -ForegroundColor Yellow
$results += Test-Shadow -TestId "6.1" -Description "Count pending tasks" -Message "quantas tarefas eu tenho pendentes?"
Start-Sleep -Seconds 2
$results += Test-Shadow -TestId "6.2" -Description "What do I have today" -Message "o que eu tenho pra fazer hoje?"
Start-Sleep -Seconds 2

# Summary
Write-Host ""
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "           TEST SUMMARY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

$passed = 0
$failed = 0
$fallback = 0

foreach ($r in $results) {
    $status = $r.Status
    $reply = $r.Reply
    
    if ($status -eq "PASS") {
        if ($reply -match "Anotado|Ocorreu um erro|erro interno|desculpe.*erro") {
            $status = "FALLBACK"
            $fallback++
            $color = "Yellow"
        } else {
            $passed++
            $color = "Green"
        }
    } else {
        $failed++
        $color = "Red"
    }
    
    if ($reply -and $reply.Length -gt 80) {
        $shortReply = $reply.Substring(0,80) + "..."
    } elseif ($reply) {
        $shortReply = $reply
    } else {
        $shortReply = $r.Error
    }
    Write-Host ("[$status] T" + $r.TestId + " - " + $shortReply) -ForegroundColor $color
}

Write-Host ""
Write-Host "----------------------------------------"
Write-Host ("PASSED:   " + $passed + " / " + $results.Count) -ForegroundColor Green
Write-Host ("FALLBACK: " + $fallback + " / " + $results.Count) -ForegroundColor Yellow
Write-Host ("FAILED:   " + $failed + " / " + $results.Count) -ForegroundColor Red
Write-Host "----------------------------------------"
