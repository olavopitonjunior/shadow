"""
ContactSummarizer - Generates summaries of conversations with contacts.

Phase 3: Automatic summarization using Gemini LLM.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage import SqliteStorage, SupabaseStorage


# Gemini summarization prompt
SUMMARY_PROMPT = """
Analise as últimas mensagens trocadas com {contact_name} e gere um resumo estruturado.

Mensagens (mais recentes primeiro):
{messages}

Retorne APENAS um JSON válido no seguinte formato (sem markdown):
{{
    "summary": "Resumo de 2-3 frases descrevendo o relacionamento e interações recentes",
    "topics": ["tópico1", "tópico2", "tópico3"],
    "sentiment": "positive|neutral|negative",
    "key_facts": ["fato importante 1", "fato importante 2"]
}}

Regras:
- summary deve ser conciso e informativo
- topics devem ser os principais assuntos discutidos (máximo 5)
- sentiment deve refletir o tom geral das conversas
- key_facts são informações importantes sobre o contato (máximo 3)
- Responda em português
"""


class ContactSummarizer:
    """
    Generates conversation summaries using Gemini.

    Features:
    - Automatic trigger after N messages
    - Topic extraction
    - Sentiment analysis
    - Key facts identification
    """

    def __init__(self, api_key: str, update_interval: int = 10):
        """
        Initialize summarizer.

        Args:
            api_key: Gemini API key
            update_interval: Messages between summary updates (default: 10)
        """
        self.api_key = api_key
        self.update_interval = update_interval
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel("gemini-1.5-flash")
            except ImportError:
                raise ImportError("google-generativeai package required for summarization")
        return self._client

    def should_update(
        self,
        storage: SqliteStorage | SupabaseStorage,
        owner_id: str,
        contact_phone: str,
    ) -> bool:
        """
        Check if summary should be updated.

        Returns True if message count since last summary >= interval.
        """
        return storage.should_update_summary(
            owner_id=owner_id,
            contact_phone=contact_phone,
            interval=self.update_interval,
        )

    async def generate_summary(
        self,
        storage: SqliteStorage | SupabaseStorage,
        owner_id: str,
        contact_phone: str,
        contact_name: str | None = None,
        message_limit: int = 20,
    ) -> dict[str, Any] | None:
        """
        Generate summary for a contact's conversation history.

        Args:
            storage: Storage instance
            owner_id: Owner's phone (E164)
            contact_phone: Contact's phone (E164)
            contact_name: Contact's display name
            message_limit: Number of messages to analyze

        Returns:
            Summary dict with summary, topics, sentiment, key_facts
            or None if generation fails
        """
        # Get recent messages
        messages = storage.search_conversations_with_contact(
            owner_id=owner_id,
            contact_identifier=contact_phone,
            limit=message_limit,
        )

        if not messages or len(messages) < 3:
            return None  # Not enough data for meaningful summary

        # Format messages for prompt
        formatted = []
        for msg in messages:
            direction = "Eu" if msg.get("direction") == "outbound" else (contact_name or "Contato")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")[:10]
            formatted.append(f"[{timestamp}] {direction}: {content}")

        messages_text = "\n".join(formatted)
        display_name = contact_name or contact_phone

        prompt = SUMMARY_PROMPT.format(
            contact_name=display_name,
            messages=messages_text,
        )

        try:
            import time as _time
            client = self._get_client()
            _t0 = _time.monotonic()
            response = await asyncio.to_thread(
                client.generate_content,
                prompt,
            )
            _latency = int((_time.monotonic() - _t0) * 1000)

            # Track Gemini usage
            try:
                from usage_tracker import get_tracker, UsageRecord
                meta = getattr(response, "usage_metadata", None)
                get_tracker().record(UsageRecord(
                    provider="google",
                    model=getattr(client, "model_name", "gemini-2.5-flash-lite"),
                    input_tokens=getattr(meta, "prompt_token_count", 0) if meta else 0,
                    output_tokens=getattr(meta, "candidates_token_count", 0) if meta else 0,
                    operation="summarization",
                    latency_ms=_latency,
                ))
            except Exception:
                pass

            # Parse JSON response
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith("```"):
                text = re.sub(r"```(?:json)?\n?", "", text)
                text = text.strip()

            result = json.loads(text)
            return {
                "summary": result.get("summary", ""),
                "topics": result.get("topics", []),
                "sentiment": result.get("sentiment", "neutral"),
                "key_facts": result.get("key_facts", []),
            }

        except json.JSONDecodeError:
            # Try to extract partial data
            return self._extract_fallback(response.text if 'response' in dir() else "")
        except Exception as e:
            print(f"[summarizer] Error generating summary: {e}")
            return None

    def _extract_fallback(self, text: str) -> dict[str, Any] | None:
        """Extract partial data from malformed response."""
        result = {
            "summary": "",
            "topics": [],
            "sentiment": "neutral",
            "key_facts": [],
        }

        # Try to find summary
        summary_match = re.search(r'"summary":\s*"([^"]+)"', text)
        if summary_match:
            result["summary"] = summary_match.group(1)

        # Try to find topics
        topics_match = re.search(r'"topics":\s*\[([^\]]+)\]', text)
        if topics_match:
            topics = re.findall(r'"([^"]+)"', topics_match.group(1))
            result["topics"] = topics[:5]

        # Try to find sentiment
        sentiment_match = re.search(r'"sentiment":\s*"(positive|neutral|negative)"', text)
        if sentiment_match:
            result["sentiment"] = sentiment_match.group(1)

        if result["summary"]:
            return result
        return None

    async def update_if_needed(
        self,
        storage: SqliteStorage | SupabaseStorage,
        owner_id: str,
        contact_phone: str,
        contact_name: str | None = None,
    ) -> bool:
        """
        Check and update summary if needed.

        Returns True if summary was updated.
        """
        if not self.should_update(storage, owner_id, contact_phone):
            return False

        summary_data = await self.generate_summary(
            storage=storage,
            owner_id=owner_id,
            contact_phone=contact_phone,
            contact_name=contact_name,
        )

        if summary_data:
            storage.update_contact_summary(
                owner_id=owner_id,
                contact_phone=contact_phone,
                summary=summary_data.get("summary"),
                topics=summary_data.get("topics"),
                sentiment=summary_data.get("sentiment"),
            )
            return True

        return False

    def update_if_needed_sync(
        self,
        storage: SqliteStorage | SupabaseStorage,
        owner_id: str,
        contact_phone: str,
        contact_name: str | None = None,
    ) -> bool:
        """
        Synchronous wrapper for update_if_needed.

        Use this from synchronous code.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.update_if_needed(storage, owner_id, contact_phone, contact_name)
            )
            loop.close()
            return result
        except Exception as e:
            print(f"[summarizer] Sync update failed: {e}")
            return False


# Global instance (lazy loaded)
_summarizer: ContactSummarizer | None = None


def get_summarizer(api_key: str | None = None) -> ContactSummarizer | None:
    """Get or create global summarizer instance."""
    global _summarizer
    if _summarizer is None and api_key:
        _summarizer = ContactSummarizer(api_key)
    return _summarizer


def maybe_update_contact_summary(
    storage: SqliteStorage | SupabaseStorage,
    owner_id: str,
    contact_phone: str,
    contact_name: str | None,
    api_key: str | None,
) -> bool:
    """
    Convenience function to check and update summary.

    Called from message_handler after processing contact messages.
    """
    if not api_key:
        return False

    summarizer = get_summarizer(api_key)
    if not summarizer:
        return False

    return summarizer.update_if_needed_sync(
        storage=storage,
        owner_id=owner_id,
        contact_phone=contact_phone,
        contact_name=contact_name,
    )
