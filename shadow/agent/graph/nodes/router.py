"""
Three-tier routing node.

Tier 1: Fast-path regex (0ms, no LLM) → direct tool execution
Tier 2: Keyword classifier (0ms) → deterministic worker routing
Tier 3: LLM supervisor → only for ambiguous/multimodal/multi-step requests
"""

from __future__ import annotations

from typing import Any

from graph.state import ShadowState


# ── Tier 1: Exact match fast-paths (no LLM needed) ──
FAST_PATHS: set[str] = {
    "oi", "olá", "ola", "hey", "hi", "hello",
    "ping", "help", "ajuda",
    "tarefas", "listar tarefas", "minhas tarefas",
    "agenda", "compromissos", "meus compromissos",
    "resumo", "contexto",
    "ok", "obrigado", "valeu", "tchau", "sim", "não", "nao",
}

# ── Tier 2: Keyword → worker mapping ──
WORKER_KEYWORDS: dict[str, set[str]] = {
    "planner": {
        "tarefa", "task", "todo", "pendente", "concluir", "concluída",
        "compromisso", "reunião", "reuniao", "meeting", "agendar",
        "lembrete", "reminder", "lembrar",
    },
    "crm": {
        "contato", "contact", "quem é", "quem e", "telefone",
        "cliente", "fornecedor", "email", "relacionamento",
    },
    "analytics": {
        "relatório", "relatorio", "dashboard", "análise", "analise",
        "como tá", "como ta", "como está", "como esta",
        "estatísticas", "estatisticas", "métricas", "metricas",
    },
    "collector": {
        "importa", "importar", "sincroniza", "sincronizar",
        "conversas do whatsapp", "histórico de conversas",
        "historico de conversas", "grupos do whatsapp",
    },
    "docgen": {
        "proposta", "proposal", "contrato", "contract",
        "documento", "document", "pdf", "gera documento",
        "gerar proposta", "gerar contrato",
    },
}


def route_message(state: ShadowState) -> str:
    """Three-tier routing: fast-path → keyword → LLM supervisor.

    Returns the name of the next node to execute.
    """
    body = (state.get("body") or "").strip().lower()

    # ── Tier 1: Fast-path (no LLM) ──
    if body in FAST_PATHS:
        return "fast_path"

    # ── Tier 2: Keyword classifier (deterministic worker) ──
    # Check multi-word keywords first (more specific), then single-word
    # Priority order matters: collector before crm (e.g., "importa contatos")
    priority_order = ["collector", "docgen", "analytics", "planner", "crm"]
    for worker in priority_order:
        keywords = WORKER_KEYWORDS[worker]
        if any(kw in body for kw in keywords):
            return worker

    # ── Tier 3: LLM supervisor (ambiguous, multimodal, multi-step) ──
    # Also route to LLM if there's multimodal content that needs understanding
    return "supervisor_think"
