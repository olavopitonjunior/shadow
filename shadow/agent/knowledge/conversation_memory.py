"""
Conversation Memory - Layer 3 of the RAG knowledge base.

Stores summarized conversation threads with embeddings for retrieval.
Populated by the Collector agent from Z-API chat history.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class ConversationMemory:
    """Semantic search over conversation summaries using LanceDB."""

    TABLE_NAME = "conversation_summaries"

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(
            Path(__file__).parent.parent / "data" / "knowledge_db"
        )
        self._db = None
        self._embedder = None

    def _get_db(self):
        if self._db is None:
            try:
                import lancedb
                self._db = lancedb.connect(self._db_path)
            except ImportError:
                raise ImportError("lancedb is required for ConversationMemory")
        return self._db

    def _embed(self, text: str) -> list[float]:
        try:
            from openai import OpenAI
            client = OpenAI()
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception:
            return [0.0] * 1536

    def store(
        self,
        summary: str,
        owner_id: str,
        contact_phone: str | None = None,
        contact_name: str | None = None,
        message_count: int = 0,
        action_items: list[str] | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> str:
        """Store a conversation summary with embedding."""
        record_id = str(uuid4())[:12]
        vector = self._embed(summary)

        record = {
            "id": record_id,
            "owner_id": owner_id,
            "contact_phone": contact_phone or "",
            "contact_name": contact_name or "",
            "summary": summary,
            "message_count": message_count,
            "action_items": "|".join(action_items or []),
            "period_start": period_start or "",
            "period_end": period_end or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "vector": vector,
        }

        db = self._get_db()
        try:
            table = db.open_table(self.TABLE_NAME)
            table.add([record])
        except Exception:
            import pyarrow as pa
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("owner_id", pa.string()),
                pa.field("contact_phone", pa.string()),
                pa.field("contact_name", pa.string()),
                pa.field("summary", pa.string()),
                pa.field("message_count", pa.int32()),
                pa.field("action_items", pa.string()),
                pa.field("period_start", pa.string()),
                pa.field("period_end", pa.string()),
                pa.field("created_at", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 1536)),
            ])
            table = db.create_table(self.TABLE_NAME, schema=schema)
            table.add([record])

        return record_id

    def search(
        self,
        query: str,
        owner_id: str,
        top_k: int = 5,
        contact_phone: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over conversation summaries."""
        query_vec = self._embed(query)

        db = self._get_db()
        try:
            table = db.open_table(self.TABLE_NAME)
        except Exception:
            return []

        search = table.search(query_vec).where(f"owner_id = '{owner_id}'")
        if contact_phone:
            search = search.where(f"contact_phone = '{contact_phone}'")

        results = search.limit(top_k).to_list()

        return [
            {
                "id": r["id"],
                "text": r["summary"],
                "contact_phone": r.get("contact_phone", ""),
                "contact_name": r.get("contact_name", ""),
                "message_count": r.get("message_count", 0),
                "action_items": r.get("action_items", "").split("|"),
                "score": r.get("_distance", 0),
            }
            for r in results
        ]
