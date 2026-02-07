"""
ManageMonitoredGroups Tool - Manages which WhatsApp groups are monitored for suggestions.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ManageMonitoredGroupsTool(Tool):
    """Manages which WhatsApp groups are monitored for proactive suggestions."""

    name = "manage_monitored_groups"
    description = "Gerencia quais grupos do WhatsApp são monitorados para sugestões proativas (listar, adicionar, remover)"
    category = "suggestions"

    parameters = [
        ToolParameter(
            name="action",
            type="string",
            description="Ação a executar: list, add, remove",
            required=True,
            enum=["list", "add", "remove"],
        ),
        ToolParameter(
            name="group_jid",
            type="string",
            description="JID do grupo (para add/remove). Ex: 123456789@g.us",
            required=False,
        ),
        ToolParameter(
            name="group_name",
            type="string",
            description="Nome amigável do grupo (opcional, para referência)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        action = params.get("action", "list")
        group_jid = params.get("group_jid")
        group_name = params.get("group_name", "")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            if action == "list":
                return self._list_groups(storage, owner_id)
            elif action == "add":
                return self._add_group(storage, owner_id, group_jid, group_name)
            elif action == "remove":
                return self._remove_group(storage, owner_id, group_jid)
            else:
                return ToolResult.error(f"Ação desconhecida: {action}")

        except Exception as e:
            return ToolResult.error(f"Erro ao gerenciar grupos: {str(e)}")

    def _list_groups(self, storage: Any, owner_id: str) -> ToolResult:
        """List all monitored groups."""
        groups = storage.get_monitored_groups(owner_id)
        settings = storage.get_user_settings(owner_id)
        monitor_all = settings.get("monitor_all_groups", False)

        if monitor_all:
            return ToolResult.ok(
                message="Monitoramento de todos os grupos está ativo",
                data={"groups": groups, "monitor_all": True},
                display_text="🔍 Monitorando TODOS os grupos.\nPara monitorar apenas alguns, desative 'monitor_all_groups' nas configurações.",
            )

        if not groups:
            return ToolResult.ok(
                message="Nenhum grupo monitorado",
                data={"groups": [], "monitor_all": False},
                display_text="📱 Nenhum grupo sendo monitorado.\n\nPara adicionar, use:\n- manage_monitored_groups(action='add', group_jid='123@g.us')",
            )

        lines = ["📱 Grupos monitorados:"]
        for i, jid in enumerate(groups, 1):
            # Extract group ID from JID
            display = jid.replace("@g.us", "") if "@g.us" in jid else jid
            lines.append(f"{i}. {display}")

        lines.append("")
        lines.append("Para remover: manage_monitored_groups(action='remove', group_jid='...')")

        return ToolResult.ok(
            message=f"{len(groups)} grupos monitorados",
            data={"groups": groups, "monitor_all": False},
            display_text="\n".join(lines),
        )

    def _add_group(
        self,
        storage: Any,
        owner_id: str,
        group_jid: str | None,
        group_name: str,
    ) -> ToolResult:
        """Add a group to monitored list."""
        if not group_jid:
            return ToolResult.error(
                "group_jid é obrigatório. Formato: 123456789@g.us"
            )

        # Normalize JID
        if not group_jid.endswith("@g.us"):
            group_jid = f"{group_jid}@g.us"

        added = storage.add_monitored_group(owner_id, group_jid)

        if added:
            display = group_jid.replace("@g.us", "")
            name_part = f" ({group_name})" if group_name else ""
            return ToolResult.ok(
                message="Grupo adicionado à lista de monitoramento",
                data={"group_jid": group_jid, "added": True},
                display_text=f"✅ Grupo {display}{name_part} adicionado ao monitoramento.\n\nMensagens deste grupo agora gerarão sugestões proativas.",
            )
        else:
            return ToolResult.ok(
                message="Grupo já estava na lista",
                data={"group_jid": group_jid, "added": False},
                display_text=f"ℹ️ Grupo já está sendo monitorado.",
            )

    def _remove_group(
        self,
        storage: Any,
        owner_id: str,
        group_jid: str | None,
    ) -> ToolResult:
        """Remove a group from monitored list."""
        if not group_jid:
            return ToolResult.error(
                "group_jid é obrigatório"
            )

        # Normalize JID
        if not group_jid.endswith("@g.us"):
            group_jid = f"{group_jid}@g.us"

        removed = storage.remove_monitored_group(owner_id, group_jid)

        if removed:
            display = group_jid.replace("@g.us", "")
            return ToolResult.ok(
                message="Grupo removido da lista de monitoramento",
                data={"group_jid": group_jid, "removed": True},
                display_text=f"✅ Grupo {display} removido do monitoramento.",
            )
        else:
            return ToolResult.ok(
                message="Grupo não estava na lista",
                data={"group_jid": group_jid, "removed": False},
                display_text=f"ℹ️ Grupo não estava sendo monitorado.",
            )
