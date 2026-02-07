"""
Suggestion Formatter - Message formatting for suggestions.

This module formats suggestions for display in WhatsApp messages.
"""

from .types import (
    Suggestion,
    SuggestionType,
    SuggestionPriority,
    SuggestionBatch,
)


# Emoji mapping for suggestion types
TYPE_EMOJI = {
    SuggestionType.CREATE_TASK: "📋",
    SuggestionType.CREATE_APPOINTMENT: "📅",
    SuggestionType.CREATE_CONTACT: "👤",
    SuggestionType.UPDATE_CONTACT: "✏️",
    SuggestionType.CONVERSATION_SUMMARY: "📝",
}

# Type labels in Portuguese
TYPE_LABELS = {
    SuggestionType.CREATE_TASK: "Tarefa",
    SuggestionType.CREATE_APPOINTMENT: "Compromisso",
    SuggestionType.CREATE_CONTACT: "Novo Contato",
    SuggestionType.UPDATE_CONTACT: "Atualizar Contato",
    SuggestionType.CONVERSATION_SUMMARY: "Resumo",
}


def format_single_suggestion(suggestion: Suggestion, use_emojis: bool = True) -> str:
    """
    Format a single suggestion for display.

    Args:
        suggestion: Suggestion to format
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    emoji = TYPE_EMOJI.get(suggestion.suggestion_type, "💡") if use_emojis else ""
    type_label = TYPE_LABELS.get(suggestion.suggestion_type, "Sugestão")

    lines = ["[Shadow] Sugestão detectada:", ""]

    # Main suggestion line
    if emoji:
        lines.append(f"{emoji} {type_label}: \"{suggestion.title}\"")
    else:
        lines.append(f"{type_label}: \"{suggestion.title}\"")

    # Additional details from body
    if suggestion.body:
        for line in suggestion.body.split("\n")[:3]:  # Max 3 lines of details
            if line.strip():
                lines.append(line.strip())

    # Confidence indicator
    confidence_pct = int(suggestion.confidence * 100)
    if use_emojis:
        lines.append(f"📊 Confiança: {confidence_pct}%")
    else:
        lines.append(f"Confiança: {confidence_pct}%")

    # Response options
    lines.append("")
    lines.append("Responda:")

    if suggestion.suggestion_type == SuggestionType.CONVERSATION_SUMMARY:
        lines.append("  [1] Guardar resumo")
        lines.append("  [2] Ignorar")
    else:
        lines.append("  [1] Criar")
        lines.append("  [2] Editar antes")
        lines.append("  [3] Ignorar")

    return "\n".join(lines)


def format_suggestion_batch(batch: SuggestionBatch, use_emojis: bool = True) -> str:
    """
    Format a batch of suggestions for display.

    Args:
        batch: Batch of suggestions
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    count = len(batch.suggestions)
    lines = [f"[Shadow] {count} sugestões pendentes:", ""]

    for i, suggestion in enumerate(batch.suggestions, 1):
        emoji = TYPE_EMOJI.get(suggestion.suggestion_type, "💡") if use_emojis else ""
        type_label = TYPE_LABELS.get(suggestion.suggestion_type, "Sugestão")
        confidence_pct = int(suggestion.confidence * 100)

        title = suggestion.title[:50]
        if len(suggestion.title) > 50:
            title += "..."

        if emoji:
            lines.append(f"{i}. {emoji} {type_label}: \"{title}\" ({confidence_pct}%)")
        else:
            lines.append(f"{i}. {type_label}: \"{title}\" ({confidence_pct}%)")

    lines.append("")
    lines.append("Responda com números para aceitar (ex: \"1,3\")")
    lines.append("Ou \"ignorar\" para descartar todas.")

    return "\n".join(lines)


def format_suggestion_list(suggestions: list[Suggestion], use_emojis: bool = True) -> str:
    """
    Format a list of suggestions for display (used by list_suggestions tool).

    Args:
        suggestions: List of suggestions
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    if not suggestions:
        return "Nenhuma sugestão pendente."

    lines = [f"Sugestões pendentes ({len(suggestions)}):", ""]

    for i, suggestion in enumerate(suggestions, 1):
        emoji = TYPE_EMOJI.get(suggestion.suggestion_type, "💡") if use_emojis else ""
        type_label = TYPE_LABELS.get(suggestion.suggestion_type, "Sugestão")
        confidence_pct = int(suggestion.confidence * 100)
        status = suggestion.status.value if hasattr(suggestion.status, "value") else suggestion.status

        title = suggestion.title[:40]
        if len(suggestion.title) > 40:
            title += "..."

        if emoji:
            lines.append(f"{i}. {emoji} {title}")
        else:
            lines.append(f"{i}. [{type_label}] {title}")

        lines.append(f"   Confiança: {confidence_pct}% | Status: {status}")

    return "\n".join(lines)


def format_acceptance_confirmation(suggestion: Suggestion, result: str, use_emojis: bool = True) -> str:
    """
    Format confirmation message after accepting a suggestion.

    Args:
        suggestion: Accepted suggestion
        result: Result message from tool execution
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    emoji = "✅" if use_emojis else ""
    type_label = TYPE_LABELS.get(suggestion.suggestion_type, "Sugestão")

    if emoji:
        return f"{emoji} {type_label} criado(a)!\n{result}"
    return f"{type_label} criado(a)!\n{result}"


def format_rejection_confirmation(suggestion: Suggestion, use_emojis: bool = True) -> str:
    """
    Format confirmation message after rejecting a suggestion.

    Args:
        suggestion: Rejected suggestion
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    emoji = "🚫" if use_emojis else ""

    if emoji:
        return f"{emoji} Sugestão ignorada."
    return "Sugestão ignorada."


def format_batch_acceptance(
    accepted: list[Suggestion],
    rejected: list[Suggestion],
    use_emojis: bool = True,
) -> str:
    """
    Format confirmation after batch acceptance/rejection.

    Args:
        accepted: List of accepted suggestions
        rejected: List of rejected suggestions
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    lines = []

    if accepted:
        emoji = "✅" if use_emojis else ""
        lines.append(f"{emoji} {len(accepted)} sugestão(ões) aceita(s):")
        for s in accepted[:3]:  # Show max 3
            lines.append(f"  - {s.title[:40]}")
        if len(accepted) > 3:
            lines.append(f"  ... e mais {len(accepted) - 3}")

    if rejected:
        emoji = "🚫" if use_emojis else ""
        lines.append(f"{emoji} {len(rejected)} sugestão(ões) ignorada(s)")

    return "\n".join(lines) if lines else "Processado."


def format_edit_prompt(suggestion: Suggestion, use_emojis: bool = True) -> str:
    """
    Format prompt asking for edits before creating.

    Args:
        suggestion: Suggestion to edit
        use_emojis: Whether to include emojis

    Returns:
        Formatted message string
    """
    type_label = TYPE_LABELS.get(suggestion.suggestion_type, "item")
    emoji = "✏️" if use_emojis else ""

    lines = [
        f"{emoji} Editando {type_label.lower()}:",
        "",
        f"Título atual: \"{suggestion.title}\"",
        "",
        "Envie o texto corrigido ou \"cancelar\" para desistir.",
    ]

    # Show current data
    data = suggestion.suggestion_data
    if data.get("due_date"):
        lines.insert(3, f"Data: {data['due_date']}")
    if data.get("scheduled_at"):
        lines.insert(3, f"Horário: {data['scheduled_at']}")

    return "\n".join(lines)
