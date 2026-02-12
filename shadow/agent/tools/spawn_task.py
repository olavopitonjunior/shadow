"""SpawnTask tool - delegates analysis tasks to background subagents.

Adapted from nanobot/agent/tools/spawn.py.
"""

from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class SpawnTaskTool(Tool):
    """Delegates a long-running analysis task to a background subagent."""

    name = "spawn_task"
    description = (
        "Delega uma tarefa de análise ou relatório para rodar em background. "
        "O resultado será enviado quando concluído. Útil para tarefas longas "
        "como resumos de contatos, análise de compromissos, relatórios etc."
    )
    category = "sistema"
    parameters = [
        ToolParameter(
            "task",
            "string",
            "Descrição detalhada da tarefa para o subagente executar",
            required=True,
        ),
        ToolParameter(
            "label",
            "string",
            "Rótulo curto para identificar a tarefa (ex: 'Relatório de contatos')",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        task = params.get("task", "").strip()
        label = params.get("label")

        if not task:
            return ToolResult.error("Descrição da tarefa é obrigatória.")

        try:
            from subagent import get_subagent_manager
            manager = get_subagent_manager()
            status = manager.spawn(task, label, context)
            return ToolResult.ok(status)
        except Exception as e:
            return ToolResult.error(f"Erro ao iniciar tarefa: {str(e)}")
