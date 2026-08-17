"""
RAG retrieval node - Fetch relevant knowledge before supervisor thinks.

Conditional: skips retrieval for greetings and short messages.
Retrieves from 4 layers:
1. Contact memories (LanceDB - existing)
2. Document store (LanceDB - new)
3. Conversation intelligence (LanceDB - new)
4. Learned patterns (SQLite - existing)
"""

from __future__ import annotations

from typing import Any

from graph.state import ShadowState

# Messages that don't need RAG
SKIP_RAG: set[str] = {
    "oi", "olá", "ola", "hey", "hi", "hello",
    "ok", "obrigado", "valeu", "sim", "não", "nao",
    "tchau", "bye", "ping", "pong",
}


def should_retrieve(body: str) -> bool:
    """Determine if RAG retrieval is needed for this message."""
    clean = body.strip().lower()
    if clean in SKIP_RAG:
        return False
    if len(clean.split()) < 3:
        return False
    return True


def rag_retrieve_node(state: ShadowState) -> dict[str, Any]:
    """Retrieve relevant knowledge from all 4 layers.

    Only runs for substantive messages (>3 words, not greetings).
    """
    body = state.get("body") or ""
    sender_phone = state.get("sender_phone")

    if not should_retrieve(body):
        return {
            "knowledge_context": [],
            "steps": [{"node": "rag_retrieve", "skipped": True}],
        }

    results: list[dict[str, Any]] = []

    # Layer 1: Contact memories (existing LanceDB)
    try:
        from contact_memory import ContactMemory

        memory = ContactMemory()
        contact_mems = memory.recall(
            query=body,
            owner_id=sender_phone or "",
            top_k=3,
        )
        for mem in contact_mems:
            results.append({"source": "contact_memory", **mem})
    except Exception as e:
        print(f"[rag] Contact memory error: {e}")

    # Layer 2: Document store (new — graceful if not yet implemented)
    try:
        from knowledge.document_memory import DocumentMemory

        doc_memory = DocumentMemory()
        doc_chunks = doc_memory.search(
            query=body,
            owner_id=sender_phone or "",
            top_k=3,
        )
        for chunk in doc_chunks:
            results.append({"source": "document", **chunk})
    except ImportError:
        pass  # Not yet implemented
    except Exception as e:
        print(f"[rag] Document memory error: {e}")

    # Layer 3: Conversation intelligence (new — graceful if not yet implemented)
    try:
        from knowledge.conversation_memory import ConversationMemory

        conv_memory = ConversationMemory()
        conv_mems = conv_memory.search(
            query=body,
            owner_id=sender_phone or "",
            top_k=2,
        )
        for mem in conv_mems:
            results.append({"source": "conversation", **mem})
    except ImportError:
        pass  # Not yet implemented
    except Exception as e:
        print(f"[rag] Conversation memory error: {e}")

    # Layer 4: Learned patterns (existing SQLite)
    try:
        from storage import Storage

        storage = Storage()
        patterns = storage.get_learned_patterns(
            owner_id=sender_phone or "",
            min_confidence=0.7,
        )
        for p in patterns[:3]:
            results.append({"source": "pattern", **p})
    except Exception as e:
        print(f"[rag] Pattern retrieval error: {e}")

    return {
        "knowledge_context": results,
        "steps": [{"node": "rag_retrieve", "results_count": len(results)}],
    }
