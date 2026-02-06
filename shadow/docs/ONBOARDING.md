# Shadow A.I. - Onboarding (MVP)

Este guia deixa o Shadow funcional em ambiente local (gateway + agent).

## 1) Requisitos
- Node.js 18+
- Python 3.11+
- WhatsApp instalado no celular
- Supabase (projeto criado) ou fallback SQLite

## 2) Banco (Supabase)
1. Crie um projeto no Supabase
2. Rode as migrations:
   - `shadow/migrations/001_shadow_schema.sql`
   - `shadow/migrations/003_conversation_unique_index.sql`
3. Pegue `SUPABASE_URL` e `SUPABASE_KEY` (service role)

## 3) Gateway WhatsApp (Baileys)
```bash
cd shadow/gateway
npm install
cp .env.example .env
```
Edite `.env` e ajuste `SHADOW_OWNER_E164` (seu numero).

Inicie o gateway:
```bash
npm run start
```
O terminal vai mostrar um QR Code. No celular:
**WhatsApp > Linked Devices > Link a device** e escaneie.

## 4) Shadow Agent (Python)
```bash
cd shadow/agent
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```
Configure `SUPABASE_URL` e `SUPABASE_KEY`.

Inicie o agent:
```bash
python main.py
```

## 5) Scheduler (opcional para lembretes)
```bash
python scheduler.py
```

## 6) Teste rapido
No WhatsApp (self-chat):
- `cria tarefa: ligar para o Joao amanha 10h`
- `lembrete: cobrar contrato sexta 14h`
- `reuniao: call com Carla quinta 15h`
- `mostrar tarefas`

Se estiver em grupo, use o gatilho:
- `@shadow cria tarefa: follow-up cliente X`

---

## Dicas
- Quer que o Shadow seja silencioso com clientes? Deixe `SHADOW_REPLY_OWNER_ONLY=true`.
- Para responder em grupos, use `@shadow` ou `/shadow`.
- Para relink: apague `shadow/gateway/auth_info` e refaca o QR.