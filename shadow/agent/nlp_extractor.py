from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any


def extract_entities(text: str) -> dict[str, Any]:
    lower = text.lower()
    intent = _detect_intent(lower)
    actions: list[dict[str, Any]] = []

    if intent == "create_task":
        actions.append(
            {
                "type": "create_task",
                "title": _guess_title(text, 120),
            }
        )
    elif intent == "create_appointment":
        when = _parse_datetime(text)
        actions.append(
            {
                "type": "create_appointment",
                "title": _guess_title(text, 120) or "Compromisso",
                "scheduled_at": when.isoformat() if when else None,
                "needs_clarification": when is None,
            }
        )

    return {
        "intent": intent,
        "actions": actions,
    }


def _detect_intent(lower: str) -> str:
    if "tarefas" in lower or lower.startswith("tarefa"):
        return "list_tasks"
    if "agenda" in lower or "compromisso" in lower or "reunioes" in lower:
        return "list_appointments"
    if any(k in lower for k in ["reuniao", "call", "meeting", "agendar", "marcar"]):
        return "create_appointment"
    if any(k in lower for k in ["lembra", "lembrete", "preciso", "enviar", "ligar", "follow"]):
        return "create_task"
    return "note"


def _guess_title(text: str, max_len: int) -> str | None:
    trimmed = text.strip()
    if not trimmed:
        return None
    return trimmed if len(trimmed) <= max_len else f"{trimmed[:max_len]}..."


def _parse_datetime(text: str) -> datetime | None:
    now = datetime.utcnow()
    lower = text.lower()
    date = now

    if "amanha" in lower:
        date = now + timedelta(days=1)
    if "hoje" in lower:
        date = now

    match_date = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b", text)
    if match_date:
        day = int(match_date.group(1))
        month = int(match_date.group(2))
        year = int(match_date.group(3)) if match_date.group(3) else now.year
        date = datetime(year, month, day)

    match_time = re.search(r"\b(\d{1,2})(?:[:h](\d{2}))?\b", text)
    if match_time:
        hour = int(match_time.group(1))
        minute = int(match_time.group(2) or 0)
        return date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if "amanha" in lower or "hoje" in lower or match_date:
        return date
    return None
