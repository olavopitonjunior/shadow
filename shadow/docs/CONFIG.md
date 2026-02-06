# Shadow A.I. - Configuracoes

## Gateway (.env)
- `SHADOW_OWNER_E164`: numero do dono (E.164, ex: +5511999999999)
- `SHADOW_AGENT_URL`: endpoint do agent (`http://127.0.0.1:8090/process`)
- `SHADOW_AGENT_TOKEN`: token para acessar o agent
- `SHADOW_AUTH_DIR`: pasta de credenciais do WhatsApp Web
- `SHADOW_TRIGGER_TOKENS`: gatilhos de resposta em grupos (ex: `@shadow,/shadow,shadow:`)
- `SHADOW_GROUP_TRIGGER_REQUIRED`: se true, so responde em grupo quando ha gatilho
- `SHADOW_DM_TRIGGER_REQUIRED`: se true, so responde em DM quando ha gatilho
- `SHADOW_IGNORE_FROM_ME`: evita loop (ignora mensagens enviadas pelo bot)
- `SHADOW_GATEWAY_PORT`: porta HTTP do gateway (endpoint `/send`)

## Agent (.env)
- `SHADOW_OWNER_E164`: mesmo numero do gateway
- `SHADOW_DB_PATH`: caminho do SQLite local (fallback)
- `SHADOW_GATEWAY_SEND_URL`: endpoint do gateway para enviar lembretes (`http://127.0.0.1:18790/send`)
- `SUPABASE_URL`: URL do projeto Supabase
- `SUPABASE_KEY`: service role key (necessaria para escrita)
- `SHADOW_USE_SUPABASE`: habilita Supabase (`true`/`false`)
- `SHADOW_DAILY_SUMMARY_HOUR_UTC`: hora do resumo diario (UTC)
- `SHADOW_AGENT_TOKEN`: token para autenticar requests no agent
- `SHADOW_MASTER_KEY`: chave base64 (32 bytes) para criptografia em repouso

## Admin (local)
- `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` (apps/admin-api)
- `ADMIN_API_TOKEN` (opcional, recomendado)

---

## Mapeamento (inspirado no Moltbot)
- allowlist / owner: `SHADOW_OWNER_E164`
- mention gating: `SHADOW_TRIGGER_TOKENS` + `SHADOW_GROUP_TRIGGER_REQUIRED`
- self-chat mode: usar o proprio numero (owner)
- debounce/dedupe: implementado no gateway via filtro de mensagens repetidas
