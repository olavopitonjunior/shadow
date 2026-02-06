# Shadow A.I.

Secretaria virtual de vendas via WhatsApp com CRM conversacional invisivel.

## Status

Fase: MVP em construcao (gateway + agent + banco local).

## Documentacao

- docs/ARCHITECTURE.md - arquitetura completa
- docs/ONBOARDING.md - passo a passo para rodar localmente
- docs/CONFIG.md - configuracoes e variaveis
- docs/RUNBOOK.md - operacao e troubleshooting

## Estrutura do projeto

```
shadow/
|-- agent/          # Python agent (API + armazenamento local)
|-- gateway/        # Node gateway (Baileys)
|-- migrations/     # SQL migrations (Supabase)
|-- docs/
|-- README.md
```

## Stack tecnica

- Agent Core: Python 3.11+
- WhatsApp (dev): Baileys (WhatsApp Web)
- WhatsApp (prod): Business API (360dialog)
- LLM: Groq + Claude fallback
- Database: Supabase PostgreSQL (MVP usa SQLite local)

## Decisoes de produto

- Interface 100% WhatsApp (sem dashboard)
- Criacao contextual de entidades
- Modo invisivel por padrao (nao responde clientes)
- Responde em grupo somente com gatilho (@shadow, /shadow)

## Roadmap resumido

- MVP: captura, tarefas, compromissos, lembretes, consultas
- Fase 2: reunioes (transcricao)
- Fase 3: roleplay e coaching