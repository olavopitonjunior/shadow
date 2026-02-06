"""
ListAlerts Tool - Lists scheduled alerts.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ListAlertsTool(Tool):
    """Lists all scheduled alerts for the user."""

    name = "list_alerts"
    description = "Lista todos os alertas programados do usuário"
    category = "alerts"

    parameters = [
        ToolParameter(
            name="include_inactive",
            type="boolean",
            description="Incluir alertas desativados (default: false)",
            required=False,
            default=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        include_inactive = params.get("include_inactive", False)

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            alerts = storage.list_scheduled_alerts(owner_id, active_only=not include_inactive)

            if not alerts:
                return ToolResult.ok(
                    message="Nenhum alerta encontrado",
                    data={"alerts": []},
                    display_text="📭 Você não tem alertas programados.",
                )

            # Format display
            lines = ["⏰ *Seus alertas programados:*", ""]

            type_labels = {
                "summary": "📋 Resumo",
                "reminder": "🔔 Lembrete",
                "custom": "✨ Personalizado",
            }
            recurrence_labels = {
                "daily": "diário",
                "weekdays": "dias úteis",
                "weekly": "semanal",
                "custom": "personalizado",
            }
            day_names = {1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom"}

            for alert in alerts:
                alert_id = alert.get("id")
                time = alert.get("alert_time", "??:??")
                alert_type = alert.get("alert_type", "summary")
                recurrence = alert.get("recurrence", "daily")
                name = alert.get("name")
                is_active = alert.get("is_active", True)
                days = alert.get("days_of_week", [])

                type_label = type_labels.get(alert_type, alert_type)
                rec_label = recurrence_labels.get(recurrence, recurrence)

                # Build alert line
                status = "✅" if is_active else "⏸️"
                if name:
                    line = f"{status} *{name}* - {time} ({rec_label})"
                else:
                    line = f"{status} {type_label} às {time} ({rec_label})"

                # Add days if custom
                if recurrence == "custom" and days:
                    days_str = ", ".join(day_names.get(d, str(d)) for d in sorted(days))
                    line += f" [{days_str}]"

                # Add message preview for reminder/custom
                if alert_type in ("reminder", "custom"):
                    message = alert.get("custom_message", "")
                    if message:
                        preview = message[:30] + "..." if len(message) > 30 else message
                        line += f"\n   └ \"{preview}\""

                line += f"  (ID: {alert_id})"
                lines.append(line)

            display_text = "\n".join(lines)

            return ToolResult.ok(
                message=f"{len(alerts)} alertas encontrados",
                data={"alerts": alerts, "count": len(alerts)},
                display_text=display_text,
            )

        except Exception as e:
            return ToolResult.error(f"Erro ao listar alertas: {str(e)}")
