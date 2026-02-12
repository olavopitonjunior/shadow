"""
Meta-tools for Progressive Tool Loading.

Inspired by nanobot's progressive skill loading system.
Instead of loading all 35 tool schemas into every LLM call,
we load only core tools (Tier 1) and provide meta-tools to
discover and activate additional tools on demand.

This saves ~35-40% of system prompt tokens per call.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


# ═══════════════════════════════════════════════════════════════
#  Tool Tier Definitions
# ═══════════════════════════════════════════════════════════════

# Tier 1: Always loaded - core tools used in >80% of interactions
TIER_1_TOOLS = {
    "create_task",
    "list_tasks",
    "complete_task",
    "create_appointment",
    "list_appointments",
    "create_reminder",
    "get_contact",
    "list_contacts",
    "recall_memory",
    "store_memory",
    "get_settings",
    # Meta-tools (always available)
    "list_available_tools",
    "load_tool",
}

# Tier 2: On-demand - advanced/less frequent operations
TIER_2_TOOLS = {
    # Task management
    "update_task",
    "delete_task",
    # Appointment management
    "update_appointment",
    "delete_appointment",
    # Contact management
    "create_contact",
    "update_contact",
    "delete_contact",
    "restore_contact",
    "merge_contacts",
    "find_duplicates",
    "search_contact_history",
    "get_contact_tasks",
    # Memory
    "forget_memory",
    # Categories
    "list_categories",
    "create_category",
    # Settings
    "update_settings",
    # Alerts
    "create_alert",
    "list_alerts",
    "delete_alert",
    "preview_summary",
    # Suggestions
    "list_suggestions",
    "manage_monitored_groups",
    # CRM
    "conversation_summary",
    "contact_history",
    # Sistema
    "spawn_task",
}

# Category labels for display
TOOL_CATEGORIES = {
    "tarefas": ["update_task", "delete_task"],
    "compromissos": ["update_appointment", "delete_appointment"],
    "contatos_avancado": [
        "create_contact", "update_contact", "delete_contact",
        "restore_contact", "merge_contacts", "find_duplicates",
        "search_contact_history", "get_contact_tasks",
    ],
    "memoria": ["forget_memory"],
    "categorias": ["list_categories", "create_category"],
    "configuracoes": ["update_settings"],
    "alertas": ["create_alert", "list_alerts", "delete_alert", "preview_summary"],
    "sugestoes": ["list_suggestions", "manage_monitored_groups"],
    "crm": ["conversation_summary", "contact_history"],
    "sistema": ["spawn_task"],
}


def get_tier(tool_name: str) -> int:
    """Return the tier of a tool (1 or 2)."""
    if tool_name in TIER_1_TOOLS:
        return 1
    return 2


# ═══════════════════════════════════════════════════════════════
#  ListAvailableToolsTool
# ═══════════════════════════════════════════════════════════════

class ListAvailableToolsTool(Tool):
    """Lists additional tools available for on-demand loading."""

    name = "list_available_tools"
    description = (
        "Lista ferramentas adicionais disponiveis por categoria. "
        "Use quando precisar editar, excluir, gerenciar contatos avancados, "
        "categorias, alertas ou configuracoes."
    )
    category = "sistema"
    parameters = [
        ToolParameter(
            "category",
            "string",
            "Filtrar por categoria: tarefas, compromissos, contatos_avancado, "
            "memoria, categorias, configuracoes, alertas, sugestoes, crm. "
            "Omita para listar todas.",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        category_filter = params.get("category")

        # Get the full registry to look up descriptions
        from .registry import get_tool_registry
        registry = get_tool_registry()

        lines = []

        categories_to_show = TOOL_CATEGORIES
        if category_filter and category_filter in TOOL_CATEGORIES:
            categories_to_show = {category_filter: TOOL_CATEGORIES[category_filter]}

        for cat_name, tool_names in categories_to_show.items():
            cat_label = cat_name.upper().replace("_", " ")
            lines.append(f"\n{cat_label}:")
            for tool_name in tool_names:
                tool = registry.get(tool_name)
                if tool:
                    desc = tool.description[:80]
                    lines.append(f"  - {tool_name}: {desc}")

        if not lines:
            return ToolResult.ok("Nenhuma ferramenta adicional encontrada.")

        header = "Ferramentas adicionais disponiveis (use load_tool para ativar):"
        result_text = header + "\n" + "\n".join(lines)

        return ToolResult.ok(
            "Ferramentas listadas",
            display_text=result_text,
        )


# ═══════════════════════════════════════════════════════════════
#  LoadToolTool
# ═══════════════════════════════════════════════════════════════

class LoadToolTool(Tool):
    """Loads an additional tool by name, making it available for use."""

    name = "load_tool"
    description = (
        "Carrega uma ferramenta adicional pelo nome para uso. "
        "Use list_available_tools primeiro para ver as opcoes."
    )
    category = "sistema"
    parameters = [
        ToolParameter(
            "tool_name",
            "string",
            "Nome da ferramenta para carregar (ex: update_task, delete_contact)",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        tool_name = params.get("tool_name", "").strip()

        if not tool_name:
            return ToolResult.error("Nome da ferramenta e obrigatorio.")

        # Check if it's a valid tier 2 tool
        if tool_name not in TIER_2_TOOLS:
            if tool_name in TIER_1_TOOLS:
                return ToolResult.ok(
                    f"Ferramenta '{tool_name}' ja esta carregada e disponivel.",
                    display_text=f"A ferramenta '{tool_name}' ja esta ativa.",
                )
            return ToolResult.error(
                f"Ferramenta '{tool_name}' nao encontrada. "
                "Use list_available_tools para ver opcoes."
            )

        # Get tool details from registry
        from .registry import get_tool_registry
        registry = get_tool_registry()
        tool = registry.get(tool_name)

        if not tool:
            return ToolResult.error(f"Ferramenta '{tool_name}' nao registrada.")

        # Build schema info for the LLM
        schema_info = []
        schema_info.append(f"Ferramenta: {tool.name}")
        schema_info.append(f"Descricao: {tool.description}")
        schema_info.append("Parametros:")
        for p in tool.parameters:
            req = "(obrigatorio)" if p.required else "(opcional)"
            schema_info.append(f"  - {p.name} ({p.type}) {req}: {p.description}")
            if p.enum:
                schema_info.append(f"    Valores: {', '.join(p.enum)}")

        # Signal to the agent that this tool should be added to active tools
        # The react_agent reads this from result.data["loaded_tool"]
        return ToolResult.ok(
            f"Ferramenta '{tool_name}' carregada com sucesso.",
            data={"loaded_tool": tool_name},
            display_text="\n".join(schema_info),
        )
