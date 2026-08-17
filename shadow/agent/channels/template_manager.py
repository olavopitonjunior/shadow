"""Template manager for WhatsApp message templates.

Manages pre-approved message templates used by Meta Cloud API
for messages outside the 24-hour conversation window.
"""

from __future__ import annotations


# Pre-defined templates (body text with {{N}} placeholders)
DEFAULT_TEMPLATES = {
    "daily_summary": {
        "category": "UTILITY",
        "body_text": "Oi {{1}}! Seu resumo: {{2}}. Responda para gerenciar.",
    },
    "task_reminder": {
        "category": "UTILITY",
        "body_text": "Lembrete: {{1}} vence {{2}}. Responda para atualizar.",
    },
    "appointment_reminder": {
        "category": "UTILITY",
        "body_text": "Compromisso: {{1}} em {{2}}. Responda para confirmar/reagendar.",
    },
    "welcome_back": {
        "category": "UTILITY",
        "body_text": "Oi {{1}}! Faz tempo que nao conversamos. Tem {{2}} tarefas pendentes.",
    },
}


class TemplateManager:
    """CRUD and rendering for message templates."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def seed_defaults(self) -> int:
        """Seed default templates if they don't exist. Returns count of created templates."""
        created = 0
        for name, tmpl in DEFAULT_TEMPLATES.items():
            existing = None
            templates = self.storage.list_channel_templates()
            for t in templates:
                if t.get("template_name") == name:
                    existing = t
                    break
            if not existing:
                self.storage.create_channel_template(
                    template_name=name,
                    body_text=tmpl["body_text"],
                    category=tmpl["category"],
                )
                created += 1
        return created

    def render(self, template_name: str, params: list[str]) -> str | None:
        """Render a template by substituting parameters.

        Returns the rendered text, or None if template not found.
        """
        # Check DB first
        templates = self.storage.list_channel_templates()
        for t in templates:
            if t.get("template_name") == template_name:
                body = t.get("body_text", "")
                for i, param in enumerate(params, 1):
                    body = body.replace(f"{{{{{i}}}}}", param)
                return body

        # Fallback to defaults
        if template_name in DEFAULT_TEMPLATES:
            body = DEFAULT_TEMPLATES[template_name]["body_text"]
            for i, param in enumerate(params, 1):
                body = body.replace(f"{{{{{i}}}}}", param)
            return body

        return None

    def list_templates(self) -> list[dict]:
        """List all templates (DB + defaults)."""
        db_templates = self.storage.list_channel_templates()
        db_names = {t.get("template_name") for t in db_templates}

        # Add defaults that aren't in DB
        for name, tmpl in DEFAULT_TEMPLATES.items():
            if name not in db_names:
                db_templates.append({
                    "template_name": name,
                    "body_text": tmpl["body_text"],
                    "category": tmpl["category"],
                    "status": "default",
                    "language": "pt_BR",
                })

        return db_templates
