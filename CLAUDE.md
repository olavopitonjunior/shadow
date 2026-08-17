# Shadow MVP - Contexto Claude Code

## Quick Reference
- **Projeto**: Assistente WhatsApp + CRM invisível com orquestração multi-agente
- **Fase**: LangGraph Multi-Agent (Supervisor + 5 Workers) com 38 tools
- **Backend**: Supabase PostgreSQL (opcional) + SQLite (local)
- **LLM**: Claude (Supervisor + Workers), Gemini (mídia/transcrição + fallback)
- **Gateway**: Baileys (porta 18790) + Z-API (REST) via adapter pattern
- **Orchestration**: LangGraph StateGraph com checkpointing, SSE streaming, retry/fallback
- **Dashboard**: React + Tailwind + Radix + Recharts (12 páginas)

## Arquitetura Multi-Agente (LangGraph)

### Visão Geral
```
WhatsApp → Gateway → Supervisor (LLM routing) → Workers → Respond
                         |
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
        CRM Agent   Planner Agent   Analytics Agent
       (14 tools)   (12 tools)      (8 tools)
           ▼             ▼
      DocGen Agent  Collector Agent
       (6 tools)     (5 tools)
```

### Feature Flag
```bash
SHADOW_USE_LANGGRAPH=true   # Ativa LangGraph (default: false = ReActAgent legado)
```

### Three-Tier Routing
1. **Fast-path** (0ms, no LLM): "oi", "tarefas", "ping", "ajuda" → resposta direta
2. **Keyword** (0ms, no LLM): palavras-chave → worker específico (planner, crm, etc.)
3. **LLM Supervisor** (500 tokens): mensagens ambíguas/multimodais → LLM decide

### Graph Topology (13 nodes)
```
START → intake → [router]
                   ├─→ fast_path → respond → END
                   ├─→ planner ──┐
                   ├─→ crm ──────┤
                   ├─→ analytics ─┤→ synthesize → [quality_check]
                   ├─→ docgen ───┤                  ├─→ respond → END
                   ├─→ collector ┘                  └─→ rag_retrieve (re-delegate)
                   └─→ rag_retrieve → supervisor_think → [route to worker or respond]
```

### Workers (Subgraphs com ReAct loop próprio)

| Worker | Tools | Função |
|--------|-------|--------|
| **CRM** | 14 | Contatos, memórias, relacionamentos, GDPR forget |
| **Planner** | 12 | Tarefas, compromissos, lembretes, categorias |
| **Analytics** | 8 | Resumos, alertas, métricas, relatórios |
| **DocGen** | 6 | Propostas, contratos, PDF (fpdf2 + Jinja2) |
| **Collector** | 5 | Z-API data mining, importação de contatos |

### RAG Knowledge Base (4 camadas)
1. **Contact Memories** (LanceDB) — `contact_memory.py` ✅ existente
2. **Document Store** (LanceDB) — `knowledge/document_memory.py` chunks com embeddings
3. **Conversation Intelligence** (LanceDB) — `knowledge/conversation_memory.py` resumos
4. **Learned Patterns** (SQLite) — `learning.py` ✅ existente

## Padrões Críticos

### Tool System (38 tools em shadow/agent/tools/)
- Base: `Tool` → `execute(context: ToolContext) -> ToolResult`
- Registry: `ToolRegistry.execute(tool_name, params)`
- LangChain adapter: `graph/adapters/tool_adapter.py` wraps Shadow tools como `StructuredTool`
- Tool loadouts por worker: `WORKER_TOOLS` em `tool_adapter.py`

### Storage Layer (⚠️ CRÍTICO)
**Arquivo**: `shadow/agent/storage/`
- `get_task(id)` → `Task | None` (PODE ser None!)
- `list_tasks()` → `List[Task]` (sempre lista)
- `create_task()` → `Task` (sempre cria)
- **SEMPRE verificar assinatura antes de chamar**

### Contact Resolver Priority
1. Parâmetro explícito
2. `reminder_target` da sessão
3. `last_recipient` da sessão
4. Config default
5. Allowlist fallback

### Gateway Pattern
- **Baileys**: `shadow/gateway/src/index-multi.js` (porta 18790)
- **Z-API**: `graph/adapters/zapi_client.py` (REST com rate limiting)
- **Evolution/Meta Cloud**: `shadow/agent/channels/` (adapter pattern)

### Hardening Patterns
- **Thread safety**: Per-thread lock (`defaultdict(threading.Lock)`) em `graph/__init__.py`
- **Tenant isolation**: Thread IDs = `owner_id:chat_id` — validados em cada invocação
- **Checkpoint DB separado**: `data/shadow_graph.db` (evita lock contention com `shadow.db`)
- **SQL safety**: `query_metrics` usa queries pré-definidas, não SQL bruto
- **Template safety**: Jinja2 `SandboxedEnvironment` + `autoescape=True`
- **Retry + fallback**: 3 tentativas com backoff 2x, fallback para Gemini em rate limit
- **Rollback**: Feature flag `SHADOW_USE_LANGGRAPH` — ReActAgent legado sempre disponível

## Arquivos-Chave

### LangGraph Orchestration
| Componente | Arquivo |
|------------|---------|
| Entry Point (LangGraph) | `shadow/agent/graph/__init__.py` → `run_graph()` |
| State Schema | `shadow/agent/graph/state.py` → `ShadowState`, `WorkerState` |
| Graph Builder | `shadow/agent/graph/builder.py` → 13 nodes, edges, compile |
| Supervisor LLM | `shadow/agent/graph/supervisor.py` → routing decision |
| Three-Tier Router | `shadow/agent/graph/nodes/router.py` |
| Fast-Path | `shadow/agent/graph/nodes/fast_path.py` |
| RAG Retrieval | `shadow/agent/graph/nodes/rag.py` (condicional) |
| Worker Factory | `shadow/agent/graph/workers/base.py` → `build_worker_subgraph()` |
| Tool Adapter | `shadow/agent/graph/adapters/tool_adapter.py` |
| Z-API Client | `shadow/agent/graph/adapters/zapi_client.py` |
| SSE Streaming | `shadow/agent/graph/streaming.py` → `AgentEventBus` |
| Observability | `shadow/agent/graph/observability.py` → LangSmith sampling |

### Legacy (funciona com flag off)
| Componente | Arquivo |
|------------|---------|
| Entry Point (Legacy) | `shadow/agent/message_handler.py` |
| ReAct Agent | `shadow/agent/react_agent.py` |
| Sessions | `shadow/agent/sessions.py` |
| Contact Resolver | `shadow/agent/contact_resolver.py` |

### Knowledge Base
| Componente | Arquivo |
|------------|---------|
| Contact Memory | `shadow/agent/contact_memory.py` (Layer 1) |
| Document Memory | `shadow/agent/knowledge/document_memory.py` (Layer 2) |
| Conversation Memory | `shadow/agent/knowledge/conversation_memory.py` (Layer 3) |
| RAG Engine | `shadow/agent/knowledge/rag_engine.py` (unified) |

### Admin Dashboard
| Componente | Arquivo |
|------------|---------|
| Agent Monitor | `apps/admin/src/pages/AgentMonitor.tsx` (SSE live) |
| CRM | `apps/admin/src/pages/CRM.tsx` (contacts + timeline) |
| Analytics | `apps/admin/src/pages/Analytics.tsx` (charts) |
| Documents | `apps/admin/src/pages/Documents.tsx` (generated docs) |
| Integrations | `apps/admin/src/pages/Integrations.tsx` (services) |
| API: Agents | `apps/admin-api/routers/agents.py` (SSE endpoint) |
| API: CRM | `apps/admin-api/routers/crm.py` |
| API: Analytics | `apps/admin-api/routers/analytics.py` |
| API: Documents | `apps/admin-api/routers/documents.py` |
| API: Integrations | `apps/admin-api/routers/integrations.py` |

### Other
| Componente | Arquivo |
|------------|---------|
| Storage | `shadow/agent/storage/` (package) |
| Tools | `shadow/agent/tools/` (38 tools) |
| Providers | `shadow/agent/providers/` (LiteLLM) |
| MessageBus | `shadow/agent/bus/` |
| Scheduler | `shadow/agent/scheduler.py` |
| Templates | `shadow/agent/templates/` (Jinja2) |
| Prompts | `shadow/prompts/SOUL.md`, `IDENTITY.md` |
| Gateway | `shadow/gateway/src/index-multi.js` |
| Migrations | `supabase/migrations/0*.sql` |

## Tool Groups

### Task Tools (5)
`create_task`, `list_tasks`, `update_task`, `complete_task`, `delete_task`

### Appointment Tools (4)
`create_appointment`, `list_appointments`, `update_appointment`, `delete_appointment`

### Contact Tools (10)
`get_contact`, `list_contacts`, `create_contact`, `update_contact`, `delete_contact`, `restore_contact`, `merge_contacts`, `find_duplicates`, `search_contact_history`, `get_contact_tasks`

### Memory Tools (3)
`recall_memory`, `store_memory`, `forget_memory`

### Category Tools (2)
`list_categories`, `create_category`

### Settings Tools (2)
`get_settings`, `update_settings`

### Alert Tools (4)
`create_alert`, `list_alerts`, `delete_alert`, `preview_summary`

### Reminder Tools (1)
`create_reminder`

### Suggestion Tools (2)
`list_suggestions`, `manage_monitored_groups`

### CRM Oculto Tools (2)
`conversation_summary`, `contact_history`

### System Tools (3)
`spawn_task`, `list_available_tools`, `load_tool`

## Environment Variables (LangGraph)

```bash
# Core
SHADOW_USE_LANGGRAPH=true          # Enable LangGraph (default: false)

# Z-API
ZAPI_INSTANCE_ID=                  # Z-API instance ID
ZAPI_TOKEN=                        # Z-API token

# LLM Providers
ANTHROPIC_API_KEY=                 # Claude (supervisor + workers)
GEMINI_API_KEY=                    # Gemini (media + fallback)
OPENAI_API_KEY=                    # Embeddings (text-embedding-3-small)

# LangSmith (optional)
LANGCHAIN_TRACING_V2=false         # Enable tracing
LANGCHAIN_PROJECT=shadow-prod      # Project name
LANGCHAIN_API_KEY=                 # LangSmith API key
LANGSMITH_SAMPLE_RATE=0.1          # Trace 10% of requests
```

## Debugging Comum

### LangGraph não está ativado
Verificar `SHADOW_USE_LANGGRAPH=true` no `.env`. Default é `false` (usa ReActAgent legado).

### Worker retornou erro
Verificar logs: `[worker_name] Worker error: ...`. Workers têm retry 3x com fallback para Gemini.

### SSE não conecta no dashboard
Verificar se admin-api está rodando e endpoint `/agents/stream` está acessível. CORS deve incluir a origem do frontend.

### Storage retornou None inesperadamente
Verificar assinatura em `storage/`. Métodos `get_*` podem retornar `None`.

### Contato não encontrado
Checar priority chain do resolver:
1. Phone explícito? 2. reminder_target? 3. last_recipient? 4. Config? 5. Allowlist?

### Rate limit no Anthropic
Workers fazem fallback automático para Gemini após 3 tentativas com backoff exponencial.

### Checkpoint corruption
Usar DB separado (`data/shadow_graph.db`). Per-thread lock previne invocações concorrentes no mesmo thread.

## Dependências

### Python (shadow/agent/requirements.txt)
```
# Core
fastapi, uvicorn, httpx, pydantic, cryptography, dateparser, croniter

# LLM
anthropic, litellm, google-generativeai

# LangGraph
langgraph, langchain-core, langchain-community, langgraph-checkpoint-sqlite

# Knowledge
lancedb, openai (embeddings)

# Documents
jinja2, fpdf2, plotly, kaleido
```

### Frontend (apps/admin/package.json)
```
react, react-router-dom, @tanstack/react-query, recharts, lucide-react, tailwindcss
```

## Módulos Deprecated (NÃO USAR)
- `orchestrator.py` — Substituído por `graph/supervisor.py`
- `nlu.py` — Claude infere intents via LLM routing
- `message_handler.py` — Disponível como fallback, mas `graph/` é o padrão com flag on
