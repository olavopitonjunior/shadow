from typing import Any


class ActionEngine:
    """Placeholder for CRUD and automation logic."""

    def __init__(self, supabase_url: str | None = None, supabase_key: str | None = None) -> None:
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key

    def execute_actions(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # MVP: just return actions without side effects.
        return actions
