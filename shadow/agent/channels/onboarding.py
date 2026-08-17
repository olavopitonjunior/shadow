"""Onboarding flow for new channel users.

Sends welcome messages and guides new users through initial setup.
"""

from __future__ import annotations

from channels.base import ChannelAdapter, SendResult


WELCOME_MESSAGE = """Oi! Eu sou o Shadow, seu assistente pessoal.

Posso te ajudar com:
- Criar e gerenciar tarefas
- Agendar compromissos e lembretes
- Lembrar informacoes sobre seus contatos
- Resumo diario da sua agenda

Pode comecar me mandando uma mensagem como:
"Criar tarefa: comprar leite"
"Agendar reuniao amanha as 10h"
"Lembrar de ligar pro dentista sexta"

Como posso te ajudar?"""


async def handle_new_user(
    phone: str,
    display_name: str | None,
    adapter: ChannelAdapter,
    storage=None,
) -> SendResult:
    """Send welcome message to a new user and update status to active.

    Args:
        phone: E.164 phone number
        display_name: User's display name (from WhatsApp profile)
        adapter: Channel adapter to send message through
        storage: Storage instance to update user status
    """
    # Send welcome message
    result = await adapter.send_text(phone, WELCOME_MESSAGE)

    # Mark user as active after welcome
    if storage and hasattr(storage, "update_channel_user"):
        storage.update_channel_user(phone, status="active")

    # Seed default categories for new user
    if storage and hasattr(storage, "seed_default_categories"):
        try:
            storage.seed_default_categories(phone)
        except Exception:
            pass  # Non-critical

    # Ensure user settings exist
    if storage and hasattr(storage, "ensure_user_settings"):
        try:
            storage.ensure_user_settings(phone)
        except Exception:
            pass  # Non-critical

    return result
