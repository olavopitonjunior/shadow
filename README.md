# Shadow MVP

Minimal backend for the Shadow WhatsApp assistant.

This repo contains:
- Supabase Edge Functions (shadow-webhook, shadow-admin, shadow-reminder)
- Supabase migrations for Shadow tables
- A small local folder `shadow/` with reference docs and schema notes

## Requirements
- Node.js (for Supabase CLI)
- Supabase CLI

## Setup (local)
1) Copy env example

```
copy supabase\functions\.env.example supabase\functions\.env.local
```

2) Start Supabase locally

```
cd supabase
npx supabase start
```

3) Apply migrations

```
npx supabase db push
```

4) Deploy functions (remote)

```
npx supabase functions deploy shadow-webhook --no-verify-jwt
npx supabase functions deploy shadow-admin --no-verify-jwt
npx supabase functions deploy shadow-reminder --no-verify-jwt
```

## Webhook configuration
Point your WhatsApp provider to:

```
https://<project-ref>.supabase.co/functions/v1/shadow-webhook
```

## Admin API
Use the access code stored in `access_codes` (default: ADMIN001) to manage config.

Example request:

```
POST https://<project-ref>.supabase.co/functions/v1/shadow-admin
Authorization: Bearer <SUPABASE_ANON_KEY>
Content-Type: application/json

{
  "action": "get_config",
  "access_code": "ADMIN001"
}
```

## Notes
- The Shadow replies only to the configured owner phone.
- Contacts are inferred from messages; no access to phone contacts.
- Supports Evolution API and Z-API if configured via secrets.

## Admin (local only)
Um painel administrativo local foi adicionado para monitoramento sem expor mensagens.

- API: `apps/admin-api` (FastAPI, localhost)
- UI: `apps/admin` (React/Vite, localhost)

O painel exibe apenas métricas e metadados agregados (sem conteúdo de mensagens).
