"""
RAG Engine - Unified retrieval across all 4 knowledge layers.

Used by the rag_retrieve node to fetch relevant context before
the supervisor thinks.
"""

from __future__ import annotations

from typing import Any


class RAGEngine:
    """Unified retrieval across all knowledge layers.

    Layers:
    1. Contact memories (LanceDB - contact_memory.py)
    2. Document store (LanceDB - document_memory.py)
    3. Conversation intelligence (LanceDB - conversation_memory.py)
    4. Learned patterns (SQLite - learning.py)
    """

    def __init__(self):
        self._contact_memory = None
        self._document_memory = None
        self._conversation_memory = None

    def query(
        self,
        text: str,
        owner_id: str,
        top_k: int = 5,
        layers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve from all layers and merge results.

        Args:
            text: Query text
            owner_id: Owner for tenant isolation
            top_k: Max results per layer
            layers: Which layers to query (default: all)

        Returns:
            Merged results sorted by relevance
        """
        active_layers = layers or ["contact", "document", "conversation", "pattern"]
        results: list[dict[str, Any]] = []

        if "contact" in active_layers:
            results.extend(self._query_contacts(text, owner_id, top_k))

        if "document" in active_layers:
            results.extend(self._query_documents(text, owner_id, top_k))

        if "conversation" in active_layers:
            results.extend(self._query_conversations(text, owner_id, top_k))

        if "pattern" in active_layers:
            results.extend(self._query_patterns(owner_id, top_k))

        return results[:top_k * 2]  # Cap total results

    def _query_contacts(self, text: str, owner_id: str, top_k: int) -> list[dict]:
        try:
            from contact_memory import ContactMemory
            if self._contact_memory is None:
                self._contact_memory = ContactMemory()
            mems = self._contact_memory.recall(query=text, owner_id=owner_id, top_k=top_k)
            return [{"source": "contact_memory", **m} for m in mems]
        except Exception:
            return []

    def _query_documents(self, text: str, owner_id: str, top_k: int) -> list[dict]:
        try:
            from knowledge.document_memory import DocumentMemory
            if self._document_memory is None:
                self._document_memory = DocumentMemory()
            chunks = self._document_memory.search(query=text, owner_id=owner_id, top_k=top_k)
            return [{"source": "document", **c} for c in chunks]
        except Exception:
            return []

    def _query_conversations(self, text: str, owner_id: str, top_k: int) -> list[dict]:
        try:
            from knowledge.conversation_memory import ConversationMemory
            if self._conversation_memory is None:
                self._conversation_memory = ConversationMemory()
            convs = self._conversation_memory.search(query=text, owner_id=owner_id, top_k=top_k)
            return [{"source": "conversation", **c} for c in convs]
        except Exception:
            return []

    def _query_patterns(self, owner_id: str, top_k: int) -> list[dict]:
        try:
            from storage import Storage
            storage = Storage()
            patterns = storage.get_learned_patterns(owner_id=owner_id, min_confidence=0.7)
            return [{"source": "pattern", **p} for p in patterns[:top_k]]
        except Exception:
            return []


# Singleton
_rag_engine: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
