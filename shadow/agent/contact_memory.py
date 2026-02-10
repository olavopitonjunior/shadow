"""
ContactMemory - Semantic memory for contacts using LanceDB.

Phase 6: Vector-based semantic search for contact interactions.
Inspired by OpenClaw's memory-lancedb implementation.

Features:
- Store memories with embeddings (OpenAI text-embedding-3-small)
- Semantic similarity search (L2 distance)
- Auto-capture of preferences, facts, decisions
- Category-based organization
- GDPR-compliant forget functionality
- Memory promotion based on feedback/usage (Phase 5 Learning)
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from storage import SqliteStorage, SupabaseStorage

# Memory categories
CATEGORIES = ["preference", "fact", "decision", "entity", "interaction"]

# Auto-capture trigger patterns (Portuguese)
MEMORY_TRIGGERS = {
    "preference": [
        r"(?:prefir[oa]|gost[oa]|quer[oa]|precis[oa])\s+",
        r"(?:sempre|nunca|importante|essencial)\s+",
        r"(?:não\s+gosto|detesto|odeio)\s+",
    ],
    "decision": [
        r"(?:decidimos|vamos\s+usar|escolhemos|optamos)\s+",
        r"(?:fechado|combinado|acordado|definido)\s*[!.]?",
        r"(?:então\s+)?(?:fica|ficou)\s+(?:assim|decidido)",
    ],
    "fact": [
        r"[\w.-]+@[\w.-]+\.\w+",  # Email
        r"\+?\d{10,15}",  # Phone number
        r"(?:meu|minha|nosso|nossa)\s+(?:endereço|email|telefone)",
        r"(?:trabalho|moro)\s+(?:em|na|no)\s+",
    ],
    "entity": [
        r"(?:empresa|firma|companhia|organização)\s+",
        r"(?:projeto|contrato|proposta)\s+",
    ],
}


class ContactMemory:
    """
    Semantic memory storage using LanceDB and OpenAI embeddings.

    Provides:
    - store(): Save memory with vector embedding
    - recall(): Semantic similarity search
    - forget(): Remove memory (GDPR compliant)
    - auto_capture(): Detect capturable info from messages
    """

    def __init__(
        self,
        db_path: str | None = None,
        openai_api_key: str | None = None,
        embedding_model: str = "text-embedding-3-small",
    ):
        """
        Initialize ContactMemory.

        Args:
            db_path: Path to LanceDB database directory
            openai_api_key: OpenAI API key for embeddings
            embedding_model: OpenAI embedding model (default: text-embedding-3-small)
        """
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "lancedb"
        )
        self.openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.embedding_model = embedding_model
        self._db = None
        self._table = None
        self._openai = None

    def _get_db(self):
        """Lazy load LanceDB connection."""
        if self._db is None:
            try:
                import lancedb
                Path(self.db_path).mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
            except ImportError:
                raise ImportError("lancedb package required: pip install lancedb")
        return self._db

    def _get_table(self):
        """Get or create memories table."""
        if self._table is None:
            db = self._get_db()
            table_name = "contact_memories"

            if table_name in db.table_names():
                self._table = db.open_table(table_name)
            else:
                # Create with schema
                import pyarrow as pa
                schema = pa.schema([
                    pa.field("id", pa.string()),
                    pa.field("owner_id", pa.string()),
                    pa.field("contact_phone", pa.string()),
                    pa.field("text", pa.string()),
                    pa.field("category", pa.string()),
                    pa.field("importance", pa.float32()),
                    pa.field("created_at", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), 1536)),  # text-embedding-3-small dimension
                ])
                self._table = db.create_table(table_name, schema=schema)

        return self._table

    def _get_openai(self):
        """Lazy load OpenAI client."""
        if self._openai is None:
            if not self.openai_key:
                raise ValueError("OpenAI API key required for embeddings")
            try:
                from openai import OpenAI
                self._openai = OpenAI(api_key=self.openai_key)
            except ImportError:
                raise ImportError("openai package required: pip install openai")
        return self._openai

    def _embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        import time as _time
        client = self._get_openai()
        _t0 = _time.monotonic()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        _latency = int((_time.monotonic() - _t0) * 1000)

        # Track OpenAI usage
        try:
            from usage_tracker import get_tracker, UsageRecord
            usage = getattr(response, "usage", None)
            get_tracker().record(UsageRecord(
                provider="openai",
                model=self.embedding_model,
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=0,
                operation="embedding",
                latency_ms=_latency,
            ))
        except Exception:
            pass

        return response.data[0].embedding

    def store(
        self,
        owner_id: str,
        text: str,
        contact_phone: str | None = None,
        category: str = "interaction",
        importance: float = 0.5,
    ) -> str:
        """
        Store a memory with vector embedding.

        Args:
            owner_id: Owner's phone (E164)
            text: Memory text content
            contact_phone: Related contact phone (optional)
            category: Memory category (preference, fact, decision, entity, interaction)
            importance: Importance score 0-1

        Returns:
            Memory ID
        """
        # Validate category
        if category not in CATEGORIES:
            category = "interaction"

        # Check for duplicates (similarity threshold 0.95)
        existing = self.recall(owner_id, text, threshold=0.95, limit=1)
        if existing:
            return existing[0]["id"]  # Already stored

        # Generate embedding
        vector = self._embed(text)

        # Create entry
        entry = {
            "id": str(uuid4()),
            "owner_id": owner_id,
            "contact_phone": contact_phone or "",
            "text": text,
            "category": category,
            "importance": importance,
            "created_at": datetime.utcnow().isoformat(),
            "vector": vector,
        }

        # Store in LanceDB
        table = self._get_table()
        table.add([entry])

        return entry["id"]

    def recall(
        self,
        owner_id: str,
        query: str,
        threshold: float = 0.5,
        limit: int = 5,
        contact_phone: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search for memories.

        Args:
            owner_id: Owner's phone (E164)
            query: Search query text
            threshold: Minimum similarity score (0-1)
            limit: Maximum results to return
            contact_phone: Filter by contact (optional)
            category: Filter by category (optional)

        Returns:
            List of matching memories with scores
        """
        try:
            table = self._get_table()
        except Exception:
            return []  # Table doesn't exist yet

        # Generate query embedding
        query_vector = self._embed(query)

        # Search with LanceDB
        results = table.search(query_vector).limit(limit * 3).to_list()

        # Filter and score results
        filtered = []
        for r in results:
            # Filter by owner
            if r.get("owner_id") != owner_id:
                continue

            # Filter by contact if specified
            if contact_phone and r.get("contact_phone") != contact_phone:
                continue

            # Filter by category if specified
            if category and r.get("category") != category:
                continue

            # Convert L2 distance to similarity score
            distance = r.get("_distance", 1.0)
            score = 1 / (1 + distance)

            if score >= threshold:
                memory = {
                    "id": r["id"],
                    "text": r["text"],
                    "category": r["category"],
                    "importance": r["importance"],
                    "contact_phone": r["contact_phone"],
                    "created_at": r["created_at"],
                    "score": score,
                }
                filtered.append(memory)

        # Sort by score descending
        filtered.sort(key=lambda x: -x["score"])

        return filtered[:limit]

    def forget(self, memory_id: str) -> bool:
        """
        Remove a memory by ID (GDPR compliant).

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            table = self._get_table()
            table.delete(f"id = '{memory_id}'")
            return True
        except Exception:
            return False

    def forget_contact(self, owner_id: str, contact_phone: str) -> int:
        """
        Remove all memories about a contact (GDPR compliant).

        Args:
            owner_id: Owner's phone (E164)
            contact_phone: Contact phone to forget

        Returns:
            Number of memories deleted
        """
        try:
            table = self._get_table()
            # Count before
            results = table.search([0] * 1536).limit(10000).to_list()
            before = len([r for r in results if r.get("owner_id") == owner_id and r.get("contact_phone") == contact_phone])

            # Delete
            table.delete(f"owner_id = '{owner_id}' AND contact_phone = '{contact_phone}'")

            return before
        except Exception:
            return 0

    # ============== Memory Promotion (Learning System) ==============

    def update_importance(self, memory_id: str, new_importance: float) -> bool:
        """
        Update the importance score of a memory.

        Args:
            memory_id: ID of memory to update
            new_importance: New importance score (0-1)

        Returns:
            True if updated, False if not found
        """
        try:
            new_importance = max(0.0, min(1.0, new_importance))
            table = self._get_table()
            # LanceDB doesn't have native update, need to delete and re-add
            results = table.search([0] * 1536).limit(10000).to_list()
            for r in results:
                if r.get("id") == memory_id:
                    # Create updated entry
                    updated = {
                        "id": r["id"],
                        "owner_id": r["owner_id"],
                        "contact_phone": r["contact_phone"],
                        "text": r["text"],
                        "category": r["category"],
                        "importance": new_importance,
                        "created_at": r["created_at"],
                        "vector": r["vector"],
                    }
                    # Delete old and add new
                    table.delete(f"id = '{memory_id}'")
                    table.add([updated])
                    return True
            return False
        except Exception as e:
            print(f"[contact_memory] Error updating importance: {e}")
            return False

    def promote_memory(
        self,
        memory_id: str,
        boost: float = 0.1,
        max_importance: float = 0.95,
    ) -> float | None:
        """
        Promote a memory by increasing its importance.

        Called when:
        - User gives positive feedback on response using this memory
        - Memory is accessed multiple times
        - User explicitly confirms the memory is useful

        Args:
            memory_id: ID of memory to promote
            boost: How much to increase importance
            max_importance: Maximum importance allowed

        Returns:
            New importance score, or None if not found
        """
        try:
            table = self._get_table()
            results = table.search([0] * 1536).limit(10000).to_list()
            for r in results:
                if r.get("id") == memory_id:
                    current = r.get("importance", 0.5)
                    new_importance = min(current + boost, max_importance)
                    self.update_importance(memory_id, new_importance)
                    print(f"[contact_memory] Promoted memory {memory_id}: {current:.2f} -> {new_importance:.2f}")
                    return new_importance
            return None
        except Exception as e:
            print(f"[contact_memory] Error promoting memory: {e}")
            return None

    def demote_memory(
        self,
        memory_id: str,
        penalty: float = 0.1,
        min_importance: float = 0.1,
    ) -> float | None:
        """
        Demote a memory by decreasing its importance.

        Called when:
        - User gives negative feedback
        - User corrects information from this memory

        Args:
            memory_id: ID of memory to demote
            penalty: How much to decrease importance
            min_importance: Minimum importance allowed

        Returns:
            New importance score, or None if not found
        """
        try:
            table = self._get_table()
            results = table.search([0] * 1536).limit(10000).to_list()
            for r in results:
                if r.get("id") == memory_id:
                    current = r.get("importance", 0.5)
                    new_importance = max(current - penalty, min_importance)
                    self.update_importance(memory_id, new_importance)
                    print(f"[contact_memory] Demoted memory {memory_id}: {current:.2f} -> {new_importance:.2f}")
                    return new_importance
            return None
        except Exception as e:
            print(f"[contact_memory] Error demoting memory: {e}")
            return None

    def get_important_memories(
        self,
        owner_id: str,
        min_importance: float = 0.7,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get high-importance memories (promoted/confirmed by user).

        These are memories that have been validated through:
        - Positive feedback
        - Repeated usage
        - Explicit confirmation

        Args:
            owner_id: Owner's phone (E164)
            min_importance: Minimum importance threshold
            limit: Maximum results

        Returns:
            List of important memories
        """
        memories = self.list_memories(owner_id, limit=limit * 3)
        important = [m for m in memories if m.get("importance", 0.5) >= min_importance]
        important.sort(key=lambda x: -x.get("importance", 0.5))
        return important[:limit]

    def list_memories(
        self,
        owner_id: str,
        contact_phone: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List memories without semantic search.

        Args:
            owner_id: Owner's phone (E164)
            contact_phone: Filter by contact (optional)
            category: Filter by category (optional)
            limit: Maximum results

        Returns:
            List of memories
        """
        try:
            table = self._get_table()
            # Use a neutral vector to get all results
            results = table.search([0] * 1536).limit(limit * 3).to_list()

            filtered = []
            for r in results:
                if r.get("owner_id") != owner_id:
                    continue
                if contact_phone and r.get("contact_phone") != contact_phone:
                    continue
                if category and r.get("category") != category:
                    continue

                filtered.append({
                    "id": r["id"],
                    "text": r["text"],
                    "category": r["category"],
                    "importance": r["importance"],
                    "contact_phone": r["contact_phone"],
                    "created_at": r["created_at"],
                })

            # Sort by created_at descending
            filtered.sort(key=lambda x: x["created_at"], reverse=True)
            return filtered[:limit]
        except Exception:
            return []


def detect_category(text: str) -> str:
    """Detect memory category from text content."""
    text_lower = text.lower()

    for category, patterns in MEMORY_TRIGGERS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return category

    return "interaction"


def auto_capture(
    message: str,
    contact_phone: str | None = None,
) -> list[dict[str, Any]]:
    """
    Detect capturable information from a message.

    Args:
        message: Message text to analyze
        contact_phone: Contact phone for context

    Returns:
        List of potential memories to capture
    """
    captures = []
    message_lower = message.lower()

    # Check each category's triggers
    for category, patterns in MEMORY_TRIGGERS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                # Determine importance based on category
                importance = {
                    "preference": 0.8,
                    "decision": 0.9,
                    "fact": 0.7,
                    "entity": 0.6,
                    "interaction": 0.5,
                }.get(category, 0.5)

                captures.append({
                    "text": message,
                    "category": category,
                    "importance": importance,
                    "contact_phone": contact_phone,
                })
                break  # One capture per message

    return captures


def format_memories_for_context(memories: list[dict[str, Any]]) -> str:
    """
    Format memories for injection into LLM context.

    Args:
        memories: List of recalled memories

    Returns:
        Formatted context block
    """
    if not memories:
        return ""

    lines = ["[Memórias relevantes]"]
    for m in memories:
        category_emoji = {
            "preference": "⭐",
            "decision": "✅",
            "fact": "📋",
            "entity": "🏢",
            "interaction": "💬",
        }.get(m["category"], "📝")

        text = m["text"][:100]
        if len(m["text"]) > 100:
            text += "..."

        lines.append(f"{category_emoji} {text}")

    return "\n".join(lines)


# Global instance (lazy loaded)
_memory: ContactMemory | None = None


def get_contact_memory(
    db_path: str | None = None,
    openai_key: str | None = None,
) -> ContactMemory | None:
    """Get or create global ContactMemory instance."""
    global _memory
    if _memory is None:
        key = openai_key or os.getenv("OPENAI_API_KEY")
        if key:
            _memory = ContactMemory(db_path=db_path, openai_api_key=key)
    return _memory


def maybe_capture_memory(
    storage: SqliteStorage | SupabaseStorage,
    owner_id: str,
    contact_phone: str | None,
    message: str,
    openai_key: str | None = None,
) -> bool:
    """
    Check and capture memory from message if relevant.

    Called from message_handler after processing contact messages.
    Also saves to SQLite/Supabase as backup.
    """
    captures = auto_capture(message, contact_phone)
    if not captures:
        return False

    # Try LanceDB first
    memory = get_contact_memory(openai_key=openai_key)
    if memory:
        for capture in captures:
            try:
                memory.store(
                    owner_id=owner_id,
                    text=capture["text"],
                    contact_phone=capture["contact_phone"],
                    category=capture["category"],
                    importance=capture["importance"],
                )
            except Exception:
                pass  # LanceDB failed, will use backup

    # Always save to SQLite/Supabase as backup
    for capture in captures:
        try:
            storage.save_contact_memory(
                owner_id=owner_id,
                text=capture["text"],
                contact_phone=capture["contact_phone"],
                category=capture["category"],
                importance=capture["importance"],
            )
        except Exception:
            pass

    return True


def process_feedback_for_memories(
    owner_id: str,
    feedback_rating: str,
    memory_ids_used: list[str] | None = None,
    openai_key: str | None = None,
) -> None:
    """
    Process feedback to promote/demote memories used in a response.

    Called from learning.py when user provides feedback.
    Implements memory promotion based on feedback loop.

    Args:
        owner_id: Owner's phone (E164)
        feedback_rating: 'positive', 'negative', or 'correction'
        memory_ids_used: IDs of memories that were used in the response
        openai_key: OpenAI API key
    """
    if not memory_ids_used:
        return

    memory = get_contact_memory(openai_key=openai_key)
    if not memory:
        return

    for memory_id in memory_ids_used:
        if feedback_rating == "positive":
            # User liked response - promote memories used
            memory.promote_memory(memory_id, boost=0.1)
        elif feedback_rating == "negative":
            # User didn't like response - slight demotion
            memory.demote_memory(memory_id, penalty=0.05)
        elif feedback_rating == "correction":
            # User corrected - stronger demotion
            memory.demote_memory(memory_id, penalty=0.15)
