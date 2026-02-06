"""
DeleteAppointment Tool - Deletes an appointment.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class DeleteAppointmentTool(Tool):
    """Deletes an appointment from the system."""

    name = "delete_appointment"
    description = "Exclui um compromisso permanentemente"
    category = "appointments"

    parameters = [
        ToolParameter(
            name="appointment_id",
            type="integer",
            description="ID do compromisso a ser excluído",
            required=True,
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirmação obrigatória para exclusão",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        appointment_id = params.get("appointment_id")
        if not appointment_id:
            return ToolResult.error("ID do compromisso é obrigatório")

        confirm = params.get("confirm", False)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        # Get appointment first to show details
        appointment = storage.get_appointment(appointment_id)
        if not appointment:
            return ToolResult.error(f"Compromisso #{appointment_id} não encontrado")

        # Require confirmation for deletion
        if not confirm:
            return ToolResult.ok(
                message="Confirmação necessária",
                data={
                    "needs_confirmation": True,
                    "appointment_id": appointment_id,
                    "title": appointment.title,
                    "scheduled_at": appointment.scheduled_at,
                },
                display_text=f"⚠️ Deseja excluir o compromisso '{appointment.title}' "
                f"agendado para {appointment.scheduled_at}?\n"
                f"Use confirm=true para confirmar.",
            )

        try:
            result = storage.delete_appointment(appointment_id)

            if not result.get("success"):
                return ToolResult.error(result.get("error", "Erro desconhecido"))

            return ToolResult.ok(
                message="Compromisso excluído com sucesso",
                data=result,
                display_text=f"🗑️ Compromisso '{result['title']}' excluído",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao excluir compromisso: {str(e)}")
