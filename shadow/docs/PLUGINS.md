# Shadow MVP Plugin System

O Shadow MVP suporta plugins tanto no Gateway (JavaScript) quanto no Agent (Python), permitindo extensibilidade sem modificar o código principal.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                     Shadow MVP                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐      ┌─────────────────────┐       │
│  │   Gateway (JS)      │      │   Agent (Python)    │       │
│  │   + Plugin Hooks    │ ───> │   + Plugin Hooks    │       │
│  └─────────┬───────────┘      └─────────┬───────────┘       │
│            │                            │                    │
│  ┌─────────▼───────────┐      ┌─────────▼───────────┐       │
│  │  Gateway Plugins    │      │  Agent Plugins      │       │
│  │  (JavaScript)       │      │  (Python)           │       │
│  └─────────────────────┘      └─────────────────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Gateway Plugins (JavaScript)

### Hooks Disponíveis

| Hook | Tipo | Descrição |
|------|------|-----------|
| `gateway_start` | void | Executado quando o gateway inicia |
| `gateway_stop` | void | Executado quando o gateway para |
| `message_received` | void | Executado quando uma mensagem é recebida |
| `message_sending` | modifying | Executado antes de enviar uma mensagem (pode modificar/cancelar) |
| `message_sent` | void | Executado após uma mensagem ser enviada |

### Estrutura de Plugin

```
shadow/gateway/plugins/meu-plugin/
├── package.json
└── index.js
```

### package.json

```json
{
  "name": "shadow-plugin-meu-plugin",
  "version": "1.0.0",
  "main": "index.js",
  "type": "module",
  "shadow": {
    "id": "meu-plugin"
  }
}
```

### index.js

```javascript
export default {
  id: "meu-plugin",
  name: "Meu Plugin",
  version: "1.0.0",

  register(api) {
    const logger = api.logger;

    // Registrar hook de mensagem recebida
    api.on("message_received", async (event, ctx) => {
      logger.info({ from: event.senderE164 }, "Mensagem recebida");
    });

    // Registrar hook de envio (pode modificar)
    api.on("message_sending", async (event, ctx) => {
      // Para modificar o conteúdo:
      // return { content: "novo conteúdo" };

      // Para cancelar o envio:
      // return { cancel: true };

      // Para não modificar:
      return undefined;
    });

    logger.info("Plugin registrado");
  },
};
```

### API do Plugin (Gateway)

```javascript
api.id          // ID do plugin
api.name        // Nome do plugin
api.config      // Configuração do gateway
api.pluginConfig // Configuração específica do plugin
api.logger      // Logger (pino)
api.on(hookName, handler, { priority })  // Registrar hook
api.resolvePath(path)  // Resolver caminho relativo
```

---

## Agent Plugins (Python)

### Hooks Disponíveis

| Hook | Tipo | Descrição |
|------|------|-----------|
| `before_handle` | modifying | Executado antes de processar mensagem (pode interceptar) |
| `after_handle` | void | Executado após processar mensagem |
| `tool_call` | modifying | Executado antes de chamar uma tool |
| `storage_write` | void | Executado após operação de storage |

### Estrutura de Plugin

```
shadow/agent/plugins/installed/meu-plugin/
├── __init__.py
└── index.py
```

### index.py

```python
from plugins.types import PluginDefinition, AgentHookName


def register(api):
    logger = api.logger

    # Hook: antes de processar
    async def before_handle(payload):
        logger.info(f"Processando: {payload.get('body', '')[:50]}")
        # Retornar None para continuar
        # Retornar dict para resposta antecipada
        return None

    # Hook: após processar
    async def after_handle(payload, result):
        logger.info(f"Intent: {result.get('intent')}")

    api.on(AgentHookName.BEFORE_HANDLE, before_handle)
    api.on(AgentHookName.AFTER_HANDLE, after_handle)

    # Registrar tool customizada
    async def minha_tool(params):
        return {"resultado": "sucesso"}

    api.register_tool("minha_tool", minha_tool)

    # Registrar handler de intent
    async def handle_greeting(payload, storage):
        return {"reply": "Olá!", "intent": "greeting"}

    api.register_handler("greeting", handle_greeting)

    logger.info("Plugin registrado")


plugin = PluginDefinition(
    id="meu-plugin",
    name="Meu Plugin",
    version="1.0.0",
    register=register,
)
```

### API do Plugin (Agent)

```python
api.id           # ID do plugin
api.name         # Nome do plugin
api.config       # Configuração do agent
api.plugin_config # Configuração específica do plugin
api.logger       # Logger (logging.Logger)
api.on(hook_name, handler, priority=0)  # Registrar hook
api.register_tool(name, handler, schema)  # Registrar tool
api.register_handler(intent, handler)  # Registrar handler de intent
api.resolve_path(path)  # Resolver caminho relativo
```

---

## Configuração

### shadow.plugins.json (Gateway)

```json
{
  "plugins": {
    "enabled": ["message-logger"],
    "disabled": ["experimental"],
    "config": {
      "message-logger": {
        "logLevel": "debug"
      }
    }
  }
}
```

### shadow.plugins.json (Agent)

```json
{
  "plugins": {
    "enabled": ["analytics"],
    "disabled": [],
    "config": {
      "analytics": {
        "trackIntents": true
      }
    }
  }
}
```

---

## Exemplos Incluídos

### Gateway: message-logger

Plugin que registra todas as mensagens recebidas e enviadas.

**Localização:** `shadow/gateway/plugins/message-logger/`

**Hooks usados:**
- `gateway_start`
- `gateway_stop`
- `message_received`
- `message_sending`
- `message_sent`

### Agent: analytics

Plugin que coleta estatísticas sobre processamento de mensagens.

**Localização:** `shadow/agent/plugins/installed/analytics/`

**Hooks usados:**
- `before_handle`
- `after_handle`

**Tools registradas:**
- `analytics_stats` - Retorna estatísticas atuais

---

## Habilitando Plugins

1. Coloque o plugin no diretório apropriado:
   - Gateway: `shadow/gateway/plugins/`
   - Agent: `shadow/agent/plugins/installed/`

2. Adicione ao arquivo de configuração:
   ```json
   {
     "plugins": {
       "enabled": ["nome-do-plugin"]
     }
   }
   ```

3. Reinicie o gateway/agent.

---

## Prioridades

Hooks podem ter prioridades. Maior prioridade = executa primeiro.

```javascript
// JavaScript
api.on("message_received", handler, { priority: 10 });
```

```python
# Python
api.on(AgentHookName.BEFORE_HANDLE, handler, priority=10)
```

---

## Hooks Modificadores vs Void

- **Void hooks**: Executam em paralelo, não retornam valor
- **Modifying hooks**: Executam sequencialmente, podem modificar/cancelar

### message_sending (modificador)

```javascript
api.on("message_sending", async (event, ctx) => {
  // Modificar conteúdo
  return { content: event.content.toUpperCase() };

  // Ou cancelar
  return { cancel: true };
});
```

### before_handle (modificador)

```python
async def before_handle(payload):
    # Resposta antecipada
    return {"reply": "Resposta do plugin", "intent": "plugin_response"}

    # Ou continuar normal
    return None
```
