"""
CreateAppointment Tool - Creates a new appointment/meeting.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class CreateAppointmentTool(Tool):
    """Creates a new appointment in the calendar."""

    name = "create_appointment"
    description = "Agenda um novo compromisso ou reunião"
    category = "calendar"

    parameters = [
        ToolParameter(
            name="title",
            type="string",
            description="Título do compromisso",
            required=True,
        ),
        ToolParameter(
            name="datetime",
            type="string",
            description="Data e hora (ISO 8601 ou texto como 'amanhã às 10h')",
            required=True,
        ),
        ToolParameter(
            name="duration",
            type="number",
            description="Duração em minutos",
            required=False,
            default=60,
        ),
        ToolParameter(
            name="location",
            type="string",
            description="Local do compromisso",
            required=False,
        ),
        ToolParameter(
            name="type",
            type="string",
            description="Tipo de compromisso (ex: 'reuniao', 'call', 'presencial')",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        title = params.get("title", "").strip()
        if not title:
            return ToolResult.error("Título do compromisso é obrigatório")

        datetime_str = params.get("datetime", "").strip()
        if not datetime_str:
            return ToolResult.ok(
                message="Preciso da data e hora do compromisso",
                data={"needs_clarification": True, "field": "datetime"},
                display_text="Qual dia e horário do compromisso?",
            )

        duration = params.get("duration")
        location = params.get("location")
        type_name = params.get("type")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone

        # Resolve type and get default duration if not specified
        type_id = None
        type_display = ""
        if type_name and owner_id:
            apt_type = storage.get_category_by_name(owner_id, type_name, "appointment")
            if apt_type:
                type_id = apt_type.get("id")
                type_display = f" [{apt_type['name']}]"
                # Use type's default duration if not explicitly provided
                if duration is None:
                    duration = apt_type.get("default_duration", 60)

        # Default duration if still not set
        if duration is None:
            duration = 60
        duration = int(duration)

        # Parse datetime
        scheduled_at = self._parse_datetime(datetime_str, context)
        if not scheduled_at:
            return ToolResult.ok(
                message="Não consegui entender a data/hora",
                data={"needs_clarification": True, "field": "datetime"},
                display_text="Não entendi a data. Pode informar no formato DD/MM às HH:MM?",
            )

        try:
            # storage.create_appointment returns Appointment object
            appointment = storage.create_appointment(
                title=title,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
            )

            # Update with type if found (after creation)
            if type_id:
                storage.update_appointment(appointment.id, type_id=type_id, location=location)

            return ToolResult.ok(
                message="Compromisso agendado",
                data={
                    "appointment_id": appointment.id,
                    "title": appointment.title,
                    "scheduled_at": appointment.scheduled_at,
                    "duration_minutes": appointment.duration_minutes,
                    "location": location,
                    "type": type_name,
                },
                display_text=f"📅 Compromisso agendado: {title}{type_display} em {datetime_str}",
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao criar compromisso: {str(e)}")

    def _parse_datetime(self, datetime_str: str, context: ToolContext) -> str | None:
        """Parse datetime string to ISO format using dateparser."""
        import dateparser
        from datetime import datetime

        if not datetime_str:
            return None

        # Use dateparser for intelligent parsing
        # Handles: "amanhã às 10h", "10/02 às 14h", "10:00", "próxima sexta", etc.
        parsed = dateparser.parse(
            datetime_str,
            languages=['pt', 'en'],
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(),
            }
        )

        if parsed:
            return parsed.isoformat()

        return None
