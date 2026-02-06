# Shadow A.I. - Arquitetura e Planejamento

## Visão Geral

Shadow A.I. é um agente de IA que atua como secretária virtual no WhatsApp, com um CRM invisível por trás. Captura conversas e reuniões, extrai entidades (contatos, tarefas, compromissos) e auxilia o usuário com automações.

---

## Decisões de Produto (Validadas com Usuário)

| Aspecto | Decisão |
|---------|---------|
| WhatsApp | Suporta pessoal (via encaminhamento) e Business (via webhook) |
| Captura | Híbrida: encaminhamento manual + webhook Business API |
| Interface | 100% WhatsApp (sem dashboard web) |
| Entidades | Criação contextual (alta confiança = auto, baixa = pergunta) |
| Número Shadow | Próprio (contato separado do vendedor) |
| MVP | Só CRM conversacional (sem reuniões, sem integração Roleplay) |

---

## Arquitetura MVP

```
┌────────────────────────────────────────────────────────────────┐
│                      CAMADA DE ENTRADA                         │
├────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐     ┌─────────────────────┐          │
│  │  Encaminhamento     │     │  Webhook Business   │          │
│  │  Manual             │     │  API                │          │
│  │  (qualquer usuário) │     │  (contas Business)  │          │
│  └──────────┬──────────┘     └──────────┬──────────┘          │
│             │                           │                      │
│             └───────────┬───────────────┘                      │
│                         ▼                                      │
│              ┌─────────────────────┐                          │
│              │  Message Ingestion  │                          │
│              │  Service            │                          │
│              └──────────┬──────────┘                          │
└─────────────────────────┼──────────────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────────────┐
│                         ▼                                      │
│              ┌─────────────────────┐                          │
│              │   Shadow Agent      │                          │
│              │   (Python)          │                          │
│              │                     │                          │
│              │  ┌───────────────┐  │                          │
│              │  │ NLP Extractor │  │  Claude API              │
│              │  │ (entidades)   │◄─┼──────────────────        │
│              │  └───────────────┘  │                          │
│              │                     │                          │
│              │  ┌───────────────┐  │                          │
│              │  │ Dialog Manager│  │  State Machine           │
│              │  │ (conversação) │  │                          │
│              │  └───────────────┘  │                          │
│              │                     │                          │
│              │  ┌───────────────┐  │                          │
│              │  │ Action Engine │  │  CRUD + Automações       │
│              │  │               │  │                          │
│              │  └───────────────┘  │                          │
│              └──────────┬──────────┘                          │
│                         │                                      │
│              CAMADA DE PROCESSAMENTO                           │
└─────────────────────────┼──────────────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────────────┐
│                         ▼                                      │
│              ┌─────────────────────┐                          │
│              │   Supabase          │                          │
│              │   (PostgreSQL)      │                          │
│              │                     │                          │
│              │  ┌───────────────┐  │                          │
│              │  │ contacts      │  │                          │
│              │  │ tasks         │  │                          │
│              │  │ appointments  │  │                          │
│              │  │ conversations │  │                          │
│              │  │ messages      │  │                          │
│              │  │ users         │  │                          │
│              │  └───────────────┘  │                          │
│              └──────────┬──────────┘                          │
│                         │                                      │
│              CAMADA DE PERSISTÊNCIA                            │
└─────────────────────────┼──────────────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────────────┐
│                         ▼                                      │
│              ┌─────────────────────┐                          │
│              │  WhatsApp Gateway   │                          │
│              │  (envio de msgs)    │                          │
│              │                     │                          │
│              │  - Baileys Gateway  │                          │
│              │    (porta 18790)    │                          │
│              └─────────────────────┘                          │
│                                                                │
│              CAMADA DE SAÍDA                                   │
└────────────────────────────────────────────────────────────────┘
```

---

## Componentes Detalhados

### 1. Message Ingestion Service

**Responsabilidade**: Receber mensagens de múltiplas fontes e normalizar.

**Fontes de entrada**:
- Webhook WhatsApp Business API
- Mensagens encaminhadas (detectadas por metadata)

**Output normalizado**:
```json
{
  "source": "whatsapp_business" | "forwarded",
  "user_id": "uuid",
  "original_sender": "5511999999999",
  "original_recipient": "5511888888888",
  "content": "texto da mensagem",
  "content_type": "text" | "audio" | "image",
  "timestamp": "ISO8601",
  "metadata": {}
}
```

**Tecnologia**: Edge Function (Deno) ou Python FastAPI

---

### 2. Shadow Agent (Core)

**Responsabilidade**: Processar mensagens, extrair entidades, manter diálogo.

**Subcomponentes**:

#### 2.1 NLP Extractor
- Usa Claude API para extração estruturada
- Identifica: contatos, tarefas, compromissos, contexto
- Retorna JSON com entidades e nível de confiança

**Prompt exemplo**:
```
Analise a mensagem abaixo e extraia entidades:

Mensagem: "João da empresa X disse que quer fechar o contrato amanhã às 14h"

Retorne JSON:
{
  "contacts": [{"name": "João", "company": "X", "confidence": 0.95}],
  "appointments": [{"description": "fechar contrato", "datetime": "amanhã 14h", "with": "João", "confidence": 0.9}],
  "tasks": [],
  "context": "negociação em fase de fechamento"
}
```

#### 2.2 Dialog Manager
- State machine para conversação
- Estados: idle, awaiting_confirmation, collecting_info, executing_action
- Histórico de contexto (últimas N mensagens)

#### 2.3 Action Engine
- CRUD de entidades no Supabase
- Criação de lembretes (scheduler)
- Consultas ao CRM

#### 2.4 Audio Transcriber (NOVO)
- Transcreve áudios do WhatsApp para texto
- Usa Groq Whisper (grátis, muito rápido)
- Fallback: OpenAI Whisper API

```python
async def transcribe_audio(audio_bytes: bytes) -> str:
    try:
        # Groq Whisper - grátis, ~1s para 30s de áudio
        result = await groq.audio.transcriptions.create(
            file=audio_bytes,
            model="whisper-large-v3",
            language="pt"
        )
        return result.text
    except RateLimitError:
        # Fallback OpenAI - $0.006/min
        result = await openai.audio.transcriptions.create(
            file=audio_bytes,
            model="whisper-1"
        )
        return result.text
```

**Tecnologia**: Python 3.11+ (consistente com agent existente)

---

### 3. WhatsApp Gateway (ATUALIZADO)

**Responsabilidade**: Enviar e receber mensagens WhatsApp.

**Estratégia dual-ambiente**:

#### Desenvolvimento: Evolution API
```
┌─────────────────────────────────────────┐
│           Evolution API                 │
│  (Docker self-hosted)                   │
├─────────────────────────────────────────┤
│  - Dashboard web de gestão              │
│  - Multi-device support                 │
│  - Webhooks configuráveis               │
│  - API REST completa                    │
│  - Suporta grupos, status, mídia        │
│  - Open-source brasileiro               │
└─────────────────────────────────────────┘
```

**Setup Evolution**:
```bash
docker run -d \
  --name evolution-api \
  -p 8080:8080 \
  -e AUTHENTICATION_API_KEY=seu-token \
  atendai/evolution-api
```

**Webhook config**:
```json
{
  "url": "https://seu-supabase.functions.supabase.co/shadow-webhook",
  "events": ["messages.upsert", "messages.update"]
}
```

#### Produção: WhatsApp Business API (via 360dialog)

```
┌─────────────────────────────────────────┐
│        360dialog (BSP Oficial)          │
├─────────────────────────────────────────┤
│  - API oficial Meta                     │
│  - Pricing: €0.0 setup + €49/mês        │
│  - Webhook nativo                       │
│  - Templates aprovados                  │
│  - 100% compliance                      │
└─────────────────────────────────────────┘
```

**Abstração unificada**:
```python
class WhatsAppGateway:
    def __init__(self, provider: str):
        if provider == "evolution":
            self.client = EvolutionClient(...)
        elif provider == "360dialog":
            self.client = Dialog360Client(...)

    async def send_message(self, to: str, text: str):
        return await self.client.send(to, text)

    async def setup_webhook(self, url: str):
        return await self.client.configure_webhook(url)
```

**Riscos do Evolution API**:
- Não-oficial, pode parar de funcionar
- WhatsApp pode banir número
- Usar apenas com números descartáveis em dev

---

### 4. Scheduler (Lembretes e Automações)

**Responsabilidade**: Executar ações agendadas.

**Exemplos**:
- "Lembrar de ligar para João amanhã às 9h"
- "Se cliente não responder em 3 dias, notificar"

**Tecnologia**:
- MVP: pg_cron (Supabase) + Edge Function
- Escala: Temporal.io ou Bull (Redis)

---

## Schema do Banco de Dados (Supabase)

```sql
-- Usuários do Shadow
CREATE TABLE shadow_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_number TEXT UNIQUE NOT NULL,
  name TEXT,
  whatsapp_type TEXT CHECK (whatsapp_type IN ('personal', 'business')),
  business_api_config JSONB, -- credentials se for Business API
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contatos extraídos
CREATE TABLE shadow_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  phone_number TEXT,
  name TEXT NOT NULL,
  company TEXT,
  role TEXT,
  notes TEXT,
  tags TEXT[],
  last_interaction_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, phone_number)
);

-- Tarefas
CREATE TABLE shadow_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  due_date TIMESTAMPTZ,
  status TEXT CHECK (status IN ('pending', 'done', 'cancelled')) DEFAULT 'pending',
  priority TEXT CHECK (priority IN ('low', 'medium', 'high')) DEFAULT 'medium',
  source_message_id UUID, -- mensagem que originou a tarefa
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Compromissos/Agenda
CREATE TABLE shadow_appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  duration_minutes INT DEFAULT 60,
  location TEXT,
  status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled')) DEFAULT 'scheduled',
  reminder_sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Histórico de conversas (com clientes)
CREATE TABLE shadow_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  summary TEXT, -- resumo gerado por AI
  sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'negative')),
  topics TEXT[]
);

-- Mensagens individuais
CREATE TABLE shadow_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES shadow_conversations(id),
  direction TEXT CHECK (direction IN ('inbound', 'outbound')) NOT NULL,
  content TEXT NOT NULL,
  content_type TEXT CHECK (content_type IN ('text', 'audio', 'image', 'document')) DEFAULT 'text',
  audio_transcription TEXT, -- se for áudio
  extracted_entities JSONB, -- entidades extraídas desta mensagem
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Interações usuário <-> Shadow
CREATE TABLE shadow_interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  user_message TEXT NOT NULL,
  shadow_response TEXT NOT NULL,
  intent TEXT, -- comando identificado
  entities_created JSONB, -- IDs das entidades criadas
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Lembretes agendados
CREATE TABLE shadow_reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  task_id UUID REFERENCES shadow_tasks(id),
  appointment_id UUID REFERENCES shadow_appointments(id),
  remind_at TIMESTAMPTZ NOT NULL,
  message TEXT NOT NULL,
  sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_contacts_user ON shadow_contacts(user_id);
CREATE INDEX idx_tasks_user_status ON shadow_tasks(user_id, status);
CREATE INDEX idx_appointments_user_date ON shadow_appointments(user_id, scheduled_at);
CREATE INDEX idx_messages_conversation ON shadow_messages(conversation_id);
CREATE INDEX idx_reminders_pending ON shadow_reminders(remind_at) WHERE sent = FALSE;
```

---

## Fluxos Principais

### Fluxo 1: Encaminhamento Manual

```
1. Vendedor recebe mensagem do cliente João
2. Vendedor encaminha para número do Shadow
3. Shadow detecta encaminhamento (metadata)
4. NLP Extractor analisa conteúdo
5. Extrai: contato "João", possível compromisso
6. Confiança > 0.8 → cria automaticamente
7. Shadow responde: "Registrei o contato João e agendei follow-up para amanhã."
```

### Fluxo 2: Webhook Business API

```
1. Mensagem chega no WhatsApp Business do vendedor
2. Webhook dispara para nosso endpoint
3. Message Ingestion normaliza
4. Shadow Agent processa em background
5. Se detectar algo importante, notifica usuário
6. Shadow: "Vi que cliente Maria perguntou sobre preço. Quer que eu prepare uma proposta?"
```

### Fluxo 3: Consulta ao CRM

```
Usuário: "Quem é o João?"
Shadow: "João Silva, da Empresa X. Último contato: ontem.
         Contexto: negociando Plano Premium, pediu 10% de desconto.
         Próximo passo: call amanhã às 14h."
```

### Fluxo 4: Criação de Tarefa

```
Usuário: "Me lembra de ligar pro João amanhã às 9h"
Shadow: "Pronto! Vou te lembrar amanhã às 9h de ligar para João Silva."

[No dia seguinte, 9h]
Shadow: "Lembrete: Ligar para João Silva (Empresa X) agora.
         Contexto: negociação de Plano Premium."
```

---

## Integrações Externas

| Serviço | Propósito | Fase |
|---------|-----------|------|
| **WhatsApp Business API** | Webhook + envio oficial | MVP |
| **Baileys/wwebjs** | Fallback contas pessoais | MVP (temporário) |
| **Claude API** | Extração de entidades, diálogo | MVP |
| **Supabase** | Banco + Auth + Edge Functions | MVP |
| **Google Calendar API** | Sincronização de agenda | Fase 2 |
| **Recall.ai** | Gravação de reuniões | Fase 2 |
| **Live Roleplay** | Sugestão de treinos | Fase 2 |

---

## Considerações de Privacidade e Compliance

### LGPD

1. **Consentimento**: Usuário aceita termos ao ativar Shadow
2. **Terceiros**: Clientes devem ser informados que conversas podem ser processadas
3. **Direito ao esquecimento**: Implementar endpoint de exclusão
4. **Armazenamento**: Dados no Brasil (Supabase região São Paulo)

### WhatsApp TOS

- **Business API**: 100% compliance
- **Baileys/wwebjs**: Viola TOS. Usar apenas para MVP controlado com poucos usuários

### Áudio

- Transcrição processada, áudio descartado após processamento
- Ou: opt-in explícito para armazenamento

---

## Stack Técnica Final (MVP) - ATUALIZADO

| Componente | Tecnologia | Notas |
|------------|------------|-------|
| **Agent Core** | Python 3.11+ (Monolito) | Simples, fácil debug |
| **WhatsApp Dev** | Evolution API | Open-source, fácil setup |
| **WhatsApp Prod** | WhatsApp Business API (360dialog) | Compliance, estável |
| **LLM Primary** | Claude Sonnet | ReAct agent com tool calling |
| **LLM Vision/Audio** | Gemini Pro | Transcrição, OCR, análise de mídia |
| **LLM Fallback** | Gemini Flash | Casos simples, custo menor |
| **Transcrição** | Groq Whisper | Grátis (beta), muito rápido |
| **Database** | Supabase (PostgreSQL) | Já no projeto |
| **Scheduler** | pg_cron + Edge Functions | MVP simples |
| **Hosting Agent** | Railway / Fly.io | Always-on worker |
| **Hosting Functions** | Supabase Edge Functions | Webhooks |

### Estimativa de Custos (1000 usuários, 50 msgs/dia)

| Item | Custo Mensal |
|------|--------------|
| Groq LLM (Llama 8B + 70B) | ~$15 |
| Groq Whisper | $0 (beta) |
| Claude fallback (~5% chamadas) | ~$25 |
| Supabase (Pro) | $25 |
| Railway (Agent) | ~$20 |
| Evolution API (self-hosted) | $0 |
| **Total MVP** | **~$85/mês** |

---

## Estrutura de Pastas

```
live_roleplay/
├── frontend/          # (existente) React app roleplay
├── agent/             # (existente) Python agent roleplay
├── supabase/          # (existente) Edge Functions
│
└── shadow/            # Shadow A.I.
    ├── agent/
    │   ├── main.py              # Entry point
    │   ├── message_handler.py   # Processa mensagens recebidas
    │   ├── nlp_extractor.py     # Extração de entidades via Claude
    │   ├── dialog_manager.py    # State machine de conversação
    │   ├── action_engine.py     # CRUD e automações
    │   ├── whatsapp_gateway.py  # Envio de mensagens
    │   └── scheduler.py         # Lembretes
    │
    ├── supabase/
    │   └── functions/
    │       ├── shadow-webhook/     # Recebe mensagens WhatsApp
    │       └── shadow-reminder/    # Dispara lembretes
    │
    ├── migrations/
    │   └── 001_shadow_schema.sql
    │
    └── docs/
        └── ARCHITECTURE.md         # Este arquivo
```

---

## Roadmap de Fases

### MVP (Fase 1) - CRM Conversacional
- [ ] Setup WhatsApp Business API (ou Baileys para teste)
- [ ] Webhook de recebimento de mensagens
- [ ] NLP Extractor com Claude
- [ ] Dialog Manager básico (perguntar/confirmar)
- [ ] CRUD de contatos, tarefas, compromissos
- [ ] Consultas simples ("quem é X?", "o que tenho hoje?")
- [ ] Lembretes básicos

### Fase 2 - Reuniões
- [ ] Integração Recall.ai (ou bot próprio)
- [ ] Transcrição de calls
- [ ] Extração de ata e action items
- [ ] Vinculação com contatos existentes

### Fase 3 - Integração Live Roleplay
- [ ] Análise de padrões de conversação
- [ ] Identificação de fraquezas (objeções não tratadas, etc)
- [ ] Sugestão de cenários de treino
- [ ] Feedback loop pós-treino

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| WhatsApp bloqueia conta não-oficial | Alta | Alto | Migrar para Business API o mais rápido possível |
| Claude API rate limits | Média | Médio | Cache de extrações similares, batch processing |
| Extração incorreta de entidades | Média | Médio | Sempre confirmar quando confiança < 0.8 |
| LGPD - reclamação de terceiro | Baixa | Alto | Termos claros, opt-out fácil |

---

## Próximos Passos

1. **Definir conta WhatsApp Business** para testes
2. **Setup do Supabase** com schema do Shadow
3. **Prototipar NLP Extractor** com prompts Claude
4. **Implementar fluxo encaminhamento manual** (mais simples)
5. **Testar com 5-10 usuários controlados**
6. **Iterar baseado em feedback**

---

## Alternativas Arquiteturais Exploradas

### WhatsApp Gateway

| Opção | Status | Motivo |
|-------|--------|--------|
| **Baileys direto** | Escolhido | Open-source, controle total, multi-user ready |
| Evolution API | Descartado | Dependência externa desnecessária |
| WhatsApp Business API | Futuro (SaaS) | Para versão comercial com compliance |
| Twilio | Descartado | Custos altos demais para MVP |

### LLM Strategy

| Opção | Status | Motivo |
|-------|--------|--------|
| **Claude + Gemini** | Escolhido | Claude ReAct + Gemini para mídia |
| Groq + Llama | Descartado | Limitações em português e tool calling |
| GPT-4o | Descartado | Sem vantagem sobre Claude para este caso |
| Self-hosted | Futuro | Se volume > 100k msgs/dia |

### Arquitetura Geral

| Opção | Status | Motivo |
|-------|--------|--------|
| **Monolito Python** | Escolhido | Simples, fácil de começar |
| Microserviços | Descartado | Over-engineering para MVP |
| Serverless puro | Descartado | Cold starts ruins para chat |
| No-code (n8n) | Descartado | Difícil customizar diálogo |

### Arquitetura LLM Multi-Tier

```
┌─────────────────────────────────────────────────────────────┐
│                    SHADOW AGENT (Python)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐                                       │
│  │   Router LLM    │                                       │
│  │  (Llama 8B)     │                                       │
│  │  ~10ms latency  │                                       │
│  └────────┬────────┘                                       │
│           │                                                 │
│           ├──────────────┬──────────────┬─────────────┐    │
│           ▼              ▼              ▼             ▼    │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────┐ ┌─────────┐│
│  │   Simple    │ │  Extractor  │ │  Dialog   │ │Fallback ││
│  │  Response   │ │  (Llama70B) │ │ (Llama70B)│ │(Claude) ││
│  │  (template) │ │  ~200ms     │ │  ~200ms   │ │ ~500ms  ││
│  └─────────────┘ └─────────────┘ └───────────┘ └─────────┘│
│                                                             │
│  Providers: Groq (primary) → Together AI (secondary)        │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Roteamento Inteligente

```python
async def route_message(message: str, context: dict) -> str:
    # 1. Llama 8B classifica intenção (~10ms, ~$0.00001)
    intent = await groq.llama_8b.classify(message)

    match intent:
        case "greeting" | "thanks" | "bye":
            # Template, sem LLM
            return templates[intent]

        case "query_simple":
            # Ex: "o que tenho hoje?" - Llama 8B basta
            return await groq.llama_8b.respond(context, message)

        case "extract_entities":
            # Precisa modelo maior
            return await groq.llama_70b.extract(message)

        case "complex_dialog":
            # Conversa elaborada
            response = await groq.llama_70b.chat(context, message)

            # Validação de qualidade
            if confidence_score(response) < 0.7:
                # Fallback para Claude
                return await claude.sonnet.chat(context, message)

            return response
```

### Comparativo de Provedores LLM

| Provider | Modelos | Latência p50 | Custo (1M in/out) | Fallback Order |
|----------|---------|--------------|-------------------|----------------|
| **Groq** | Llama 8B/70B | ~100ms | $0.05/$0.08 | Primary |
| **Together** | Llama, Mixtral | ~300ms | $0.20/$0.20 | Secondary |
| **Fireworks** | Llama, Mistral | ~250ms | $0.20/$0.20 | Tertiary |
| **Claude** | Sonnet | ~500ms | $3.00/$15.00 | Quality fallback |

---

## Desafios do LLM Open-Source e Mitigações

### 1. Qualidade em Português Brasileiro

| Problema | Mitigação |
|----------|-----------|
| Llama treinado majoritariamente em inglês | Prompts em PT-BR com exemplos claros |
| Gírias e expressões brasileiras | Few-shot examples com vocabulário local |
| Formatação de datas BR (dd/mm/yyyy) | Regex + normalização pré-processamento |
| Nomes brasileiros (José, João, Maria) | Lista de nomes comuns no prompt |

**Exemplo de prompt otimizado para PT-BR**:
```python
EXTRACTION_PROMPT = """
Você é um assistente brasileiro especializado em extrair informações de conversas de vendas.

REGRAS:
- Datas no formato brasileiro: "amanhã", "segunda-feira", "dia 15"
- Horários: "às 14h", "depois do almoço" = 14:00
- Valores: "5 mil", "R$ 5.000,00"
- Telefones: (11) 99999-9999 ou 11999999999

EXEMPLOS:
Entrada: "O João da Empresa X quer fechar amanhã às 14h"
Saída: {"contacts": [{"name": "João", "company": "Empresa X"}], "appointments": [{"datetime": "amanhã 14:00", "description": "fechar negócio"}]}

Entrada: "Me liga depois, tô em reunião"
Saída: {"contacts": [], "appointments": [], "context": "cliente ocupado, reagendar"}

Agora analise:
{message}
"""
```

### 2. Structured Output (JSON)

Llama não tem "tool calling" nativo como Claude/GPT. Mitigações:

```python
# Opção A: Regex extraction
import re
import json

def extract_json(response: str) -> dict:
    # Tenta encontrar JSON na resposta
    match = re.search(r'\{[\s\S]*\}', response)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None

# Opção B: Outlines (constrained generation)
from outlines import models, generate

model = models.transformers("meta-llama/Llama-3.1-70B")
generator = generate.json(model, ContactSchema)
result = generator(prompt)  # Sempre retorna JSON válido

# Opção C: Instructor (wrapper para structured output)
import instructor
from groq import Groq

client = instructor.from_groq(Groq())
contact = client.chat.completions.create(
    model="llama-3.1-70b-versatile",
    response_model=Contact,  # Pydantic model
    messages=[{"role": "user", "content": message}]
)
```

### 3. Rate Limits do Groq

| Tier | Requests/min | Tokens/min | Tokens/dia |
|------|--------------|------------|------------|
| Free | 30 | 14,400 | 14,400 |
| Paid | 100 | 100,000 | Ilimitado |

**Estratégia de fallback**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def llm_call_with_fallback(prompt: str) -> str:
    providers = [
        ("groq", groq_client),
        ("together", together_client),
        ("fireworks", fireworks_client),
    ]

    for name, client in providers:
        try:
            return await client.complete(prompt)
        except RateLimitError:
            logger.warning(f"{name} rate limited, trying next...")
            continue

    # Último recurso: Claude (mais caro mas sempre funciona)
    return await claude_client.complete(prompt)
```

### 4. Alucinações e Validação

```python
async def validate_extraction(message: str, extracted: dict) -> dict:
    # Validação básica de entidades
    issues = []

    # Contato mencionado deve existir na mensagem
    for contact in extracted.get("contacts", []):
        if contact["name"].lower() not in message.lower():
            issues.append(f"Nome '{contact['name']}' não encontrado na mensagem")

    # Data deve fazer sentido
    for apt in extracted.get("appointments", []):
        if "datetime" in apt:
            try:
                parsed = parse_brazilian_datetime(apt["datetime"])
                if parsed < datetime.now():
                    issues.append(f"Data no passado: {apt['datetime']}")
            except:
                issues.append(f"Data inválida: {apt['datetime']}")

    if issues:
        # Re-tentar com Claude para casos problemáticos
        logger.warning(f"Validation issues: {issues}")
        return await claude_extract(message)

    return extracted
```

---

## Considerações de Escala Futura

### Self-Hosting LLM (quando fazer sentido)

| Métrica | API (Groq) | Self-Hosted |
|---------|------------|-------------|
| Volume break-even | < 100k msgs/dia | > 100k msgs/dia |
| Setup | Minutos | Semanas |
| GPU necessária | N/A | A100 80GB (~$2/hora) |
| Latência controlável | Não | Sim |
| Privacidade total | Não | Sim |

**Opções de self-hosting**:
- **vLLM**: Inference server otimizado, suporta batching
- **Text Generation Inference (TGI)**: Da Hugging Face, production-ready
- **Ollama**: Simples mas menos features
- **LocalAI**: API compatível com OpenAI

### Infraestrutura para escala

```
┌─────────────────────────────────────────────────────────────┐
│                    ESCALA (Fase 3+)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │  Load Balancer  │────►│  Agent Pool     │               │
│  │  (Cloudflare)   │     │  (K8s/Railway)  │               │
│  └─────────────────┘     └─────────────────┘               │
│                                 │                           │
│                          ┌──────┴──────┐                   │
│                          ▼             ▼                   │
│                   ┌───────────┐ ┌───────────┐              │
│                   │  Redis    │ │  Postgres │              │
│                   │  (cache)  │ │  (data)   │              │
│                   └───────────┘ └───────────┘              │
│                                                             │
│  ┌─────────────────┐                                       │
│  │  Self-hosted    │  Para volume > 100k msgs/dia          │
│  │  vLLM cluster   │  GPU: 4x A100 80GB                    │
│  │  (Llama 70B)    │  Custo: ~$6k/mês                      │
│  └─────────────────┘                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Verificação

Para validar que o MVP está funcionando:

1. Encaminhar mensagem para o Shadow → deve extrair entidades corretamente
2. Perguntar "quem é X?" → deve retornar dados do contato
3. Pedir "me lembra de Y amanhã às 9h" → deve criar lembrete
4. Receber lembrete no horário agendado
5. Listar tarefas pendentes → deve mostrar lista correta

---

## Sistema de Memória de Longo Prazo

### Hierarquia de Memória

```
┌─────────────────────────────────────────────────────────────┐
│  Working Memory  │  Últimas 5-10 mensagens (sempre no prompt) │
├──────────────────┼───────────────────────────────────────────┤
│  Short-term      │  Resumo da sessão atual                    │
├──────────────────┼───────────────────────────────────────────┤
│  Long-term       │  Fatos persistentes sobre contatos (DB)    │
├──────────────────┼───────────────────────────────────────────┤
│  Semantic        │  Embeddings + busca vetorial (pgvector)    │
└──────────────────┴───────────────────────────────────────────┘
```

### Tabelas de Memória (Supabase)

```sql
-- Memórias estruturadas por contato
CREATE TABLE shadow_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  memory_type TEXT CHECK (memory_type IN (
    'fact',           -- "João é gerente de TI"
    'preference',     -- "Prefere reuniões de manhã"
    'negotiation',    -- "Pediu 10% de desconto"
    'context'         -- "Está avaliando concorrentes"
  )),
  content TEXT NOT NULL,
  confidence FLOAT DEFAULT 1.0,
  source_message_id UUID,
  extracted_at TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT TRUE
);

-- Embeddings para busca semântica
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE shadow_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  source_type TEXT CHECK (source_type IN ('message', 'memory', 'summary')),
  source_id UUID NOT NULL,
  embedding vector(1536),  -- OpenAI text-embedding-3-small
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON shadow_embeddings
  USING ivfflat (embedding vector_cosine_ops);

-- Resumos compactados de conversas antigas
CREATE TABLE shadow_conversation_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES shadow_conversations(id),
  summary TEXT NOT NULL,
  key_facts JSONB,
  messages_from TIMESTAMPTZ,
  messages_to TIMESTAMPTZ,
  message_count INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Pipeline de Memória

```python
class MemoryManager:
    async def process_message(self, message: Message):
        # 1. Working memory (últimas 10 msgs)
        self.working_memory.append(message)

        # 2. Extrair fatos persistentes
        memories = await self.extract_memories(message)

        # 3. Gerar embedding para busca futura
        embedding = await openai.embeddings.create(
            model="text-embedding-3-small",
            input=message.content
        )
        await self.store_embedding(message.id, embedding)

        # 4. Atualizar resumo da sessão (a cada 5 msgs)
        if len(self.working_memory) % 5 == 0:
            await self.update_session_summary()

    async def get_relevant_context(self, query: str) -> str:
        """Monta contexto para responder uma query."""
        context = []

        # Working memory (sempre)
        context.append("Conversa recente:\n" + format(self.working_memory))

        # Busca semântica no histórico
        similar = await self.vector_search(query, limit=5)
        if similar:
            context.append("Histórico relevante:\n" + format(similar))

        # Memórias estruturadas do contato
        contact = extract_contact_name(query)
        if contact:
            memories = await self.get_contact_memories(contact)
            context.append(f"Sobre {contact}:\n" + format(memories))

        return "\n\n".join(context)
```

### Compactação de Histórico

Conversas > 30 dias são compactadas em resumos para economizar storage:

```python
async def compact_old_conversations():
    old = await get_conversations_older_than(days=30)
    for conv in old:
        summary = await llm.summarize(conv.messages)
        key_facts = await llm.extract_facts(conv.messages)
        await save_summary(conv.id, summary, key_facts)
        # Opcional: deletar mensagens originais
```

### Custo do Sistema de Memória

| Item | Volume (1000 users) | Custo/mês |
|------|---------------------|-----------|
| Embeddings (OpenAI 3-small) | 1.5M msgs | ~$3 |
| Storage pgvector | ~500MB | Incluído Supabase Pro |
| Compactação LLM | 50k resumos | ~$5 |
| **Total** | | **~$8/mês** |

---

## Suporte a Grupos WhatsApp

### Tipos de Grupos

| Tipo | Comportamento | Exemplo |
|------|---------------|---------|
| **client** | Monitorar, extrair entidades | "Projeto X - Empresa Y" |
| **internal** | Ignorar completamente | "Time de Vendas" |
| **support** | Monitorar tickets | "Suporte - Cliente Z" |
| **unknown** | Perguntar ao usuário | Novo grupo |

### Schema de Grupos

```sql
CREATE TABLE shadow_group_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  group_jid TEXT NOT NULL,
  group_name TEXT,
  group_type TEXT CHECK (group_type IN ('client', 'internal', 'support', 'unknown')),
  should_monitor BOOLEAN DEFAULT FALSE,
  participants JSONB,  -- [{"phone": "...", "role": "client|colleague"}]
  primary_contact_id UUID REFERENCES shadow_contacts(id),
  UNIQUE(user_id, group_jid)
);
```

### Fluxo de Classificação

```
Mensagem de grupo → Grupo conhecido?
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
             SIM                   NÃO
              │                     │
              ▼                     ▼
         Usar config          LLM classifica
         salva                nome + mensagens
              │                     │
              │              ┌──────┴──────┐
              │              ▼             ▼
              │           cliente       interno
              │              │             │
              │              ▼             ▼
              │         Perguntar       Ignorar
              │         confirmação   silenciosamente
              │              │
              └──────┬───────┘
                     ▼
              Processar ou Ignorar
```

### Filtragem de Mensagens

Em grupos, a maioria das mensagens é ruído. Filtrar agressivamente:

```python
async def filter_group_message(msg, group):
    # Próprio usuário = ignorar
    if msg.sender == group.user_phone:
        return False

    # Colegas internos = ignorar (exceto @menções)
    if msg.sender_role == "colleague":
        return f"@{group.user_name}" in msg.content

    # Stickers, reações = ignorar
    if msg.content_type in ["sticker", "reaction"]:
        return False

    # Mensagens curtas demais = provavelmente irrelevante
    if len(msg.content) < 10:
        return False

    # Cliente = verificar se é acionável (Llama 8B)
    return await quick_relevance_check(msg.content)
```

### Configuração via WhatsApp

```
Usuário: "grupos"

Shadow: "Seus grupos:
1. Projeto ABC - Empresa X - Monitorando
2. Time de Vendas - Ignorado
3. Suporte Cliente Y - 3 tickets

Responda com número para configurar."

Usuário: "1"

Shadow: "Projeto ABC - Empresa X
Participantes:
- João (cliente)
- Maria (você)
- Pedro (colega)

1 - Alterar participante
2 - Pausar monitoramento
3 - Ver histórico"
```

### Riscos de Grupos

| Risco | Mitigação |
|-------|-----------|
| Monitorar grupo errado | Sempre confirmar antes de ativar |
| Custo alto de LLM | Llama 8B para filtragem, 70B só extração |
| Privacidade de colegas | Não armazenar msgs de "internos" |

---

## Integrações Externas

### Prioridades

| Integração | Prioridade | Valor |
|------------|------------|-------|
| **Google Calendar** | Alta | Criar eventos, verificar disponibilidade |
| **Pipedrive** | Alta | Sincronizar pipeline de vendas |
| **Notion** | Média | Base de conhecimento de clientes |
| **HubSpot** | Baixa | Alternativa ao Pipedrive |

### Tabela de Integrações

```sql
CREATE TABLE shadow_integrations (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES shadow_users(id),
  provider TEXT NOT NULL,  -- 'google_calendar', 'pipedrive', 'notion'
  access_token TEXT,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  config JSONB,
  is_active BOOLEAN DEFAULT TRUE,
  last_sync_at TIMESTAMPTZ,
  UNIQUE(user_id, provider)
);

-- Mapeamento Shadow <-> Sistema externo
CREATE TABLE shadow_entity_mappings (
  id UUID PRIMARY KEY,
  integration_id UUID REFERENCES shadow_integrations(id),
  local_type TEXT,   -- 'contact', 'appointment'
  local_id UUID,
  external_type TEXT, -- 'person', 'event', 'deal'
  external_id TEXT,
  UNIQUE(integration_id, local_type, local_id)
);
```

### Fluxo de Conexão (via WhatsApp)

```
Usuário: "conectar google"

Shadow: "Para conectar Google Calendar:
         1. Acesse: shadow.app/connect/google
         2. Faça login e autorize
         3. Pronto! Confirmarei aqui."

[Usuário autoriza no browser]

Shadow: "Google Calendar conectado!
         Agora posso criar eventos e ver sua agenda."
```

### Exemplos de Uso

**Google Calendar**:
```
Usuário: "Agenda reunião com João amanhã 14h"
Shadow: "Criei no Google Calendar:
         Reunião com João Silva
         Amanhã, 14h-15h
         meet.google.com/abc-xyz"
```

**Pipedrive**:
```
Shadow detecta: "João quer fechar por R$ 50k"
         ↓
[Atualiza deal no Pipedrive automaticamente]
         ↓
Shadow: "Atualizei o deal do João: R$ 50k, fase Proposta"
```

**Notion**:
```
Usuário: "Cria página do projeto X"
Shadow: "Criei no Notion:
         Projeto X - Empresa Y
         → Contatos, histórico, próximos passos
         notion.so/projeto-x-abc"
```

### Sync Automático

```python
# Job que roda a cada 15 minutos
async def background_sync_job():
    for user in users_with_integrations:
        # Shadow → Google Calendar (novos eventos)
        await sync_appointments_to_calendar(user)

        # Pipedrive → Shadow (deals atualizados)
        await sync_pipedrive_to_contacts(user)

        # Shadow → Notion (novas notas)
        await sync_notes_to_notion(user)
```

### Custo de Integrações

| API | Custo |
|-----|-------|
| Google Calendar | Grátis |
| Pipedrive | Grátis (com plano pago) |
| Notion | Grátis |
| HubSpot | Grátis (básico) |
| **Infra adicional** | ~$5/mês |

---

## Respostas por Voz (TTS)

### Valor

Shadow pode responder com áudio, não só texto:
- Mais pessoal e natural
- Melhor para respostas longas
- Diferencial vs assistentes texto-only

### Provedores TTS

| Provider | Qualidade | Latência | Custo/1M chars |
|----------|-----------|----------|----------------|
| **OpenAI TTS** | Muito boa | ~300ms | $15 |
| **Google Cloud** | Boa | ~200ms | $4 |
| **ElevenLabs** | Excelente | ~500ms | $5 (chars) |
| **Coqui (open)** | Média | ~1s | Grátis |

**Recomendação**: Google Cloud TTS (custo) ou ElevenLabs (qualidade).

### Preferências do Usuário

```sql
ALTER TABLE shadow_users ADD COLUMN voice_preference TEXT
  CHECK (voice_preference IN (
    'text_only',    -- Sempre texto
    'audio_only',   -- Sempre áudio
    'audio_long',   -- Áudio para respostas longas (default)
    'mirror'        -- Responde no mesmo formato que recebeu
  )) DEFAULT 'audio_long';
```

### Fluxo de Decisão

```
Gerar resposta texto
        │
        ▼
┌─────────────────┐
│ voice_preference│
└────────┬────────┘
         │
    ┌────┴────┬─────────┬──────────┐
    ▼         ▼         ▼          ▼
text_only  audio_only  mirror   audio_long
    │         │         │          │
    ▼         ▼         ▼          ▼
  Texto    Gerar     Usuário    Resposta
           áudio     mandou     > 200 chars?
                     áudio?         │
                        │      ┌────┴────┐
                   ┌────┴────┐ ▼         ▼
                   ▼         ▼ SIM      NÃO
                  SIM       NÃO │        │
                   │         │  ▼        ▼
                   ▼         ▼ Áudio   Texto
                 Áudio     Texto
```

### Implementação

```python
from openai import AsyncOpenAI

class VoiceResponder:
    async def text_to_audio(self, text: str) -> bytes:
        # Adaptar texto para fala natural
        speech_text = self.adapt_for_speech(text)

        response = await self.client.audio.speech.create(
            model="tts-1",
            voice="nova",  # alloy, echo, fable, onyx, nova, shimmer
            input=speech_text,
            response_format="mp3"
        )
        return response.content

    def adapt_for_speech(self, text: str) -> str:
        # Remover markdown
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        # Remover emojis
        text = re.sub(r'[📅🕐📍✅❌]', '', text)
        # Expandir abreviações
        text = text.replace("R$", "reais")
        return text
```

### Voz Customizada (Premium)

Usuários premium podem clonar a própria voz via ElevenLabs:

```
Usuário: "clonar minha voz"

Shadow: "Envie 3-5 áudios seus (30s cada).
         Recurso premium - R$ 29/mês"

[Usuário envia áudios]

Shadow: "Voz clonada! Agora uso sua voz nas respostas."
```

### Custo TTS

| Cenário (1000 users, 10 áudios/dia) | Custo/mês |
|-------------------------------------|-----------|
| Google Cloud TTS | ~$24 |
| OpenAI TTS-1 | ~$90 |
| ElevenLabs | ~$30 |

---

## Multi-Tenancy

### Estratégia

| Fase | Abordagem | Isolamento |
|------|-----------|------------|
| MVP | Single DB + tenant_id | Baixo (RLS) |
| Crescimento | Schema por tenant | Médio |
| Enterprise | Database/instância separada | Total |

### Schema de Organizações

```sql
CREATE TABLE shadow_organizations (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,  -- "empresa-x"
  plan TEXT CHECK (plan IN ('free', 'starter', 'professional', 'enterprise')),
  max_users INT DEFAULT 5,
  billing_email TEXT,
  stripe_customer_id TEXT,
  settings JSONB DEFAULT '{}',
  sharing_settings JSONB DEFAULT '{
    "contacts": "shared",
    "appointments": "team",
    "memories": "shared"
  }'
);

-- Usuários pertencem a uma org
ALTER TABLE shadow_users
  ADD COLUMN organization_id UUID REFERENCES shadow_organizations(id),
  ADD COLUMN role_in_org TEXT CHECK (role_in_org IN ('owner', 'admin', 'member'));

-- Todas as tabelas de dados ganham organization_id
ALTER TABLE shadow_contacts ADD COLUMN organization_id UUID;
ALTER TABLE shadow_tasks ADD COLUMN organization_id UUID;
-- ... repetir para todas
```

### Row Level Security

```sql
ALTER TABLE shadow_contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see only org data"
  ON shadow_contacts FOR ALL
  USING (
    organization_id = (
      SELECT organization_id FROM shadow_users
      WHERE phone_number = current_setting('app.current_user_phone')
    )
  );
```

### Hierarquia de Roles

```
OWNER (1 por org)
└── Billing, gerenciar admins, excluir org

ADMIN (N por org)
└── Adicionar/remover members, ver dados de todos

MEMBER (N por org)
└── Ver/editar apenas próprios dados
```

### Convite de Membros

```
Admin: "adicionar usuario 11999998888"

Shadow: "Convite enviado!"

[No WhatsApp do convidado]
Shadow: "Você foi convidado para Empresa X. Aceitar?"
```

### Planos e Limites

| Plano | Usuários | Msgs/mês | Preço |
|-------|----------|----------|-------|
| Free | 1 | 500 | R$ 0 |
| Starter | 5 | 5.000 | R$ 49/mês |
| Professional | 20 | 50.000 | R$ 149/mês |
| Enterprise | Ilimitado | Ilimitado | Sob consulta |

### Métricas por Org

```
Admin: "metricas"

Shadow: "Empresa X:
12/20 usuários
487 contatos
8.432/50.000 mensagens

Top performers:
1. Maria - 89 tarefas
2. João - 67 tarefas"
```

---

## Onboarding de Usuários

### Fluxo Completo (100% WhatsApp)

```
1. Primeira mensagem
   Shadow: "Sou o Shadow, seu assistente de vendas.
            Vamos configurar em 2 min?"

2. Tipo de conta
   Shadow: "Empresa ou autônomo?"
   → Se empresa: "Qual nome da empresa?"

3. Nome do usuário
   Shadow: "Como devo te chamar?"

4. Preferência de voz
   Shadow: "Como prefere que eu responda?
            1 Texto | 2 Áudio longo | 3 Sempre áudio"

5. Integrações (opcional)
   Shadow: "Conectar Google Calendar ou Pipedrive?"

6. Tutorial prático
   Shadow: "Configurado! Encaminhe uma mensagem de cliente."

7. Primeira extração
   Shadow: "Identifiquei João da Empresa Y! Salvei contato."
```

### State Machine

```python
class OnboardingState(Enum):
    NOT_STARTED = "not_started"
    WAITING_CONFIRM = "waiting_confirm"
    WAITING_TYPE = "waiting_type"
    WAITING_COMPANY = "waiting_company"
    WAITING_NAME = "waiting_name"
    WAITING_VOICE = "waiting_voice"
    WAITING_INTEGRATIONS = "waiting_integrations"
    WAITING_FIRST_MESSAGE = "waiting_first_message"
    COMPLETED = "completed"
```

### Tabela de Sessão

```sql
CREATE TABLE shadow_onboarding_sessions (
  id UUID PRIMARY KEY,
  phone_number TEXT UNIQUE NOT NULL,
  state TEXT NOT NULL DEFAULT 'not_started',
  data JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);
```

### Onboarding de Membro (Convite)

Fluxo reduzido para membros convidados:

```
Shadow: "Você foi convidado para Empresa X. Aceitar?"
Usuário: "aceitar"
Shadow: "Como te chamar?"
Usuário: "Pedro"
Shadow: "Bem-vindo, Pedro! Encaminhe uma mensagem para começar."
```

### Ajuda Contextual Pós-Onboarding

```python
CONTEXTUAL_HELP = {
    "first_contact": "Primeiro contato salvo! Diga 'quem é X' para detalhes.",
    "first_task": "Primeira tarefa! Diga 'tarefas' para ver todas.",
    "idle_3_days": "Faz 3 dias! Você tem 5 tarefas pendentes."
}
```

### Métricas de Funil

```sql
CREATE VIEW shadow_onboarding_funnel AS
SELECT
  DATE(started_at) as date,
  COUNT(*) as started,
  COUNT(*) FILTER (WHERE state = 'completed') as completed,
  ROUND(100.0 * completed / started, 1) as conversion_rate
FROM shadow_onboarding_sessions
GROUP BY DATE(started_at);
```

---

## Analytics e Métricas

### Métricas por Persona

| Persona | Métricas | Canal |
|---------|----------|-------|
| **Usuário** | Tarefas, contatos, follow-ups | WhatsApp |
| **Admin Org** | Ranking do time, alertas | WhatsApp + Dashboard |
| **Owner** | Uso vs limite, billing | WhatsApp + Dashboard |
| **Plataforma** | MAU, retenção, custos | Dashboard interno |

### Resumo do Usuário (via WhatsApp)

```
Usuário: "métricas"

Shadow: "Sua semana:
23 tarefas concluídas
12 novos contatos
15 reuniões
15% acima da sua média!"
```

### Métricas do Admin

```
Admin: "métricas time"

Shadow: "Equipe Empresa X:
Ranking:
1. Maria - 45 tarefas
2. João - 38 tarefas

Alertas:
- Pedro: 12 tarefas atrasadas
- Lucas: inativo há 5 dias"
```

### Schema de Eventos

```sql
-- Eventos granulares
CREATE TABLE shadow_events (
  id UUID PRIMARY KEY,
  organization_id UUID,
  user_id UUID,
  event_type TEXT NOT NULL,  -- 'message_received', 'task_completed', etc
  event_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agregações diárias (performance)
CREATE TABLE shadow_daily_stats (
  organization_id UUID,
  user_id UUID,
  date DATE,
  messages_received INT,
  tasks_completed INT,
  contacts_created INT,
  UNIQUE(organization_id, user_id, date)
);
```

### Tipos de Eventos

```python
class EventType:
    MESSAGE_RECEIVED = "message_received"
    CONTACT_CREATED = "contact_created"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    APPOINTMENT_CREATED = "appointment_created"
    LLM_CALL = "llm_call"  # para custos
    USER_ACTIVE = "user_active"
```

### Relatórios Semanais Automáticos

```python
async def send_weekly_report(user_id: str):
    stats = await get_user_weekly_stats(user_id)

    message = f"""Seu relatório semanal:
    Tarefas: {stats.tasks_completed}
    Contatos: {stats.contacts_created}
    Streak: {stats.active_days} dias ativos"""

    await send_whatsapp_message(user_id, message)
```

### Alertas Inteligentes

```python
ALERT_RULES = [
    {"name": "tasks_overdue", "condition": "tasks_overdue > 5"},
    {"name": "inactive_user", "condition": "last_active > 3 days"},
    {"name": "approaching_limit", "condition": "usage > 80%"},
]
```

### Dashboard Web (Opcional)

Para análises complexas que não cabem no WhatsApp:

```
shadow.app/dashboard
├── Gráficos de atividade (Recharts)
├── Ranking de usuários
├── Tarefas atrasadas
└── Status de integrações
```

---

## Áreas Exploradas - Resumo Final

| Área | Status |
|------|--------|
| Arquitetura MVP | Completo |
| LLM Open-Source (Groq/Llama) | Completo |
| WhatsApp Gateway (Evolution + Business API) | Completo |
| Schema de Banco Completo | Completo |
| Memória de Longo Prazo | Completo |
| Grupos WhatsApp | Completo |
| Integrações Externas | Completo |
| Respostas por Voz | Completo |
| Multi-Tenancy | Completo |
| Onboarding | Completo |
| Analytics | Completo |

**Todas as áreas foram exploradas!**
