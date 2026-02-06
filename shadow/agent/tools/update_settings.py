"""
UpdateSettings Tool - Updates user settings.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class UpdateSettingsTool(Tool):
    """Updates user settings and preferences."""

    name = "update_settings"
    description = "Atualiza configurações do usuário"
    category = "settings"

    parameters = [
        ToolParameter(
            name="setting",
            type="string",
            description="Nome da configuração a alterar",
            required=True,
            enum=[
                "always_ask_incomplete",
                "auto_create_from_conversations",
                "group_monitoring_enabled",
                "default_reminder_minutes",
                "morning_summary_enabled",
                "morning_summary_time",
                "gcal_check_conflicts",
                "gcal_auto_sync",
                "timezone",
                "language",
                "use_emojis",
                "verbose_responses",
            ],
        ),
        ToolParameter(
            name="value",
            type="string",
            description="Novo valor da configuração (true/false para booleanos, número para minutos, texto para outros)",
            required=True,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        setting = params.get("setting", "").strip()
        value = params.get("value", "").strip()

        if not setting:
            return ToolResult.error("Nome da configuração é obrigatório")
        if not value:
            return ToolResult.error("Valor da configuração é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Parse value based on setting type
        bool_settings = [
            "always_ask_incomplete",
            "auto_create_from_conversations",
            "group_monitoring_enabled",
            "morning_summary_enabled",
            "gcal_check_conflicts",
            "gcal_auto_sync",
            "use_emojis",
            "verbose_responses",
        ]
        int_settings = ["default_reminder_minutes"]

        try:
            if setting in bool_settings:
                parsed_value = value.lower() in ("true", "1", "sim", "yes", "ativar", "on")
            elif setting in int_settings:
                parsed_value = int(value)
            else:
                parsed_value = value

            # Update the setting
            updated = storage.update_user_settings(owner_id, **{setting: parsed_value})

            # Format confirmation
            setting_labels = {
                "always_ask_incomplete": "Perguntar quando incompleto",
                "auto_create_from_conversations": "Criar automaticamente de conversas",
                "group_monitoring_enabled": "Monitorar grupos",
                "default_reminder_minutes": "Antecedência padrão de lembretes",
                "morning_summary_enabled": "Resumo matinal",
                "morning_summary_time": "Horário do resumo matinal",
                "gcal_check_conflicts": "Verificar conflitos no Google Calendar",
                "gcal_auto_sync": "Sincronização automática com Google Calendar",
                "timezone": "Fuso horário",
                "language": "Idioma",
                "use_emojis": "Usar emojis",
                "verbose_responses": "Respostas detalhadas",
            }

            label = setting_labels.get(setting, setting)
            display_value = "✅ Ativado" if parsed_value is True else "❌ Desativado" if parsed_value is False else str(parsed_value)

            return ToolResult.ok(
                message="Configuração atualizada",
                data={"setting": setting, "value": parsed_value, "all_settings": updated},
                display_text=f"⚙️ {label}: {display_value}",
            )
        except ValueError as e:
            return ToolResult.error(f"Valor inválido: {str(e)}")
        except Exception as e:
            return ToolResult.error(f"Erro ao atualizar configuração: {str(e)}")
