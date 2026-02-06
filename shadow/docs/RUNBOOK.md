# Shadow A.I. - Runbook (MVP)

## Relink WhatsApp
1) Pare o gateway
2) Apague `shadow/gateway/auth_info`
3) Suba o gateway e escaneie o QR novamente

## Erros comuns
- `agent_unreachable`: o agent nao esta rodando ou URL errada
- `WhatsApp deslogou`: refaca o QR
- Sem resposta em grupo: confirme `@shadow` no texto e `SHADOW_GROUP_TRIGGER_REQUIRED=true`
- Supabase erro de permissao: confirme `SUPABASE_KEY` (service role)
- 401 Unauthorized no agent: confirme `SHADOW_AGENT_TOKEN`

## Endpoints uteis
- `GET /summary` -> contagem de tarefas/compromissos
- `GET /today` -> lista do dia
- `GET /contacts` -> lista de contatos recentes
- `GET /contacts/{phone}/timeline` -> ultimas mensagens do contato

## Comandos WhatsApp (owner)
- `resumo do dia` -> retorna o resumo imediato
- `ping` -> verifica se o Shadow esta online

## Scheduler
- Envia lembretes pendentes
- Envia resumo diario (hora UTC configuravel)

## Logs
- Gateway: logs no terminal
- Agent: logs no terminal

## Backup
- Supabase: dados gerenciados pelo projeto
- Fallback SQLite: `shadow/agent/data/shadow.db`