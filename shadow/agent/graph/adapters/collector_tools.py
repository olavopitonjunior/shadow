"""
Collector-specific tools for Z-API data collection.

Provides WhatsApp data mining tools:
- sync_contacts_to_crm: Import WhatsApp contacts into Shadow CRM
- get_whatsapp_chats: List all active WhatsApp chats
- get_chat_messages: Get message history from a chat
- summarize_conversation: Summarize a conversation thread
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain_core.tools import StructuredTool


def _get_zapi_client():
    """Get or create Z-API client from environment."""
    from graph.adapters.zapi_client import ZAPIClient

    instance_id = os.getenv("ZAPI_INSTANCE_ID", "")
    token = os.getenv("ZAPI_TOKEN", "")

    if not instance_id or not token:
        return None

    return ZAPIClient(instance_id=instance_id, token=token)


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=60)
    else:
        return asyncio.run(coro)


def _sync_contacts_to_crm() -> str:
    """Import WhatsApp contacts from Z-API into Shadow CRM.

    Fetches all contacts from WhatsApp and creates/updates them in the CRM.
    """
    client = _get_zapi_client()
    if not client:
        return "Z-API não configurado. Defina ZAPI_INSTANCE_ID e ZAPI_TOKEN."

    try:
        from storage import Storage
        from tools import ToolContext, get_tool_registry, setup_default_tools

        setup_default_tools()
        registry = get_tool_registry()
        storage = Storage()
        context = ToolContext(storage=storage)

        contacts = _run_async(client.get_contacts())

        if not contacts:
            return "Nenhum contato encontrado no WhatsApp."

        created = 0
        updated = 0
        skipped = 0

        for wa_contact in contacts[:100]:  # Limit to 100 per sync
            phone = wa_contact.get("id", "").replace("@c.us", "")
            name = wa_contact.get("name") or wa_contact.get("notify") or ""

            if not phone or len(phone) < 8:
                skipped += 1
                continue

            # Check if contact exists
            existing = registry.execute("get_contact", {"query": phone}, context)
            if existing and existing.data:
                # Update name if we have a better one
                if name and not existing.data.get("name"):
                    registry.execute("update_contact", {
                        "phone": phone,
                        "name": name,
                    }, context)
                    updated += 1
                else:
                    skipped += 1
            else:
                # Create new contact
                registry.execute("create_contact", {
                    "name": name or phone,
                    "phone": phone,
                }, context)
                created += 1

        return (
            f"Sincronização concluída!\n"
            f"- {created} contatos criados\n"
            f"- {updated} contatos atualizados\n"
            f"- {skipped} pulados (já existentes ou inválidos)\n"
            f"- {len(contacts)} total no WhatsApp"
        )
    except Exception as e:
        return f"Erro na sincronização: {e}"


def _get_whatsapp_chats() -> str:
    """List all active WhatsApp chats via Z-API."""
    client = _get_zapi_client()
    if not client:
        return "Z-API não configurado. Defina ZAPI_INSTANCE_ID e ZAPI_TOKEN."

    try:
        chats = _run_async(client.get_chats())
        if not chats:
            return "Nenhum chat encontrado."

        lines = [f"Total de chats: {len(chats)}\n"]
        for chat in chats[:20]:  # Show first 20
            name = chat.get("name") or chat.get("id", "?")
            msg_count = chat.get("unreadCount", 0)
            is_group = "@g.us" in str(chat.get("id", ""))
            tipo = "Grupo" if is_group else "Direto"
            lines.append(f"- [{tipo}] {name} (não lidas: {msg_count})")

        if len(chats) > 20:
            lines.append(f"\n... e mais {len(chats) - 20} chats")

        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao buscar chats: {e}"


def _get_chat_messages(phone: str, amount: int = 30) -> str:
    """Get recent messages from a specific WhatsApp chat.

    Args:
        phone: Phone number or chat ID
        amount: Number of messages to retrieve (max 100)
    """
    client = _get_zapi_client()
    if not client:
        return "Z-API não configurado."

    amount = min(amount, 100)

    try:
        messages = _run_async(client.get_messages(phone, amount))
        if not messages:
            return f"Nenhuma mensagem encontrada para {phone}."

        lines = [f"Últimas {len(messages)} mensagens de {phone}:\n"]
        for msg in messages[:amount]:
            sender = "Você" if msg.get("fromMe") else msg.get("senderName", "?")
            text = msg.get("body") or msg.get("caption") or "[mídia]"
            text = text[:150]  # Truncate long messages
            lines.append(f"- {sender}: {text}")

        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao buscar mensagens: {e}"


def _summarize_conversation(phone: str, amount: int = 50) -> str:
    """Summarize a WhatsApp conversation thread.

    Fetches messages and uses Gemini Flash for cost-effective summarization.

    Args:
        phone: Phone number or chat ID
        amount: Number of messages to analyze
    """
    client = _get_zapi_client()
    if not client:
        return "Z-API não configurado."

    try:
        messages = _run_async(client.get_messages(phone, min(amount, 100)))
        if not messages:
            return f"Nenhuma mensagem para resumir de {phone}."

        # Build conversation text
        conv_lines = []
        for msg in messages:
            sender = "Owner" if msg.get("fromMe") else msg.get("senderName", "Contact")
            text = msg.get("body") or msg.get("caption") or ""
            if text:
                conv_lines.append(f"{sender}: {text}")

        if not conv_lines:
            return "Conversa sem mensagens de texto."

        conversation_text = "\n".join(conv_lines[-50:])  # Last 50 messages

        # Summarize with LLM (prefer Gemini for cost)
        try:
            from providers import get_provider
            provider = get_provider(provider_name="gemini")
        except Exception:
            from providers import get_provider
            provider = get_provider()

        response = provider.chat(
            messages=[{"role": "user", "content": (
                f"Resuma esta conversa do WhatsApp em português. "
                f"Inclua: tópicos principais, decisões tomadas, ações pendentes.\n\n"
                f"Conversa:\n{conversation_text}"
            )}],
            max_tokens=500,
            temperature=0.3,
        )

        return response.content or "Não foi possível gerar resumo."
    except Exception as e:
        return f"Erro ao resumir conversa: {e}"


def get_collector_tools() -> list[StructuredTool]:
    """Get Collector-specific LangChain tools."""
    return [
        StructuredTool.from_function(
            func=_sync_contacts_to_crm,
            name="sync_contacts_to_crm",
            description="Import all WhatsApp contacts into Shadow CRM. Creates new contacts and updates existing ones.",
        ),
        StructuredTool.from_function(
            func=_get_whatsapp_chats,
            name="get_whatsapp_chats",
            description="List all active WhatsApp chats with unread message counts.",
        ),
        StructuredTool.from_function(
            func=_get_chat_messages,
            name="get_chat_messages",
            description="Get recent messages from a specific WhatsApp chat. Args: phone (str), amount (int, default 30).",
        ),
        StructuredTool.from_function(
            func=_summarize_conversation,
            name="summarize_conversation",
            description="Summarize a WhatsApp conversation. Fetches messages and generates a summary with topics, decisions, and pending actions. Args: phone (str), amount (int, default 50).",
        ),
    ]
