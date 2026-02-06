"""
CreateAlert Tool - Creates a scheduled alert.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateAlertTool(Tool):
    """Creates a new RECURRING scheduled alert (not for one-time alerts)."""

    name = "create_alert"
    description = "Cria um alerta RECORRENTE programado (resumo diário, lembrete semanal fixo). Para alertas ÚNICOS como 'me avise daqui 1 minuto' ou 'lembre-me às 15h', use create_reminder."
    category = "alerts"

    parameters = [
        ToolParameter(
            name="time",
            type="string",
            description="Horário do alerta (formato HH:MM, ex: '07:00', '14:30')",
            required=True,
        ),
        ToolParameter(
            name="type",
            type="string",
            description="Tipo do alerta",
            required=False,
            enum=["summary", "reminder", "custom"],
            default="summary",
        ),
        ToolParameter(
            name="message",
            type="string",
            description="Mensagem do alerta (obrigatório para tipo 'reminder' ou 'custom')",
            required=False,
        ),
        ToolParameter(
            name="recurrence",
            type="string",
            description="Frequência do alerta",
            required=False,
            enum=["daily", "weekdays", "weekly", "custom"],
            default="daily",
        ),
        ToolParameter(
            name="days",
            type="string",
            description="Dias da semana (1=Seg, 7=Dom), separados por vírgula. Ex: '1,2,3,4,5' para dias úteis",
            required=False,
        ),
        ToolParameter(
            name="name",
            type="string",
            description="Nome amigável para o alerta (opcional)",
            required=False,
        ),
        ToolParameter(
            name="include_tasks",
            type="boolean",
            description="Incluir tarefas no resumo (default: true)",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="include_appointments",
            type="boolean",
            description="Incluir compromissos no resumo (default: true)",
            required=False,
            default=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        time_str = params.get("time", "").strip()
        if not time_str:
            return ToolResult.error("Horário do alerta é obrigatório (formato HH:MM)")

        # Validate time format
        if not self._validate_time(time_str):
            return ToolResult.error("Formato de horário inválido. Use HH:MM (ex: 07:00)")

        alert_type = params.get("type", "summary")
        message = params.get("message")
        recurrence = params.get("recurrence", "daily")
        days_str = params.get("days")
        name = params.get("name")
        include_tasks = params.get("include_tasks", True)
        include_appointments = params.get("include_appointments", True)

        # Validate message for reminder/custom types
        if alert_type in ("reminder", "custom") and not message:
            return ToolResult.error(f"Mensagem é obrigatória para alertas do tipo '{alert_type}'")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Parse days of week
        days_of_week = None
        if days_str:
            try:
                days_of_week = [int(d.strip()) for d in days_str.split(",")]
                if not all(1 <= d <= 7 for d in days_of_week):
                    return ToolResult.error("Dias devem estar entre 1 (Segunda) e 7 (Domingo)")
            except ValueError:
                return ToolResult.error("Formato de dias inválido. Use números separados por vírgula")
        elif recurrence == "weekdays":
            days_of_week = [1, 2, 3, 4, 5]

        # Get user timezone
        settings = storage.get_user_settings(owner_id)
        timezone = settings.get("timezone", "America/Sao_Paulo")

        try:
            result = storage.create_scheduled_alert(
                owner_id=owner_id,
                alert_time=time_str,
                alert_type=alert_type,
                recurrence=recurrence,
                days_of_week=days_of_week,
                custom_message=message,
                include_tasks=include_tasks,
                include_appointments=include_appointments,
                name=name,
                timezone=timezone,
            )

            if result.get("success"):
                # Format display
                type_labels = {
                    "summary": "Resumo diário",
                    "reminder": "Lembrete",
                    "custom": "Alerta personalizado",
                }
                recurrence_labels = {
                    "daily": "todos os dias",
                    "weekdays": "dias úteis",
                    "weekly": "semanalmente",
                    "custom": "dias específicos",
                }
                type_label = type_labels.get(alert_type, alert_type)
                rec_label = recurrence_labels.get(recurrence, recurrence)

                display = f"⏰ Alerta criado: {type_label} às {time_str} ({rec_label})"
                if name:
                    display = f"⏰ '{name}' criado às {time_str} ({rec_label})"

                return ToolResult.ok(
                    message="Alerta criado",
                    data=result,
                    display_text=display,
                )
            else:
                return ToolResult.error(result.get("error", "Erro ao criar alerta"))

        except Exception as e:
            return ToolResult.error(f"Erro ao criar alerta: {str(e)}")

    def _validate_time(self, time_str: str) -> bool:
        """Validate time format HH:MM."""
        import re
        if not re.match(r"^\d{1,2}:\d{2}$", time_str):
            return False
        try:
            hours, minutes = time_str.split(":")
            return 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59
        except ValueError:
            return False
