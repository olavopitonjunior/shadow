"""
CreateReminder Tool - Creates a reminder to be sent later.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateReminderTool(Tool):
    """Creates a one-time reminder to be sent at a specific time."""

    name = "create_reminder"
    description = "Cria um lembrete ÚNICO para ser enviado em um horário específico. Use para: 'lembre-me em X minutos', 'avise-me às 15h', 'alerta daqui 1 hora', 'me envie um alerta em 5 min'. NÃO use create_alert para alertas únicos."
    category = "reminders"

    parameters = [
        ToolParameter(
            name="message",
            type="string",
            description="Mensagem do lembrete",
            required=True,
        ),
        ToolParameter(
            name="when",
            type="string",
            description="Quando enviar (ISO 8601 ou texto como 'amanhã às 9h')",
            required=True,
        ),
        ToolParameter(
            name="task_id",
            type="number",
            description="ID da tarefa relacionada (opcional)",
            required=False,
        ),
        ToolParameter(
            name="target_phone",
            type="string",
            description="Telefone destino (opcional, usa sessão atual se não especificado)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        message = params.get("message", "").strip()
        if not message:
            return ToolResult.error("Mensagem do lembrete é obrigatória")

        when_str = params.get("when", "").strip()
        if not when_str:
            return ToolResult.ok(
                message="Preciso saber quando enviar o lembrete",
                data={"needs_clarification": True, "field": "when"},
                display_text="Quando devo te lembrar?",
            )

        task_id = params.get("task_id")
        target_phone = params.get("target_phone")

        # If no explicit target, use session's user phone (Phase 4)
        if not target_phone and context.user_phone:
            target_phone = context.user_phone

        # Parse when
        remind_at = self._parse_datetime(when_str, context)
        if not remind_at:
            return ToolResult.ok(
                message="Não consegui entender o horário",
                data={"needs_clarification": True, "field": "when"},
                display_text="Não entendi o horário. Pode informar de outra forma?",
            )

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        try:
            # storage.create_reminder returns None (void)
            storage.create_reminder(
                remind_at=remind_at,
                message=message,
                task_id=task_id,
                target_phone=target_phone,
            )

            return ToolResult.ok(
                message="Lembrete criado",
                data={
                    "message": message,
                    "remind_at": remind_at,
                    "task_id": task_id,
                    "target_phone": target_phone,
                },
                display_text=f"⏰ Lembrete criado para {when_str}: {message}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao criar lembrete: {str(e)}")

    def _parse_datetime(self, datetime_str: str, context: ToolContext) -> str | None:
        """Parse datetime string to ISO format."""
        from datetime import datetime, timedelta
        import re

        lower = datetime_str.lower().strip()
        now = datetime.fromisoformat(context.timestamp) if context.timestamp else datetime.now()

        # Relative time patterns
        # Pattern: "daqui X minuto(s)", "daqui X min"
        daqui_min = re.search(r"daqui\s+(\d+)\s*min", lower)
        if daqui_min:
            minutes = int(daqui_min.group(1))
            return (now + timedelta(minutes=minutes)).isoformat()

        # Pattern: "daqui X hora(s)"
        daqui_hour = re.search(r"daqui\s+(\d+)\s*hora", lower)
        if daqui_hour:
            hours = int(daqui_hour.group(1))
            return (now + timedelta(hours=hours)).isoformat()

        # Pattern: "em X minuto(s)", "em X min"
        in_minutes = re.search(r"em (\d+)\s*min", lower)
        if in_minutes:
            minutes = int(in_minutes.group(1))
            return (now + timedelta(minutes=minutes)).isoformat()

        in_hours = re.search(r"em (\d+)\s*hora", lower)
        if in_hours:
            hours = int(in_hours.group(1))
            return (now + timedelta(hours=hours)).isoformat()

        # Extract time if present
        time_match = re.search(r"(\d{1,2})[h:](\d{2})?", lower)
        hour, minute = None, 0
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)

        # Parse date part
        if "hoje" in lower or "today" in lower:
            base_date = now.date()
            if hour is None:
                hour = now.hour + 1  # Default: 1 hour from now
        elif "amanhã" in lower or "amanha" in lower or "tomorrow" in lower:
            base_date = (now + timedelta(days=1)).date()
            if hour is None:
                hour = 9  # Default morning
        else:
            # Try to find date pattern
            date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", lower)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3)) if date_match.group(3) else now.year
                if year < 100:
                    year += 2000
                try:
                    base_date = datetime(year, month, day).date()
                    if hour is None:
                        hour = 9
                except ValueError:
                    return None
            else:
                # Try ISO format
                try:
                    return datetime.fromisoformat(datetime_str).isoformat()
                except ValueError:
                    return None

        if hour is None:
            hour = 9

        # Combine date and time
        result = datetime(base_date.year, base_date.month, base_date.day, hour, minute)
        return result.isoformat()
