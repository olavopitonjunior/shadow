"""
GetSettings Tool - Retrieves user settings.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class GetSettingsTool(Tool):
    """Retrieves user settings and preferences."""

    name = "get_settings"
    description = "Mostra as configurações atuais do usuário"
    category = "settings"

    parameters = []

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        try:
            settings = storage.get_user_settings(owner_id)

            # Format for display
            lines = ["⚙️ *Suas configurações:*", ""]

            # Behavior settings
            lines.append("📝 *Comportamento:*")
            lines.append(f"• Perguntar quando incompleto: {'✅' if settings.get('always_ask_incomplete', True) else '❌'}")
            lines.append(f"• Criar automaticamente de conversas: {'✅' if settings.get('auto_create_from_conversations', False) else '❌'}")
            lines.append(f"• Monitorar grupos: {'✅' if settings.get('group_monitoring_enabled', False) else '❌'}")
            lines.append("")

            # Reminders
            lines.append("⏰ *Lembretes:*")
            lines.append(f"• Antecedência padrão: {settings.get('default_reminder_minutes', 30)} min")
            lines.append(f"• Resumo matinal: {'✅ ' + settings.get('morning_summary_time', '07:00') if settings.get('morning_summary_enabled', False) else '❌'}")
            lines.append("")

            # Google Calendar (future)
            lines.append("📅 *Google Calendar:*")
            lines.append(f"• Verificar conflitos: {'✅' if settings.get('gcal_check_conflicts', True) else '❌'}")
            lines.append(f"• Sincronização automática: {'✅' if settings.get('gcal_auto_sync', True) else '❌'}")
            lines.append("")

            # Preferences
            lines.append("🌐 *Preferências:*")
            lines.append(f"• Fuso horário: {settings.get('timezone', 'America/Sao_Paulo')}")
            lines.append(f"• Idioma: {settings.get('language', 'pt-BR')}")
            lines.append(f"• Usar emojis: {'✅' if settings.get('use_emojis', True) else '❌'}")
            lines.append(f"• Respostas detalhadas: {'✅' if settings.get('verbose_responses', False) else '❌'}")

            display_text = "\n".join(lines)

            return ToolResult.ok(
                message="Configurações recuperadas",
                data=settings,
                display_text=display_text,
            )
        except Exception as e:
            return ToolResult.error(f"Erro ao buscar configurações: {str(e)}")
