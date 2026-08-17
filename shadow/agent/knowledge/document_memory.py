"""
Document Memory - Layer 2 of the RAG knowledge base.

Stores chunked documents (proposals, contracts, reports) with embeddings
in LanceDB for semantic retrieval.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class DocumentMemory:
    """Semantic search over stored documents using LanceDB.

    Stores document chunks with OpenAI embeddings for retrieval.
    Each chunk links back to its source document.
    """

    TABLE_NAME = "document_chunks"

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(
            Path(__file__).parent.parent / "data" / "knowledge_db"
        )
        self._db = None
        self._table = None
        self._embedder = None

    def _get_db(self):
        if self._db is None:
            try:
                import lancedb
                self._db = lancedb.connect(self._db_path)
            except ImportError:
                raise ImportError("lancedb is required for DocumentMemory")
        return self._db

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from openai import OpenAI
                self._embedder = OpenAI()
            except ImportError:
                raise ImportError("openai is required for embeddings")
        return self._embedder

    def _embed(self, text: str) -> list[float]:
        """Generate embedding for text using OpenAI."""
        client = self._get_embedder()
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def store(
        self,
        text: str,
        owner_id: str,
        doc_type: str = "general",
        doc_id: str | None = None,
        chunk_num: int = 0,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a document chunk with embedding."""
        chunk_id = str(uuid4())[:12]

        try:
            vector = self._embed(text)
        except Exception:
            vector = [0.0] * 1536

        record = {
            "id": chunk_id,
            "owner_id": owner_id,
            "doc_type": doc_type,
            "doc_id": doc_id or str(uuid4())[:8],
            "chunk_num": chunk_num,
            "text": text,
            "source": source,
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
                pa.field("doc_type", pa.string()),
                pa.field("doc_id", pa.string()),
                pa.field("chunk_num", pa.int32()),
                pa.field("text", pa.string()),
                pa.field("source", pa.string()),
                pa.field("created_at", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 1536)),
            ])
            table = db.create_table(self.TABLE_NAME, schema=schema)
            table.add([record])

        return chunk_id

    def search(
        self,
        query: str,
        owner_id: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over document chunks."""
        try:
            query_vec = self._embed(query)
        except Exception:
            return []

        db = self._get_db()
        try:
            table = db.open_table(self.TABLE_NAME)
        except Exception:
            return []

        results = (
            table.search(query_vec)
            .where(f"owner_id = '{owner_id}'")
            .limit(top_k)
            .to_list()
        )

        if doc_type:
            results = [r for r in results if r.get("doc_type") == doc_type]

        return [
            {
                "id": r["id"],
                "text": r["text"],
                "doc_type": r.get("doc_type", ""),
                "source": r.get("source", ""),
                "score": r.get("_distance", 0),
            }
            for r in results
        ]

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i : i + chunk_size])
            if len(chunk) > 50:
                chunks.append(chunk)
        return chunks
