"""
DeleteAlert Tool - Deletes or deactivates a scheduled alert.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class DeleteAlertTool(Tool):
    """Deletes or deactivates a scheduled alert."""

    name = "delete_alert"
    description = "Remove ou desativa um alerta programado"
    category = "alerts"

    parameters = [
        ToolParameter(
            name="alert_id",
            type="integer",
            description="ID do alerta a ser removido",
            required=True,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirmar a exclusão (obrigatório)",
            required=True,
        ),
        ToolParameter(
            name="hard_delete",
            type="boolean",
            description="Excluir permanentemente (default: false = apenas desativa)",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        alert_id = params.get("alert_id")
        confirm = params.get("confirm", False)
        hard_delete = params.get("hard_delete", False)

        if not alert_id:
            return ToolResult.error("ID do alerta é obrigatório")

        if not confirm:
            return ToolResult.ok(
                message="Confirmação necessária",
                data={"needs_confirmation": True, "alert_id": alert_id},
                display_text="⚠️ Para excluir o alerta, confirme com confirm=true",
            )

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            # Get alert info before deleting
            alert = storage.get_scheduled_alert(owner_id, alert_id)
            if not alert:
                return ToolResult.error(f"Alerta #{alert_id} não encontrado")

            success = storage.delete_scheduled_alert(owner_id, alert_id, hard_delete=hard_delete)

            if success:
                action = "excluído" if hard_delete else "desativado"
                name = alert.get("name") or f"Alerta #{alert_id}"
                return ToolResult.ok(
                    message=f"Alerta {action}",
                    data={"alert_id": alert_id, "hard_delete": hard_delete},
                    display_text=f"🗑️ '{name}' foi {action} com sucesso",
                )
            else:
                return ToolResult.error("Não foi possível remover o alerta")

        except Exception as e:
            return ToolResult.error(f"Erro ao excluir alerta: {str(e)}")
