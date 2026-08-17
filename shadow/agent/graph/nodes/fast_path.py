"""
Fast-path node - Handle simple commands without LLM.

Processes exact-match commands like greetings, task listing,
appointment listing, etc. using direct tool execution.
"""

from __future__ import annotations

from typing import Any

from graph.state import ShadowState


# Greeting responses (no tool needed)
GREETINGS = {"oi", "olá", "ola", "hey", "hi", "hello"}
FAREWELLS = {"tchau", "bye", "até mais"}
ACKS = {"ok", "obrigado", "valeu", "sim", "não", "nao"}


def fast_path_node(state: ShadowState) -> dict[str, Any]:
    """Handle simple commands without LLM invocation.

    Falls back to existing message_handler fast-path logic
    for tool-based commands (list tasks, appointments, etc.).
    """
    body = (state.get("body") or "").strip().lower()

    # Greetings
    if body in GREETINGS:
        return {
            "reply": "Olá! Como posso ajudar? 😊",
            "steps": [{"node": "fast_path", "intent": "greeting"}],
        }

    # Farewells
    if body in FAREWELLS:
        return {
            "reply": "Até mais! Se precisar, é só chamar. 👋",
            "steps": [{"node": "fast_path", "intent": "farewell"}],
        }

    # Simple acks — no response needed
    if body in ACKS:
        return {
            "reply": None,  # No reply for acks
            "steps": [{"node": "fast_path", "intent": "ack"}],
        }

    # Tool-based fast paths
    if body in {"tarefas", "listar tarefas", "minhas tarefas"}:
        return _execute_tool_fast("list_tasks", {}, state)

    if body in {"agenda", "compromissos", "meus compromissos"}:
        return _execute_tool_fast("list_appointments", {}, state)

    if body in {"resumo", "contexto"}:
        return _execute_tool_fast("preview_summary", {}, state)

    if body in {"ping"}:
        return {
            "reply": "pong 🏓",
            "steps": [{"node": "fast_path", "intent": "ping"}],
        }

    if body in {"help", "ajuda"}:
        return {
            "reply": (
                "Posso ajudar com:\n"
                "📋 *Tarefas* — criar, listar, concluir\n"
                "📅 *Agenda* — compromissos, reuniões\n"
                "⏰ *Lembretes* — avisos programados\n"
                "👤 *Contatos* — CRM invisível\n"
                "🧠 *Memória* — lembrar informações\n"
                "📊 *Relatórios* — resumos e análises\n"
                "📄 *Documentos* — propostas, contratos\n"
            ),
            "steps": [{"node": "fast_path", "intent": "help"}],
        }

    # Fallback — should not reach here (router filters first)
    return {
        "reply": None,
        "steps": [{"node": "fast_path", "intent": "unknown"}],
    }


def _execute_tool_fast(
    tool_name: str,
    params: dict[str, Any],
    state: ShadowState,
) -> dict[str, Any]:
    """Execute a single tool directly without LLM."""
    try:
        from tools import get_tool_registry, ToolContext
        from storage import Storage

        registry = get_tool_registry()
        storage = Storage()
        context = ToolContext(
            user_phone=state.get("sender_phone") or "",
            user_name=state.get("sender_name") or "",
            session_id=state.get("session_id") or "",
            chat_id=state.get("chat_id") or "",
            message_text=state.get("body") or "",
            timestamp="",
            storage=storage,
            metadata={},
        )
        result = registry.execute(tool_name, params, context)
        return {
            "reply": result.display_text or result.message,
            "steps": [{"node": "fast_path", "tool": tool_name, "success": result.success}],
        }
    except Exception as e:
        return {
            "reply": f"Erro ao executar {tool_name}: {str(e)[:100]}",
            "steps": [{"node": "fast_path", "tool": tool_name, "error": str(e)[:100]}],
        }
