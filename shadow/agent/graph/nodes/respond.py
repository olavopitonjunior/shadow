"""
Respond node - Send ONE consolidated message via MessageBus.

Never sends per-node updates to WhatsApp (that would spam the user).
Real-time agent tracing goes to the admin dashboard via SSE instead.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from graph.state import ShadowState


def respond_node(state: ShadowState) -> dict[str, Any]:
    """Publish final reply to MessageBus for WhatsApp delivery.

    Sends a single consolidated message. Attachments (PDFs, images)
    are sent as separate messages via the gateway.
    """
    reply = state.get("reply")
    chat_id = state.get("chat_id")
    attachments = state.get("attachments", [])

    if not reply and not attachments:
        # Nothing to send (e.g., ack messages)
        return {
            "steps": [{"node": "respond", "sent": False}],
        }

    # Publish text reply via MessageBus
    if reply and chat_id:
        try:
            from bus import get_message_bus, OutboundMessage

            bus = get_message_bus()
            bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id=chat_id,
                content=reply,
            ))
        except Exception as e:
            print(f"[respond] Failed to publish message: {e}")

    # Publish attachments (PDFs, images, charts)
    for attachment in attachments:
        if chat_id:
            try:
                from bus import get_message_bus, OutboundMessage

                bus = get_message_bus()
                bus.publish_outbound(OutboundMessage(
                    channel="whatsapp",
                    chat_id=chat_id,
                    content=attachment.get("caption", ""),
                    message_type=attachment.get("type", "document"),
                    metadata=attachment,
                ))
            except Exception as e:
                print(f"[respond] Failed to publish attachment: {e}")

    # Add AI message to conversation history
    messages = []
    if reply:
        messages = [AIMessage(content=reply)]

    return {
        "messages": messages,
        "steps": [{
            "node": "respond",
            "sent": True,
            "reply_length": len(reply) if reply else 0,
            "attachments_count": len(attachments),
        }],
    }
