"""
Synthesize node - Merge worker results and check quality.

synthesize_node: Combines results from one or more workers into a reply.
check_quality: Decides whether to respond, re-delegate, or fallback.
"""

from __future__ import annotations

from typing import Any

from graph.state import ShadowState

MAX_RETRIES = 2


def synthesize_node(state: ShadowState) -> dict[str, Any]:
    """Merge worker results into a consolidated reply.

    Handles single and multi-worker results.
    Prioritizes by worker status (ok > partial > error).
    """
    results = state.get("worker_results", [])

    if not results:
        return {
            "reply": "Não consegui processar sua solicitação. Tente novamente.",
            "steps": [{"node": "synthesize", "results_count": 0}],
        }

    # Single worker — use its display_text directly
    if len(results) == 1:
        r = results[0]
        reply = r.get("display_text") or r.get("data", {}).get("message", "")
        return {
            "reply": reply,
            "steps": [{"node": "synthesize", "worker": r.get("worker_name"), "status": r.get("status")}],
        }

    # Multiple workers — combine display texts
    ok_results = [r for r in results if r.get("status") == "ok"]
    partial_results = [r for r in results if r.get("status") == "partial"]
    error_results = [r for r in results if r.get("status") == "error"]

    parts: list[str] = []
    for r in ok_results + partial_results:
        text = r.get("display_text", "")
        if text:
            parts.append(text)

    if error_results and not parts:
        # All workers failed
        return {
            "reply": "Houve um erro ao processar. Tente novamente em alguns instantes.",
            "steps": [{"node": "synthesize", "all_errors": True}],
        }

    reply = "\n\n".join(parts) if parts else "Processado com sucesso."

    return {
        "reply": reply,
        "steps": [{
            "node": "synthesize",
            "ok": len(ok_results),
            "partial": len(partial_results),
            "errors": len(error_results),
        }],
    }


def check_quality(state: ShadowState) -> str:
    """Decide whether to respond, re-delegate, or give up.

    Returns the name of the next node:
    - "respond" — result is good, send to user
    - "supervisor_think" — re-delegate (retry)
    - "fallback_respond" — max retries exhausted
    """
    results = state.get("worker_results", [])
    retry_count = state.get("retry_count", 0)

    # No results or all errors — try again
    if not results or all(r.get("status") == "error" for r in results):
        if retry_count < MAX_RETRIES:
            return "supervisor_think"
        return "respond"  # Give up gracefully (synthesize already set error reply)

    # At least one ok/partial result — proceed to respond
    return "respond"
