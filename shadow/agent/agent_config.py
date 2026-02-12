"""
Agent Configuration - Settings for the ReAct Agent.

Provides centralized configuration and system prompts for the Claude-based agent.
"""

import os
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for the ReAct Agent."""

    # Provider settings
    provider: str = "auto"  # "anthropic", "openai", "gemini", "deepseek", "auto"

    # Model settings
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.1

    # ReAct loop settings
    max_iterations: int = 5

    # Fast-path patterns (commands that bypass LLM)
    fast_path_patterns: tuple[str, ...] = (
        "ping", "/ping",
        "ajuda", "/help", "help",
        "tarefas", "mostrar tarefas", "listar tarefas",
        "compromissos", "agenda",
        "resumo", "resumo do dia",
        "contexto", "/contexto",
    )

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        return cls(
            provider=os.getenv("SHADOW_LLM_PROVIDER", "auto"),
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_iterations=int(os.getenv("SHADOW_MAX_ITERATIONS", "5")),
            max_tokens=int(os.getenv("SHADOW_MAX_TOKENS", "1024")),
        )


# System prompt for the Shadow agent
SYSTEM_PROMPT = """Você é o Shadow, um assistente pessoal inteligente via WhatsApp.

CAPACIDADES CORE (ferramentas já carregadas):
- Tarefas: create_task, list_tasks, complete_task
- Compromissos: create_appointment, list_appointments
- Lembretes: create_reminder
- Contatos: get_contact, list_contacts
- Memória: recall_memory, store_memory
- Configurações: get_settings

FERRAMENTAS ADICIONAIS:
Para editar, excluir, gerenciar categorias, alertas, contatos avançados,
CRM ou configurações, use:
1. list_available_tools() → ver ferramentas adicionais por categoria
2. load_tool("nome") → ativar a ferramenta necessária

Categorias disponíveis: tarefas, compromissos, contatos_avancado,
memoria, categorias, configuracoes, alertas, sugestoes, crm.

REGRAS:
1. Execute PASSO A PASSO usando as ferramentas
2. Confirme ações executadas com mensagem clara
3. Se uma ferramenta falhar, tente abordagem alternativa
4. Responda SEMPRE em português brasileiro
5. Seja conciso e direto - WhatsApp deve ser curto
6. Ao criar tarefas, SEPARE o título da data
7. NUNCA invente números de telefone - formato E.164: +5511999999999
8. Sobre contatos: NUNCA diga "não encontrei" sem tentar get_contact() primeiro

COMPORTAMENTO:
- Saudações/conversa casual → Responda SEM ferramentas
- Pedidos de ação → Use ferramentas (carregue se necessário)
- Mensagens curtas, sem markdown complexo (WhatsApp)
"""

# Error recovery prompt (used when a tool fails)
ERROR_RECOVERY_PROMPT = """A ferramenta {tool_name} falhou.

Erro: {error}
Tentativa: {attempt}/{max_attempts}

═══════════════════════════════════════════════════════════════════════════════
                           ESTRATÉGIAS POR TIPO DE ERRO
═══════════════════════════════════════════════════════════════════════════════

## Erros de Validação (parâmetros inválidos)

Se o erro menciona "inválido", "formato", "obrigatório":
1. Verificar formato de data (ISO ou texto natural como "amanhã")
2. Verificar formato de telefone (E.164: +5511999999999)
3. Se task_id/contact_id não existe: usar list_* para listar opções
4. Se falta parâmetro obrigatório: perguntar ao usuário

Exemplo de recuperação:
- "id não encontrado" → list_tasks() para mostrar IDs válidos
- "telefone inválido" → perguntar formato correto ao usuário

## Erros de Contato (não encontrado)

Se o erro menciona "contato não encontrado" ou "nenhum contato":
1. Tentar busca por alias: get_contact(identifier=nome_parcial)
2. Listar contatos similares: list_contacts() e filtrar
3. Perguntar: "Não encontrei [nome]. Você quis dizer [similar]?"
4. Se não encontrar: sugerir criar o contato

## Erros de Permissão (confirm=False)

Se o erro menciona "confirmação necessária" ou "confirm":
1. SEMPRE mostrar preview do que será feito
2. Pedir confirmação explícita ao usuário
3. Nunca assumir confirmação automaticamente
4. Exemplo: "Confirma a exclusão da tarefa 'X'?"

## Erros de Conflito (duplicata)

Se o erro menciona "duplicado" ou "já existe":
1. Mostrar item existente ao usuário
2. Perguntar se quer atualizar ou criar novo
3. Sugerir merge se forem contatos duplicados

## Erros de Rede/Timeout

Se o erro menciona "timeout", "conexão", "rede":
1. Primeira falha: tentar novamente imediatamente
2. Segunda falha: aguardar e tentar uma vez mais
3. Terceira falha: informar usuário e sugerir tentar depois
4. Nunca ficar em loop infinito de retries

## Erros de Limite (quota/rate limit)

Se o erro menciona "limite", "quota", "rate":
1. Não tentar novamente imediatamente
2. Informar usuário sobre a limitação temporária
3. Sugerir tentar novamente em alguns minutos

## Fallback Geral

Se nenhuma estratégia específica se aplica:
1. Tentar ferramenta alternativa se existir
2. Simplificar parâmetros (remover opcionais)
3. Informar usuário com mensagem clara:
   - O que tentou fazer
   - Por que falhou
   - O que pode ser feito diferente

═══════════════════════════════════════════════════════════════════════════════
                              REGRAS IMPORTANTES
═══════════════════════════════════════════════════════════════════════════════

- NUNCA inventar IDs, telefones ou outros dados
- Se não conseguir recuperar, PERGUNTE ao usuário
- Seja transparente sobre o que falhou
- Não repita a mesma ação que falhou sem mudar algo
- Após {max_attempts} tentativas, desistir e informar usuário
"""
