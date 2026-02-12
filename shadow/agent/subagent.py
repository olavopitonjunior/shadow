"""Subagent manager for background task execution.

Adapted from nanobot/agent/subagent.py.
Uses threading (sync) instead of asyncio for Shadow's architecture.
Subagents have read-only tool access and send results via MessageBus.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests

from providers import LLMProvider, LLMResponse, get_provider
from tools import ToolRegistry, ToolContext, ToolResult
from tools.base import Tool
from bus import OutboundMessage, get_message_bus

# Read-only tools allowed for subagents
SUBAGENT_ALLOWED_TOOLS = {
    "list_tasks",
    "list_appointments",
    "get_contact",
    "list_contacts",
    "recall_memory",
    "contact_history",
    "preview_summary",
    "get_settings",
    "list_categories",
    "list_alerts",
    "list_suggestions",
    "list_available_tools",
}

MAX_CONCURRENT_SUBAGENTS = 3
MAX_SUBAGENT_ITERATIONS = 10


@dataclass
class SubagentResult:
    """Result from a completed subagent."""
    task_id: str
    label: str
    status: str  # "ok" | "error"
    result: str
    elapsed_s: float = 0.0


class SubagentManager:
    """
    Manages background subagent execution in threads.

    Subagents are lightweight agent instances with read-only tools
    that run in background threads for long-running analysis tasks.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        gateway_url: str | None = None,
    ):
        self.provider = provider
        self.gateway_url = gateway_url
        self._running_tasks: dict[str, threading.Thread] = {}
        self._results: dict[str, SubagentResult] = {}

    def spawn(
        self,
        task: str,
        label: str | None = None,
        context: ToolContext | None = None,
    ) -> str:
        """
        Spawn a subagent to execute a task in the background.

        Args:
            task: Task description for the subagent.
            label: Optional human-readable label.
            context: Tool context for storage access.

        Returns:
            Status message indicating the subagent was started.
        """
        if len(self._running_tasks) >= MAX_CONCURRENT_SUBAGENTS:
            return (
                f"Limite de {MAX_CONCURRENT_SUBAGENTS} tarefas simultâneas atingido. "
                "Aguarde uma tarefa finalizar."
            )

        task_id = str(uuid.uuid4())[:8]
        display_label = label or (task[:30] + ("..." if len(task) > 30 else ""))

        thread = threading.Thread(
            target=self._run_subagent,
            args=(task_id, task, display_label, context),
            name=f"subagent-{task_id}",
            daemon=True,
        )
        self._running_tasks[task_id] = thread
        thread.start()

        print(f"[subagent] Spawned [{task_id}]: {display_label}")
        return (
            f"Tarefa '{display_label}' iniciada em background (id: {task_id}). "
            "Você será notificado quando concluir."
        )

    def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        context: ToolContext | None,
    ) -> None:
        """Execute the subagent task and announce the result."""
        start = time.monotonic()
        print(f"[subagent] [{task_id}] Starting: {label}")

        try:
            # Build read-only tool registry
            registry = self._build_read_only_registry(context)

            # Get or create provider
            provider = self.provider or get_provider()

            # Build tool definitions (OpenAI format)
            from tool_adapter import to_openai_tools, format_tool_result_openai
            tools = []
            for tool_name in registry.list_tools():
                tool = registry.get(tool_name)
                if tool:
                    from tool_adapter import tool_to_openai_format
                    tools.append(tool_to_openai_format(tool))

            # System prompt
            system_prompt = self._build_prompt(task)

            # Messages
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": task},
            ]

            # Run agent loop
            import json
            final_result: str | None = None

            for iteration in range(MAX_SUBAGENT_ITERATIONS):
                response: LLMResponse = provider.chat(
                    messages=messages,
                    tools=tools if tools else None,
                    system=system_prompt,
                )

                if response.finish_reason == "error":
                    final_result = f"Erro: {response.content}"
                    break

                if not response.has_tool_calls:
                    final_result = response.content
                    break

                # Build assistant message
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                # Execute tools
                for tc in response.tool_calls:
                    print(f"[subagent] [{task_id}] Executing: {tc.name}")
                    result = registry.execute(tc.name, tc.arguments, context)
                    result_text = result.display_text or result.message
                    messages.append(format_tool_result_openai(
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        result=result_text,
                    ))

            if final_result is None:
                final_result = "Tarefa concluída sem resposta final."

            elapsed = time.monotonic() - start
            self._results[task_id] = SubagentResult(
                task_id=task_id, label=label, status="ok",
                result=final_result, elapsed_s=elapsed,
            )
            print(f"[subagent] [{task_id}] Completed in {elapsed:.1f}s")
            self._announce_result(task_id, label, final_result)

        except Exception as e:
            elapsed = time.monotonic() - start
            error_msg = f"Erro na tarefa '{label}': {str(e)}"
            self._results[task_id] = SubagentResult(
                task_id=task_id, label=label, status="error",
                result=error_msg, elapsed_s=elapsed,
            )
            print(f"[subagent] [{task_id}] Failed: {e}")
            self._announce_result(task_id, label, error_msg)

        finally:
            self._running_tasks.pop(task_id, None)

    def _build_read_only_registry(self, context: ToolContext | None) -> ToolRegistry:
        """Build a registry with only read-only tools."""
        from tools import get_tool_registry
        full_registry = get_tool_registry()
        read_only = ToolRegistry()

        for tool_name in SUBAGENT_ALLOWED_TOOLS:
            tool = full_registry.get(tool_name)
            if tool:
                read_only.register(tool)

        return read_only

    def _build_prompt(self, task: str) -> str:
        """Build focused system prompt for the subagent."""
        return f"""Você é um subagente do Shadow, executando uma tarefa específica em background.

TAREFA: {task}

REGRAS:
1. Foque APENAS na tarefa atribuída
2. Use as ferramentas disponíveis para coletar informações
3. Você só tem acesso a ferramentas de LEITURA (listar, buscar)
4. NÃO pode criar, editar ou excluir dados
5. Seja conciso e informativo no resultado
6. Responda em português brasileiro

Ao finalizar, forneça um resumo claro dos resultados encontrados."""

    def _announce_result(self, task_id: str, label: str, result: str) -> None:
        """Send the subagent result via message bus."""
        try:
            bus = get_message_bus()
            content = f"[Tarefa '{label}' concluída]\n\n{result}"
            bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id="owner",
                content=content,
            ))
        except Exception as e:
            print(f"[subagent] [{task_id}] Failed to announce: {e}")

    def get_running_count(self) -> int:
        """Number of currently running subagents."""
        return len(self._running_tasks)

    def get_result(self, task_id: str) -> SubagentResult | None:
        """Get result for a completed subagent."""
        return self._results.get(task_id)

    def status(self) -> dict[str, Any]:
        """Get subagent manager status."""
        return {
            "running": list(self._running_tasks.keys()),
            "completed": len(self._results),
            "max_concurrent": MAX_CONCURRENT_SUBAGENTS,
        }


# Singleton
_subagent_manager: SubagentManager | None = None


def get_subagent_manager() -> SubagentManager:
    """Get or create the subagent manager singleton."""
    global _subagent_manager
    if _subagent_manager is None:
        _subagent_manager = SubagentManager()
    return _subagent_manager


def reset_subagent_manager() -> None:
    """Reset the singleton (useful for testing)."""
    global _subagent_manager
    _subagent_manager = None
