"""
ConversationSummary Tool - Generates a summary of conversations with a contact.

Phase 8C: CRM Oculto - Resumo de conversa sob demanda.
"""

import os
from typing import Any

from .base import Tool, ToolContext, ToolParameter, ToolResult


class ConversationSummaryTool(Tool):
    """Generates summary of conversations with a specific contact."""

    name = "conversation_summary"
    description = "Gera um resumo das conversas com um contato específico"
    category = "contacts"

    parameters = [
        ToolParameter(
            name="contact_name",
            type="string",
            description="Nome do contato para gerar resumo",
            required=True,
        ),
        ToolParameter(
            name="max_messages",
            type="integer",
            description="Número máximo de mensagens a considerar (padrão: 50)",
            required=False,
        ),
    ]

    def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        contact_name = params.get("contact_name", "").strip()
        max_messages = params.get("max_messages", 50)

        if not contact_name:
            return ToolResult.error("Nome do contato é obrigatório")

        storage = context.storage
        if not storage:
            return ToolResult.error("Storage não disponível")

        owner_id = context.user_phone
        if not owner_id:
            return ToolResult.error("Usuário não identificado")

        # Try to find contact
        contact = storage.find_contact_by_name(owner_id, contact_name)
        if not contact:
            # Try direct phone lookup
            contact = storage.get_contact_context(owner_id, contact_phone=contact_name)

        if not contact:
            return ToolResult.ok(
                message="Contato não encontrado",
                data={"found": False, "contact_name": contact_name},
                display_text=f"Não encontrei o contato '{contact_name}'.",
            )

        contact_phone = contact.get("contact_phone")
        contact_display_name = contact.get("contact_name") or contact_name

        if not contact_phone:
            return ToolResult.error("Telefone do contato não encontrado")

        # Get messages with contact
        messages = storage.search_conversations_with_contact(owner_id, contact_phone, limit=max_messages)

        if not messages:
            return ToolResult.ok(
                message="Nenhuma mensagem encontrada",
                data={"found": True, "message_count": 0},
                display_text=f"Não encontrei mensagens com {contact_display_name}.",
            )

        # Generate summary using Gemini
        summary = self._generate_summary(messages, contact_display_name, owner_id)

        # Get additional context
        topics = contact.get("topics") or []
        sentiment = contact.get("sentiment") or "neutral"
        last_interaction = contact.get("last_interaction", "")

        lines = [
            f"📝 *Resumo com {contact_display_name}*",
            "",
            summary,
            "",
            f"_Baseado em {len(messages)} mensagens_",
        ]

        if last_interaction:
            lines.append(f"_Última interação: {last_interaction[:10]}_")

        if topics:
            lines.append(f"_Tópicos: {', '.join(topics[:5])}_")

        return ToolResult.ok(
            message="Resumo gerado",
            data={
                "found": True,
                "contact": contact,
                "message_count": len(messages),
                "summary": summary,
            },
            display_text="\n".join(lines),
        )

    def _generate_summary(
        self,
        messages: list[dict[str, Any]],
        contact_name: str,
        owner_id: str,
    ) -> str:
        """Generate summary using Gemini (or fallback to basic summary)."""

        # Get API key
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if not gemini_key:
            # Fallback to basic summary
            return self._basic_summary(messages, contact_name)

        try:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash-lite")

            # Format messages for prompt
            formatted_messages = []
            for msg in messages[:30]:  # Limit for context window
                direction = "Você" if msg.get("is_owner") or msg.get("direction") == "outbound" else contact_name
                content = msg.get("content") or msg.get("body") or ""
                timestamp = msg.get("timestamp", "")[:10] if msg.get("timestamp") else ""

                formatted_messages.append(f"[{timestamp}] {direction}: {content[:200]}")

            messages_text = "\n".join(formatted_messages)

            prompt = f"""Você é um assistente que gera resumos de conversas.

Analise a conversa abaixo entre o usuário e {contact_name} e gere um resumo conciso em português.

O resumo deve incluir:
1. Principais assuntos discutidos
2. Decisões ou acordos feitos (se houver)
3. Tarefas ou compromissos mencionados (se houver)
4. Tom geral da conversa

Seja direto e objetivo. Máximo de 5 linhas.

CONVERSA:
{messages_text}

RESUMO:"""

            response = model.generate_content(prompt)

            if response and response.text:
                return response.text.strip()

        except Exception as e:
            print(f"[summary] Gemini error: {e}")

        # Fallback
        return self._basic_summary(messages, contact_name)

    def _basic_summary(self, messages: list[dict[str, Any]], contact_name: str) -> str:
        """Basic summary without LLM."""
        total = len(messages)

        if total == 0:
            return "Nenhuma conversa encontrada."

        # Count directions
        inbound = sum(1 for m in messages if m.get("direction") == "inbound" or not m.get("is_owner"))
        outbound = total - inbound

        # Get first and last messages
        first_msg = messages[-1] if messages else {}
        last_msg = messages[0] if messages else {}

        first_date = first_msg.get("timestamp", "")[:10] if first_msg.get("timestamp") else "N/A"
        last_date = last_msg.get("timestamp", "")[:10] if last_msg.get("timestamp") else "N/A"

        # Extract some keywords (simple approach)
        all_text = " ".join(m.get("content", "") or m.get("body", "") for m in messages[:20])
        words = all_text.lower().split()
        word_counts = {}
        stopwords = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não", "uma"}
        for word in words:
            if len(word) > 3 and word not in stopwords:
                word_counts[word] = word_counts.get(word, 0) + 1

        top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        keywords = [w[0] for w in top_words]

        lines = [
            f"Conversa com {contact_name}:",
            f"- {total} mensagens ({inbound} recebidas, {outbound} enviadas)",
            f"- Período: {first_date} a {last_date}",
        ]

        if keywords:
            lines.append(f"- Assuntos frequentes: {', '.join(keywords)}")

        return "\n".join(lines)
