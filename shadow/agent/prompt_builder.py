"""
Prompt Builder - Dynamic system prompt assembly.

Builds the system prompt by combining:
1. SOUL.md - Personality and values
2. IDENTITY.md - Capabilities and tools
3. USER_TEMPLATE.md - Dynamic user preferences and learned patterns

Inspired by OpenClaw's prompt architecture.
"""

import os
from pathlib import Path
from typing import Any

# Default paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class PromptBuilder:
    """Builds dynamic system prompts for the Shadow agent."""

    def __init__(self, prompts_dir: Path | str | None = None):
        self.prompts_dir = Path(prompts_dir) if prompts_dir else PROMPTS_DIR
        self._cache: dict[str, str] = {}

    def _load_file(self, filename: str) -> str:
        """Load a prompt file, with caching."""
        if filename in self._cache:
            return self._cache[filename]

        filepath = self.prompts_dir / filename
        if not filepath.exists():
            print(f"[prompt_builder] Warning: {filename} not found at {filepath}")
            return ""

        content = filepath.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def get_soul(self) -> str:
        """Get the SOUL.md content (personality)."""
        return self._load_file("SOUL.md")

    def get_identity(self) -> str:
        """Get the IDENTITY.md content (capabilities)."""
        return self._load_file("IDENTITY.md")

    def get_user_template(self) -> str:
        """Get the USER_TEMPLATE.md content."""
        return self._load_file("USER_TEMPLATE.md")

    def build_user_section(
        self,
        settings: dict[str, Any],
        learned_patterns: dict[str, Any] | None = None,
        recent_corrections: list[dict] | None = None,
        important_memories: list[str] | None = None,
    ) -> str:
        """
        Build the user-specific section of the prompt.

        Args:
            settings: User settings from storage.get_user_settings()
            learned_patterns: Patterns learned from user behavior
            recent_corrections: Recent corrections the user made
            important_memories: Important facts to remember

        Returns:
            Formatted user section string
        """
        # Extract settings with defaults
        timezone = settings.get("timezone", "America/Sao_Paulo")
        language = settings.get("language", "pt-BR")
        use_emojis = "Sim" if settings.get("use_emojis", True) else "Não"
        verbose = "Sim" if settings.get("verbose_responses", False) else "Não"

        always_ask = "Sim" if settings.get("always_ask_incomplete", True) else "Não"
        auto_create = "Sim" if settings.get("auto_create_from_conversations", False) else "Não"
        group_monitoring = "Sim" if settings.get("group_monitoring_enabled", False) else "Não"
        reminder_minutes = settings.get("default_reminder_minutes", 30)

        morning_enabled = "Sim" if settings.get("morning_summary_enabled", False) else "Não"
        morning_time = settings.get("morning_summary_time", "07:00")

        # Format learned patterns
        learned = learned_patterns or {}
        time_prefs = learned.get("time_preferences", "Nenhum padrão identificado ainda")
        top_cats = learned.get("top_categories", "Nenhuma categoria frequente")
        freq_contacts = learned.get("frequent_contacts", "Nenhum contato frequente")
        comm_style = learned.get("communication_style", "Padrão")

        # Format corrections
        corrections_text = "Nenhuma correção recente"
        if recent_corrections:
            corrections_list = []
            for c in recent_corrections[:5]:  # Limit to 5 most recent
                trigger = c.get("trigger_text", "")
                action = c.get("learned_action", "")
                if trigger and action:
                    corrections_list.append(f"- Quando disse \"{trigger}\" → {action}")
            if corrections_list:
                corrections_text = "\n".join(corrections_list)

        # Format memories
        memories_text = "Nenhuma memória importante registrada"
        if important_memories:
            memories_list = [f"- {m}" for m in important_memories[:10]]
            if memories_list:
                memories_text = "\n".join(memories_list)

        # Build the section
        return f"""## Configurações Ativas

- **Fuso horário**: {timezone}
- **Idioma**: {language}
- **Usar emojis**: {use_emojis}
- **Respostas detalhadas**: {verbose}

## Comportamento Configurado

- **Perguntar quando incompleto**: {always_ask}
- **Criar de conversas automaticamente**: {auto_create}
- **Monitorar grupos**: {group_monitoring}
- **Antecedência padrão de lembretes**: {reminder_minutes} minutos

## Alertas

- **Resumo matinal**: {morning_enabled}
- **Horário do resumo**: {morning_time}

## Padrões Aprendidos

### Preferências de Horário
{time_prefs}

### Categorias Mais Usadas
{top_cats}

### Contatos Frequentes
{freq_contacts}

### Estilo de Comunicação
{comm_style}

## Correções Recentes

{corrections_text}

## Memórias Importantes

{memories_text}"""

    def build_context_section(
        self,
        contact_context: dict[str, Any] | None = None,
        recent_memories: list[str] | None = None,
        pending_tasks: list[dict] | None = None,
    ) -> str:
        """
        Build the current context section of the prompt.

        Args:
            contact_context: Current contact's context/summary
            recent_memories: Recently retrieved memories
            pending_tasks: Pending tasks for context

        Returns:
            Formatted context section string
        """
        lines = []

        # Contact context
        if contact_context:
            name = contact_context.get("name", "Desconhecido")
            phone = contact_context.get("phone", "")
            summary = contact_context.get("summary", "")
            relationship = contact_context.get("relationship_type", "")

            lines.append("### Contato Atual")
            lines.append(f"- Nome: {name}")
            if phone:
                lines.append(f"- Telefone: {phone}")
            if relationship:
                lines.append(f"- Relação: {relationship}")
            if summary:
                lines.append(f"- Resumo: {summary}")
            lines.append("")

        # Recent memories
        if recent_memories:
            lines.append("### Memórias Relevantes")
            for mem in recent_memories[:5]:
                lines.append(f"- {mem}")
            lines.append("")

        # Pending tasks
        if pending_tasks:
            lines.append(f"### Tarefas Pendentes ({len(pending_tasks)})")
            for task in pending_tasks[:5]:
                title = task.get("title", "Sem título")
                due = task.get("due_at", "")
                due_str = f" (vence: {due[:10]})" if due else ""
                lines.append(f"- {title}{due_str}")
            lines.append("")

        if not lines:
            return "Sem contexto adicional disponível."

        return "\n".join(lines)

    def build_system_prompt(
        self,
        settings: dict[str, Any] | None = None,
        contact_context: dict[str, Any] | None = None,
        recent_memories: list[str] | None = None,
        pending_tasks: list[dict] | None = None,
        learned_patterns: dict[str, Any] | None = None,
        recent_corrections: list[dict] | None = None,
        important_memories: list[str] | None = None,
        include_soul: bool = True,
        include_identity: bool = True,
    ) -> str:
        """
        Build the complete system prompt.

        Args:
            settings: User settings
            contact_context: Current contact context
            recent_memories: Retrieved memories
            pending_tasks: Pending tasks
            learned_patterns: Learned user patterns
            recent_corrections: Recent corrections
            important_memories: Important memories to include
            include_soul: Whether to include SOUL.md
            include_identity: Whether to include IDENTITY.md

        Returns:
            Complete system prompt string
        """
        sections = ["Você é o Shadow, um assistente pessoal inteligente via WhatsApp.\n"]

        # SOUL section
        if include_soul:
            soul = self.get_soul()
            if soul:
                sections.append("═" * 79)
                sections.append("                              PERSONALIDADE")
                sections.append("═" * 79)
                sections.append(soul)
                sections.append("")

        # IDENTITY section
        if include_identity:
            identity = self.get_identity()
            if identity:
                sections.append("═" * 79)
                sections.append("                          CAPACIDADES E FERRAMENTAS")
                sections.append("═" * 79)
                sections.append(identity)
                sections.append("")

        # USER section (dynamic)
        if settings:
            sections.append("═" * 79)
            sections.append("                          PREFERÊNCIAS DO USUÁRIO")
            sections.append("═" * 79)
            user_section = self.build_user_section(
                settings=settings,
                learned_patterns=learned_patterns,
                recent_corrections=recent_corrections,
                important_memories=important_memories,
            )
            sections.append(user_section)
            sections.append("")

        # CONTEXT section (dynamic)
        if contact_context or recent_memories or pending_tasks:
            sections.append("═" * 79)
            sections.append("                              CONTEXTO ATUAL")
            sections.append("═" * 79)
            context_section = self.build_context_section(
                contact_context=contact_context,
                recent_memories=recent_memories,
                pending_tasks=pending_tasks,
            )
            sections.append(context_section)
            sections.append("")

        # RULES section (always included)
        sections.append("═" * 79)
        sections.append("                          REGRAS DE EXECUÇÃO")
        sections.append("═" * 79)
        sections.append("""
1. SEPARAR PARÂMETROS: "tarefa comprar leite amanhã" →
   title="comprar leite", due_date="amanhã"

2. CONFIRMAR AÇÕES DESTRUTIVAS: delete_*, merge_* requerem confirm=True

3. RESOLVER CONTATOS: Se ambíguo, listar opções e perguntar

4. PASSO A PASSO: Tarefas complexas = divida em steps

5. PERGUNTAR QUANDO INCOMPLETO: Se falta info essencial, PERGUNTE

6. NUNCA INVENTAR: Telefones, emails, datas - se não sei, pergunto

7. MENSAGENS CURTAS: WhatsApp não é email, seja conciso
""")

        return "\n".join(sections)

    def clear_cache(self) -> None:
        """Clear the file cache."""
        self._cache.clear()


# Singleton instance
_builder: PromptBuilder | None = None


def get_prompt_builder() -> PromptBuilder:
    """Get or create the prompt builder singleton."""
    global _builder
    if _builder is None:
        _builder = PromptBuilder()
    return _builder


def build_system_prompt(**kwargs) -> str:
    """Convenience function to build system prompt."""
    return get_prompt_builder().build_system_prompt(**kwargs)
