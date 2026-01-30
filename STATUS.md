# Shadow MVP - Status do Projeto

> **Última atualização:** 2026-01-29
> **Versão:** 1.0.0
> **Fase atual:** ✅ MVP Completo - Pronto para Testes

---

## Progresso Geral

```
[██████████] 100% MVP Concluído!
```

| Fase | Status | Progresso |
|------|--------|-----------|
| Fase 1: Fundação | ✅ Concluída | 100% |
| Fase 2: Sessões e Contexto | ✅ Concluída | 100% |
| Fase 3: Segurança | ✅ Concluída | 100% |
| Fase 4: Mídia | ✅ Concluída | 100% |
| Fase 5: Hooks e Plugins | ✅ Concluída | 100% |
| Fase 6: Polimento MVP | ✅ Concluída | 100% |

---

## Checklist de Implementação

### Fase 1: Fundação
- [x] Estrutura básica do projeto
- [x] WhatsApp Gateway (Baileys)
- [x] Agent FastAPI funcionando
- [x] Storage dual (SQLite + Supabase)
- [x] Intent detection em português
- [x] Criar STATUS.md
- [x] Implementar CronService (`cron_service.py`)
- [x] Migration `shadow_cron_jobs` (015)
- [x] Agendamento de lembretes implementado

### Fase 2: Sessões e Contexto
- [x] Criar `sessions.py` com SessionStore
- [x] Migration `shadow_sessions` (016)
- [x] Context window (últimas 10 mensagens)
- [x] Integrar sessões no message_handler
- [x] Comando `/contexto` para ver histórico
- [x] Continuidade de conversa implementada

### Fase 3: Segurança
- [x] Criar `security.py` com audit framework
- [x] Rate limiting por telefone (RateLimiter)
- [x] Validação de secrets expostos (SecurityAudit)
- [x] AccessPolicy (owner_only, allowlist, open)
- [x] Endpoint `/audit` para diagnóstico
- [x] Endpoint `/audit/summary` para resumo
- [x] Endpoint `/rate-limit` para info de limite
- [x] Proteções implementadas

### Fase 4: Mídia
- [x] Criar `media.py` com download/upload
- [x] Transcrição de áudio (Gemini/Whisper)
- [x] OCR de imagens (Gemini Vision)
- [x] Extração de texto de PDFs
- [x] Extrair tarefas de áudios
- [x] Fluxo de mídia implementado

### Fase 5: Hooks e Plugins
- [x] Expandir hooks em `plugins/types.py` (20+ hooks)
- [x] Plugin de analytics melhorado
- [x] Plugin de notificações (via hooks)
- [x] Documentar API de plugins (em types.py)
- [x] Ciclo de vida implementado

### Fase 6: Polimento MVP
- [x] Envio real de lembretes (Evolution API + Z-API)
- [x] Onboarding flow (comando /help)
- [x] Logs estruturados (`logger.py`)
- [x] `.env.example` completo
- [x] Documentação em STATUS.md

---

## Ferramentas e Integrações

| Ferramenta | Camada | Propósito | Status |
|------------|--------|-----------|--------|
| **Baileys 6.7** | Gateway | Conexão WhatsApp Web via WebSocket | ✅ Funcionando |
| **FastAPI** | Agent | API REST do agente Python | ✅ Funcionando |
| **Supabase** | Storage | Banco PostgreSQL + Edge Functions | ✅ Funcionando |
| **SQLite** | Storage | Banco local para desenvolvimento | ✅ Funcionando |
| **Gemini AI** | NLP | Análise de mensagens e mídia | ✅ Opcional |
| **dateparser** | NLP | Parsing de datas em português | ✅ Funcionando |
| **httpx** | HTTP | Cliente async para requisições | ✅ Funcionando |
| **CronService** | Scheduler | Agendamento robusto de tarefas | ✅ Implementado |
| **SessionStore** | Context | Gerenciamento de sessões/contexto | ✅ Implementado |
| **SecurityAudit** | Security | Framework de auditoria | ✅ Implementado |
| **RateLimiter** | Security | Limite de requisições por usuário | ✅ Implementado |
| **AccessPolicy** | Security | Controle de acesso (owner/allowlist) | ✅ Implementado |
| **MediaProcessor** | Media | Download/transcrição/OCR | ✅ Implementado |

### Legenda
- ✅ Funcionando - Implementado e testado
- 🔄 Implementando - Em desenvolvimento
- ⏳ Pendente - Aguardando implementação
- ❌ Bloqueado - Dependência não resolvida

---

## Jornada do Usuário

### 1. Instalação

```bash
# 1. Clonar repositório
git clone https://github.com/seu-usuario/shadow_mvp.git
cd shadow_mvp

# 2. Configurar ambiente
cp .env.example .env
# Editar .env com suas credenciais:
# - OWNER_PHONE=5511999999999
# - SUPABASE_URL=https://xxx.supabase.co
# - SUPABASE_KEY=eyJ...

# 3. Iniciar banco local (desenvolvimento)
cd supabase
npx supabase start
npx supabase db push

# 4. Iniciar Gateway (Terminal 1)
cd shadow/gateway
npm install
npm start
# → Escanear QR code que aparece no terminal

# 5. Iniciar Agent (Terminal 2)
cd shadow/agent
pip install -r requirements.txt
python -m main
# → Servidor rodando em http://localhost:8000
```

### 2. Primeiro Uso

| Passo | Ação no WhatsApp | Resposta Esperada |
|-------|------------------|-------------------|
| 1 | Enviar "oi" ou "olá" | Boas-vindas + comandos disponíveis |
| 2 | "criar tarefa: testar shadow" | "Tarefa criada: testar shadow" |
| 3 | "mostrar tarefas" | Lista de tarefas pendentes |
| 4 | "lembrete: reunião amanhã 9h" | "Lembrete agendado para..." |
| 5 | "agenda" | Compromissos do dia |

### 3. Uso Diário

| Horário | Evento | Descrição |
|---------|--------|-----------|
| 09:00 | Resumo automático | Shadow envia resumo de tarefas e compromissos |
| Durante o dia | Comandos via chat | Criar/listar tarefas, agendar, consultar |
| Configurado | Lembretes | Notificações nos horários definidos |

### 4. Comandos Disponíveis

| Comando | Exemplo | Ação |
|---------|---------|------|
| Criar tarefa | "criar tarefa: revisar código" | Adiciona tarefa pendente |
| Listar tarefas | "mostrar tarefas" | Exibe tarefas pendentes |
| Criar compromisso | "reunião: call com cliente amanhã 14h" | Agenda compromisso |
| Ver agenda | "agenda" ou "compromissos" | Lista compromissos futuros |
| Criar lembrete | "lembrete: pagar conta em 2 dias" | Agenda notificação |
| Resumo | "resumo do dia" | Visão geral de tarefas/agenda |

### 5. Coleta de Dados

| Dado | Origem | Armazenamento | Uso |
|------|--------|---------------|-----|
| Mensagens | WhatsApp | Supabase/SQLite | Histórico e contexto |
| Contatos | Extração automática | Tabela `shadow_contacts` | CRM e timeline |
| Tarefas | Intent detection | Tabela `shadow_tasks` | Gestão de atividades |
| Compromissos | Intent detection | Tabela `shadow_appointments` | Agenda |
| Lembretes | Intent detection | Tabela `shadow_reminders` | Notificações |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      SHADOW MVP 2.0                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 WhatsApp (Baileys)                    │   │
│  │            Gateway Node.js - Porta 3001               │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  Agent Python                         │   │
│  │              FastAPI - Porta 8000                     │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │   │
│  │  │ Intent  │ │ Session │ │  Cron   │ │ Media   │     │   │
│  │  │ Handler │ │  Store  │ │ Service │ │Processor│     │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘     │   │
│  │       └───────────┴───────────┴───────────┘          │   │
│  │                         │                             │   │
│  └─────────────────────────┼────────────────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Storage Layer                      │   │
│  │         SQLite (local) │ Supabase (produção)         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Estrutura de Arquivos

```
shadow_mvp/
├── STATUS.md                    # ← Este arquivo
├── README.md                    # Documentação geral
├── .env.example                 # Template de configuração
│
├── shadow/
│   ├── agent/                   # Core Python
│   │   ├── main.py              # FastAPI server
│   │   ├── message_handler.py   # Intent detection
│   │   ├── storage.py           # Dual backend storage
│   │   ├── scheduler.py         # Job scheduler (→ CronService)
│   │   ├── config.py            # Configuration
│   │   ├── logger.py            # 🆕 Logs estruturados
│   │   ├── cron_service.py      # 🆕 Agendamento robusto
│   │   ├── sessions.py          # 🆕 Session management
│   │   ├── security.py          # 🆕 Audit framework
│   │   ├── media.py             # 🆕 Media processing
│   │   └── plugins/
│   │       ├── types.py         # Hook definitions
│   │       ├── registry.py      # Plugin registry
│   │       └── installed/       # Plugins ativos
│   │
│   ├── gateway/                 # Node.js WhatsApp
│   │   └── src/
│   │       ├── index.js         # HTTP server
│   │       ├── wa-session.js    # Baileys connection
│   │       ├── agent-client.js  # Agent HTTP client
│   │       └── normalize.js     # Message utilities
│   │
│   └── migrations/              # SQL migrations (SQLite)
│
├── supabase/
│   ├── functions/               # Edge Functions
│   │   ├── shadow-webhook/      # Webhook processor
│   │   ├── shadow-admin/        # Admin API
│   │   └── shadow-reminder/     # Reminder scheduler
│   │
│   └── migrations/              # PostgreSQL migrations
│
└── moltbot/                     # Referência (padrões a adotar)
```

---

## Changelog

### [2026-01-29] - v1.0.0 (MVP Completo)

**Finalização do MVP:**
- `shadow/agent/logger.py` - Sistema de logs estruturados (JSON/texto)
- `.env.example` - Template completo de configuração (90 variáveis)
- `plugins/types.py` - Expandido para 20+ hooks:
  - MESSAGE_RECEIVED, MESSAGE_SENDING, MESSAGE_SENT
  - BEFORE_TOOL_CALL, AFTER_TOOL_CALL
  - SESSION_START, SESSION_END, SESSION_EXPIRED
  - TASK_CREATED, TASK_COMPLETED, TASK_DELETED
  - REMINDER_CREATED, REMINDER_TRIGGERED, REMINDER_SENT
  - CRON_JOB_START, CRON_JOB_COMPLETE, CRON_JOB_ERROR
  - ACCESS_DENIED, RATE_LIMITED, SECURITY_ALERT
  - MEDIA_RECEIVED, MEDIA_PROCESSED

**Envio real de lembretes:**
- `supabase/functions/shadow-reminder/index.ts` refatorado
- Suporte a Evolution API como gateway principal
- Suporte a Z-API como gateway de fallback
- Retry automático em caso de falha

---

### [2026-01-29] - v0.2.0-beta (Integração Completa)

**Novos arquivos criados:**
- `shadow/agent/cron_service.py` - CronService robusto com suporte a cron expressions
- `shadow/agent/sessions.py` - SessionStore com context window
- `shadow/agent/security.py` - SecurityAudit, RateLimiter, AccessPolicy
- `shadow/agent/media.py` - MediaProcessor com Gemini/Whisper

**Migrations adicionadas:**
- `015_shadow_cron_jobs.sql` - Tabela de jobs agendados
- `016_shadow_sessions.sql` - Tabela de sessões com contexto
- `004_cron_jobs_sessions.sql` - Versão SQLite

**Integração completa:**
- `message_handler.py` agora usa SessionStore para contexto
- Novo comando `/contexto` para ver histórico de conversa
- `main.py` refatorado com novos endpoints:
  - `GET /audit` - Auditoria de segurança completa
  - `GET /audit/summary` - Resumo da auditoria
  - `GET /sessions` - Lista sessões ativas
  - `GET /sessions/{id}` - Detalhes de uma sessão
  - `DELETE /sessions/{id}` - Remove sessão
  - `POST /sessions/{id}/clear` - Limpa contexto
  - `GET /rate-limit` - Info de rate limit
  - `GET /status` - Status completo do serviço
- Rate limiting integrado no endpoint `/process`
- AccessPolicy verificando acesso no `/process`
- `requirements.txt` atualizado com `croniter` e `supabase`

**Atualizações:**
- `scheduler.py` refatorado para usar CronService
- STATUS.md criado para controle do projeto
- Documentada jornada do usuário e arquitetura

### [Anterior] - v0.1.0
- Estrutura inicial do projeto
- WhatsApp Gateway com Baileys
- Agent FastAPI básico
- Storage dual (SQLite + Supabase)
- Intent detection em português
- Daily summary às 9h UTC

---

## Decisões Técnicas

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Linguagem Agent | Python 3.11+ | Melhor para NLP e dateparser |
| Linguagem Gateway | Node.js | Baileys é JavaScript |
| Banco produção | Supabase | Edge Functions + PostgreSQL |
| Banco local | SQLite | Zero config, portável |
| WhatsApp | Baileys | Open source, sem custo |
| AI opcional | Gemini | Bom custo-benefício |
| Hospedagem | VPS próprio | Controle total |

---

## Métricas de Sucesso MVP

| Métrica | Meta | Atual |
|---------|------|-------|
| Mensagens processadas/dia | 100+ | - |
| Latência média resposta | <3s | - |
| Uptime | 99% | - |
| Tarefas criadas com sucesso | 95% | - |
| Lembretes entregues | 100% | - |

---

## Contato e Suporte

- **Repositório:** [GitHub - shadow_mvp](#)
- **Issues:** Reportar bugs e sugestões
- **Documentação:** `/shadow/docs/`

---

*Este documento é atualizado automaticamente conforme o progresso do projeto.*
