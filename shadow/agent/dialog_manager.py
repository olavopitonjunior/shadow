from typing import Any


def build_reply(user_text: str, extracted: dict[str, Any]) -> str:
    intent = extracted.get("intent", "note")
    actions = extracted.get("actions", [])

    if intent == "list_tasks":
        return "Vou buscar suas tarefas pendentes."
    if intent == "list_appointments":
        return "Vou listar seus compromissos."
    if intent == "create_task":
        title = actions[0].get("title") if actions else "Nova tarefa"
        return f"Tarefa criada: {title}"
    if intent == "create_appointment":
        if actions and actions[0].get("needs_clarification"):
            return "Qual dia e horario do compromisso?"
        title = actions[0].get("title") if actions else "Compromisso"
        return f"Compromisso agendado: {title}"

    return "Anotado. Posso ajudar com tarefas ou compromissos se precisar."
