# Shadow A.I. - Testes (MVP)

## Pre-requisitos
- Agent e Gateway rodando
- Token configurado: SHADOW_AGENT_TOKEN (agent e gateway)
- Supabase migrations aplicadas

## 1) Health check
- Agent: GET http://127.0.0.1:8090/health

## 2) Fluxo WhatsApp (owner)
No self-chat:
1. ping
   - Esperado: "Shadow online."
2. cria tarefa: ligar para o Joao amanha 10h
   - Esperado: confirma tarefa criada
3. lembrete: cobrar contrato sexta 14h
   - Esperado: confirma lembrete
4. reuniao: call com Carla quinta 15h
   - Esperado: confirma compromisso
5. mostrar tarefas
   - Esperado: lista de tarefas pendentes
6. resumo do dia
   - Esperado: resumo imediato

## 3) Ingestao silenciosa (contatos)
- Envie uma mensagem de um contato (nao-owner)
- Esperado: Shadow nao responde
- Verifique Supabase: shadow_contacts atualizado

## 4) Endpoints com token
Use o token do agent:
Header: Authorization: Bearer <token>

Exemplos (PowerShell):
- Invoke-RestMethod http://127.0.0.1:8090/summary -Headers @{ Authorization = "Bearer <token>" }
- Invoke-RestMethod http://127.0.0.1:8090/today -Headers @{ Authorization = "Bearer <token>" }
- Invoke-RestMethod http://127.0.0.1:8090/contacts?limit=10 -Headers @{ Authorization = "Bearer <token>" }
- Invoke-RestMethod http://127.0.0.1:8090/contacts/+5511999999999/timeline?limit=10 -Headers @{ Authorization = "Bearer <token>" }

## 5) Scheduler
- Rodar scheduler: python scheduler.py
- Forcar lembrete com horario no passado
- Esperado: mensagem enviada via gateway

## 6) Supabase verificacoes
- shadow_conversations: chat_id preenchido
- shadow_messages: conversation_id preenchido
- shadow_tasks / shadow_appointments / shadow_reminders: registros criados
- shadow_interactions: logs de comandos

## 7) Regressao (seguranca)
- Se SHADOW_AGENT_TOKEN estiver definido, qualquer chamada sem token deve dar 401

## 8) Smoke script
Se `SHADOW_AGENT_TOKEN` estiver no ambiente ou no `shadow/agent/.env`, o script detecta automaticamente.
```powershell
.\shadow\scripts\smoke.ps1 -OwnerPhone "+5511999999999"
```
Ou informe manualmente:
```powershell
.\shadow\scripts\smoke.ps1 -Token "<token>" -OwnerPhone "+5511999999999"
```
