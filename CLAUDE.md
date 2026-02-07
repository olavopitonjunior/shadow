# Shadow MVP - Contexto Claude Code

## Quick Reference
- **Projeto**: Assistente WhatsApp + CRM invisível
- **Fase**: MVP (Phase 7 Suggestions) com 33 tools
- **Backend**: Supabase PostgreSQL (opcional) + SQLite (local)
- **LLM**: Claude (ReAct Agent), Gemini (mídia/transcrição)
- **Gateway**: Baileys direto (porta 18790)

## Padrões Críticos

### Tool System (33 tools em shadow/agent/tools/)
- Base: `Tool` → `execute(context: ToolContext) -> ToolResult`
- Registry: `ToolRegistry.execute(tool_name, params)`
- Grupos: Task(5), Appointment(4), Reminder(1), Contact(10), Memory(3), Category(2), Settings(2), Alert(4), Suggestion(2)

### Storage Layer (⚠️ CRÍTICO)
**Arquivo**: `shadow/agent/storage.py`
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

### Gateway Pattern (Baileys)
- **Local**: `shadow/gateway/src/`
- **Entry**: `index.js` (single-user), `index-multi.js` (multi-user)
- **Manager**: `manager.js` (multi-session support)
- **Porta**: 18790 (configurable via SHADOW_GATEWAY_PORT)

## Arquivos-Chave

| Componente | Arquivo |
|------------|---------|
| Entry Point | `shadow/agent/message_handler.py` |
| Storage | `shadow/agent/storage.py` |
| Tools | `shadow/agent/tools/` |
| Sessions | `shadow/agent/sessions.py` |
| Contact Resolver | `shadow/agent/contact_resolver.py` |
| Learning | `shadow/agent/learning.py` |
| Suggestions | `shadow/agent/suggestions/` |
| Prompts | `shadow/prompts/SOUL.md`, `IDENTITY.md` |
| Gateway | `shadow/gateway/src/index.js` |
| Migrations | `supabase/migrations/0*.sql` (27 total) |

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

## Migrations Recentes
- 020: Enhanced contacts (aliases, memories, relationship_type)
- 021: Contact management (soft delete, merge history, duplicate detection)
- 022: Categories (task_categories, appointment_types)
- 023: User Settings (shadow_user_settings)
- 024: Scheduled Alerts (shadow_scheduled_alerts, alert_history)
- 025: Learning System (feedback, patterns, preferences)
- 026: Multi-tenancy incremental (user_id columns, helper functions)
- 027: Proactive Suggestions (shadow_suggestions, daily counts)

## Debugging Comum

### Storage retornou None inesperadamente
Verificar assinatura em `storage.py`. Métodos `get_*` podem retornar `None`.

### Contato não encontrado
Checar priority chain do resolver:
1. Phone explícito? 2. reminder_target? 3. last_recipient? 4. Config? 5. Allowlist?

### Mensagem enviada para pessoa errada
Verificar `resolveTarget()` no adapter e `last_recipient` na sessão.

### Phone validation falhou
Usar `validate_phone_number()` de `security.py` - remove chars especiais, valida DDD.

## Dependências Especiais
- `lancedb>=0.4.0` - Vector DB para memória semântica
- `openai>=1.0.0` - Embeddings para busca semântica

## Módulos Deprecated (NÃO USAR)
- `orchestrator.py` - Claude faz seleção nativa de tools
- `nlu.py` - Claude infere intents no ReAct loop
