"""
SessionStore - Gerenciamento de sessões de conversa para Shadow MVP.

Baseado nos padrões do Moltbot, suporta:
- Contexto de conversa persistente
- Window de mensagens recentes
- Configurações por sessão
- Métricas de uso
- Proteção contra path traversal (moltbot 2026.2.x)
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from config import resolve_db_path
from security import sanitize_session_key, validate_phone_number, ValidationError
from crypto import get_crypto


@dataclass
class PendingConfirmation:
    """
    Confirmação pendente de ação (Phase 8 - CRM Oculto).

    Quando o Shadow detecta um compromisso em conversa de terceiros,
    ele pergunta ao owner se deve registrar. Esta estrutura rastreia
    a confirmação pendente.
    """
    confirmation_type: str  # "create_appointment", "create_task", etc.
    entity_data: dict[str, Any]
    sender_phone: str | None
    sender_name: str | None
    source_chat_id: str | None
    created_at: str
    expires_at: str

    def is_expired(self) -> bool:
        """Check if confirmation has expired."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return now > expires

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmation_type": self.confirmation_type,
            "entity_data": self.entity_data,
            "sender_phone": self.sender_phone,
            "sender_name": self.sender_name,
            "source_chat_id": self.source_chat_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingConfirmation":
        return cls(
            confirmation_type=data.get("confirmation_type", "unknown"),
            entity_data=data.get("entity_data", {}),
            sender_phone=data.get("sender_phone"),
            sender_name=data.get("sender_name"),
            source_chat_id=data.get("source_chat_id"),
            created_at=data.get("created_at", ""),
            expires_at=data.get("expires_at", ""),
        )


@dataclass
class ContextMessage:
    """Uma mensagem no contexto da sessão."""
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """Representa uma sessão de conversa."""
    id: str
    chat_id: str
    participant_phone: str | None
    kind: Literal["direct", "group"]
    status: Literal["active", "idle", "closed"]
    context_window: list[ContextMessage]
    context_summary: str | None
    defaults: dict[str, Any]
    metadata: dict[str, Any]
    label: str | None
    display_name: str | None
    message_count: int
    input_tokens: int
    output_tokens: int
    created_at: str
    updated_at: str
    last_activity_at: str
    # Recipient tracking (Phase 4 - moltbot pattern)
    last_channel: str | None = None
    last_recipient: str | None = None
    last_recipient_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "participant_phone": self.participant_phone,
            "kind": self.kind,
            "status": self.status,
            "context_window": [m.to_dict() for m in self.context_window],
            "context_summary": self.context_summary,
            "defaults": self.defaults,
            "metadata": self.metadata,
            "label": self.label,
            "display_name": self.display_name,
            "message_count": self.message_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity_at": self.last_activity_at,
            "last_channel": self.last_channel,
            "last_recipient": self.last_recipient,
            "last_recipient_at": self.last_recipient_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        crypto = get_crypto()
        context_data = data.get("context_window", [])
        if isinstance(context_data, str):
            context_data = crypto.decrypt_json(context_data, default=[]) if context_data else []

        context_window = [
            ContextMessage.from_dict(m) if isinstance(m, dict) else m
            for m in context_data
        ]

        defaults = data.get("defaults", {})
        if isinstance(defaults, str):
            defaults = crypto.decrypt_json(defaults, default={}) if defaults else {}

        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            metadata = crypto.decrypt_json(metadata, default={}) if metadata else {}

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            chat_id=data.get("chat_id", ""),
            participant_phone=data.get("participant_phone"),
            kind=data.get("kind", "direct"),
            status=data.get("status", "active"),
            context_window=context_window,
            context_summary=crypto.decrypt_text(data.get("context_summary") or ""),
            defaults=defaults,
            metadata=metadata,
            label=data.get("label"),
            display_name=data.get("display_name"),
            message_count=data.get("message_count", 0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            last_activity_at=data.get("last_activity_at", datetime.now(timezone.utc).isoformat()),
            last_channel=data.get("last_channel"),
            last_recipient=data.get("last_recipient"),
            last_recipient_at=data.get("last_recipient_at"),
        )


class SessionStore:
    """
    Gerenciador de sessões de conversa.

    Exemplo de uso:
    ```python
    store = SessionStore()

    # Obter ou criar sessão
    session = store.get_or_create(chat_id="5511999999999@s.whatsapp.net")

    # Adicionar mensagem ao contexto
    store.add_message(session.id, ContextMessage(
        role="user",
        content="Olá!",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    # Obter contexto para o agente
    context = store.get_context(session.id, limit=10)
    ```
    """

    DEFAULT_CONTEXT_WINDOW_SIZE = 10

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or resolve_db_path()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.crypto = get_crypto()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Cria tabela de sessões se não existir."""
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL UNIQUE,
                participant_phone TEXT,
                kind TEXT NOT NULL DEFAULT 'direct',
                status TEXT DEFAULT 'active',
                context_window TEXT DEFAULT '[]',
                context_summary TEXT,
                defaults TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                label TEXT,
                display_name TEXT,
                message_count INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                last_activity_at TEXT,
                last_channel TEXT,
                last_recipient TEXT,
                last_recipient_at TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_participant ON sessions(participant_phone)")

        # Migration: Add recipient tracking columns if not exist (Phase 4)
        self._migrate_recipient_columns(cur)

        # Phase 8: Pending confirmations table for CRM Oculto
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                owner_id TEXT PRIMARY KEY,
                confirmation_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        self._conn.commit()

    def _migrate_recipient_columns(self, cur: sqlite3.Cursor) -> None:
        """Add recipient tracking columns to existing schema."""
        # Check if columns exist
        cur.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in cur.fetchall()}

        if "last_channel" not in columns:
            cur.execute("ALTER TABLE sessions ADD COLUMN last_channel TEXT")
        if "last_recipient" not in columns:
            cur.execute("ALTER TABLE sessions ADD COLUMN last_recipient TEXT")
        if "last_recipient_at" not in columns:
            cur.execute("ALTER TABLE sessions ADD COLUMN last_recipient_at TEXT")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, session_id: str) -> Session | None:
        """Obtém sessão por ID."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        if row:
            return Session.from_dict(dict(row))
        return None

    def get_by_chat(self, chat_id: str) -> Session | None:
        """Obtém sessão por chat_id."""
        # Valida chat_id para prevenir path traversal (moltbot 2026.2.x)
        try:
            safe_chat_id = sanitize_session_key(chat_id)
        except ValidationError as e:
            # Log tentativa suspeita mas não falha silenciosamente
            print(f"[security] Invalid chat_id rejected: {e}")
            return None

        cur = self._conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE chat_id = ?", (safe_chat_id,))
        row = cur.fetchone()
        if row:
            return Session.from_dict(dict(row))
        return None

    def get_or_create(
        self,
        chat_id: str,
        participant_phone: str | None = None,
        kind: Literal["direct", "group"] = "direct",
        display_name: str | None = None,
    ) -> Session:
        """Obtém sessão existente ou cria uma nova."""
        # Valida inputs para prevenir path traversal (moltbot 2026.2.x)
        try:
            safe_chat_id = sanitize_session_key(chat_id)
        except ValidationError as e:
            print(f"[security] Invalid chat_id rejected: {e}")
            raise ValueError(f"Invalid chat_id: {chat_id[:50]}")

        # Valida participant_phone se fornecido
        safe_participant = None
        if participant_phone:
            safe_participant = validate_phone_number(participant_phone)
            if not safe_participant:
                print(f"[security] Invalid participant_phone, using None")

        session = self.get_by_chat(safe_chat_id)
        if session:
            # Atualiza última atividade
            self._update_activity(session.id)
            return session

        # Cria nova sessão
        now = self._now_iso()
        session_id = str(uuid.uuid4())

        session = Session(
            id=session_id,
            chat_id=safe_chat_id,
            participant_phone=safe_participant,
            kind=kind,
            status="active",
            context_window=[],
            context_summary=None,
            defaults={},
            metadata={},
            label=None,
            display_name=display_name,
            message_count=0,
            input_tokens=0,
            output_tokens=0,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
        )

        cur = self._conn.cursor()
        cur.execute("""
            INSERT INTO sessions (
                id, chat_id, participant_phone, kind, status,
                context_window, context_summary, defaults, metadata,
                label, display_name, message_count, input_tokens, output_tokens,
                created_at, updated_at, last_activity_at,
                last_channel, last_recipient, last_recipient_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.id,
            session.chat_id,
            session.participant_phone,
            session.kind,
            session.status,
            self.crypto.encrypt_json([], aad="session:context"),
            self.crypto.encrypt_text(session.context_summary or "", aad="session:summary"),
            self.crypto.encrypt_json(session.defaults, aad="session:defaults"),
            self.crypto.encrypt_json(session.metadata, aad="session:metadata"),
            session.label,
            session.display_name,
            session.message_count,
            session.input_tokens,
            session.output_tokens,
            session.created_at,
            session.updated_at,
            session.last_activity_at,
            session.last_channel,
            session.last_recipient,
            session.last_recipient_at,
        ))
        self._conn.commit()

        return session

    def _update_activity(self, session_id: str) -> None:
        """Atualiza timestamp de última atividade."""
        now = self._now_iso()
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE sessions SET last_activity_at = ?, updated_at = ? WHERE id = ?",
            (now, now, session_id)
        )
        self._conn.commit()

    def add_message(
        self,
        session_id: str,
        message: ContextMessage,
        max_window_size: int | None = None,
    ) -> None:
        """
        Adiciona mensagem ao contexto da sessão.

        Mantém apenas as últimas `max_window_size` mensagens.
        """
        if max_window_size is None:
            max_window_size = self.DEFAULT_CONTEXT_WINDOW_SIZE

        session = self.get(session_id)
        if not session:
            return

        # Adiciona mensagem
        session.context_window.append(message)

        # Limita tamanho da janela
        if len(session.context_window) > max_window_size:
            session.context_window = session.context_window[-max_window_size:]

        # Atualiza contadores
        session.message_count += 1

        now = self._now_iso()
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                context_window = ?,
                message_count = ?,
                updated_at = ?,
                last_activity_at = ?
            WHERE id = ?
        """, (
            self.crypto.encrypt_json([m.to_dict() for m in session.context_window], aad="session:context"),
            session.message_count,
            now,
            now,
            session_id,
        ))
        self._conn.commit()

    def get_context(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[ContextMessage]:
        """
        Obtém mensagens de contexto da sessão.

        Retorna as últimas `limit` mensagens.
        """
        session = self.get(session_id)
        if not session:
            return []

        context = session.context_window
        if limit and len(context) > limit:
            context = context[-limit:]

        return context

    def get_context_for_llm(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """
        Obtém contexto formatado para LLM (OpenAI/Anthropic format).

        Retorna lista de dicts com 'role' e 'content'.
        """
        messages = self.get_context(session_id, limit)
        return [{"role": m.role, "content": m.content} for m in messages]

    def update_tokens(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Atualiza contadores de tokens."""
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?,
                updated_at = ?
            WHERE id = ?
        """, (input_tokens, output_tokens, self._now_iso(), session_id))
        self._conn.commit()

    def update_defaults(
        self,
        session_id: str,
        defaults: dict[str, Any],
    ) -> None:
        """Atualiza configurações da sessão."""
        session = self.get(session_id)
        if not session:
            return

        session.defaults.update(defaults)

        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                defaults = ?,
                updated_at = ?
            WHERE id = ?
        """, (self.crypto.encrypt_json(session.defaults, aad="session:defaults"), self._now_iso(), session_id))
        self._conn.commit()

    def update_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Atualiza metadados da sessão."""
        session = self.get(session_id)
        if not session:
            return

        session.metadata.update(metadata)

        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                metadata = ?,
                updated_at = ?
            WHERE id = ?
        """, (self.crypto.encrypt_json(session.metadata, aad="session:metadata"), self._now_iso(), session_id))
        self._conn.commit()

    def set_status(
        self,
        session_id: str,
        status: Literal["active", "idle", "closed"],
    ) -> None:
        """Define status da sessão."""
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                status = ?,
                updated_at = ?
            WHERE id = ?
        """, (status, self._now_iso(), session_id))
        self._conn.commit()

    def clear_context(self, session_id: str) -> None:
        """Limpa contexto da sessão."""
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                context_window = ?,
                context_summary = NULL,
                updated_at = ?
            WHERE id = ?
        """, (self.crypto.encrypt_json([], aad="session:context"), self._now_iso(), session_id))
        self._conn.commit()

    def set_summary(self, session_id: str, summary: str) -> None:
        """Define resumo do contexto (para sessões longas)."""
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                context_summary = ?,
                updated_at = ?
            WHERE id = ?
        """, (self.crypto.encrypt_text(summary, aad="session:summary"), self._now_iso(), session_id))
        self._conn.commit()

    def list_active(self, limit: int = 50) -> list[Session]:
        """Lista sessões ativas ordenadas por última atividade."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT * FROM sessions
            WHERE status = 'active'
            ORDER BY last_activity_at DESC
            LIMIT ?
        """, (limit,))
        return [Session.from_dict(dict(row)) for row in cur.fetchall()]

    def list_by_participant(self, phone: str, limit: int = 20) -> list[Session]:
        """Lista sessões de um participante específico."""
        # Valida phone para prevenir injection
        safe_phone = validate_phone_number(phone)
        if not safe_phone:
            print(f"[security] Invalid phone in list_by_participant, returning empty")
            return []

        cur = self._conn.cursor()
        cur.execute("""
            SELECT * FROM sessions
            WHERE participant_phone = ?
            ORDER BY last_activity_at DESC
            LIMIT ?
        """, (safe_phone, limit))
        return [Session.from_dict(dict(row)) for row in cur.fetchall()]

    def delete(self, session_id: str) -> bool:
        """Remove uma sessão."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """
        Remove sessões inativas há mais de N dias.

        Retorna número de sessões removidas.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        cur = self._conn.cursor()
        cur.execute("""
            DELETE FROM sessions
            WHERE status IN ('idle', 'closed')
            AND last_activity_at < ?
        """, (cutoff,))
        self._conn.commit()
        return cur.rowcount

    # === Pending Confirmations (Phase 8 - CRM Oculto) ===

    def set_pending_confirmation(
        self,
        owner_id: str,
        confirmation_type: str,
        entity_data: dict[str, Any],
        sender_phone: str | None = None,
        sender_name: str | None = None,
        source_chat_id: str | None = None,
        expires_in_seconds: int = 300,
    ) -> None:
        """
        Define uma confirmação pendente para o owner.

        Quando o Shadow detecta um compromisso em conversa de terceiros,
        ele cria uma confirmação pendente e pergunta ao owner.

        Args:
            owner_id: Telefone E.164 do owner
            confirmation_type: Tipo de ação ("create_appointment", "create_task")
            entity_data: Dados da entidade extraída
            sender_phone: Telefone de quem enviou a mensagem original
            sender_name: Nome de quem enviou a mensagem original
            source_chat_id: Chat de onde veio a mensagem
            expires_in_seconds: Tempo até expirar (default: 5 min)
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)

        confirmation = PendingConfirmation(
            confirmation_type=confirmation_type,
            entity_data=entity_data,
            sender_phone=sender_phone,
            sender_name=sender_name,
            source_chat_id=source_chat_id,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )

        cur = self._conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO pending_confirmations (
                owner_id, confirmation_data, created_at, expires_at
            ) VALUES (?, ?, ?, ?)
        """, (
            owner_id,
            self.crypto.encrypt_json(confirmation.to_dict(), aad="pending:confirmation"),
            confirmation.created_at,
            confirmation.expires_at,
        ))
        self._conn.commit()

    def get_pending_confirmation(self, owner_id: str) -> PendingConfirmation | None:
        """
        Obtém confirmação pendente para o owner.

        Retorna None se não houver confirmação ou se expirou.
        """
        cur = self._conn.cursor()
        cur.execute("""
            SELECT confirmation_data, expires_at
            FROM pending_confirmations
            WHERE owner_id = ?
        """, (owner_id,))

        row = cur.fetchone()
        if not row:
            return None

        # Check expiration
        expires_at = row[1]
        if expires_at:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires:
                # Expired - clean up
                self.clear_pending_confirmation(owner_id)
                return None

        # Decrypt and return
        data = self.crypto.decrypt_json(row[0], default={})
        if not data:
            return None

        return PendingConfirmation.from_dict(data)

    def clear_pending_confirmation(self, owner_id: str) -> None:
        """Remove confirmação pendente do owner."""
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM pending_confirmations WHERE owner_id = ?",
            (owner_id,)
        )
        self._conn.commit()

    # === Recipient Tracking (Phase 4 - moltbot pattern) ===

    def update_last_recipient(
        self,
        session_id: str,
        channel: str,
        recipient: str,
    ) -> None:
        """
        Atualiza o último destinatário usado nesta sessão.

        Usado para resolução inteligente de destinatários em reminders.

        Args:
            session_id: ID da sessão
            channel: Canal usado (ex: "whatsapp", "evolution", "zapi")
            recipient: Número/ID do destinatário
        """
        # Valida recipient
        safe_recipient = validate_phone_number(recipient)
        if not safe_recipient:
            print(f"[security] Invalid recipient in update_last_recipient")
            return

        now = self._now_iso()
        cur = self._conn.cursor()
        cur.execute("""
            UPDATE sessions SET
                last_channel = ?,
                last_recipient = ?,
                last_recipient_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (channel, safe_recipient, now, now, session_id))
        self._conn.commit()

    def get_recent_recipients(
        self,
        participant_phone: str | None = None,
        limit: int = 5,
        max_age_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Obtém destinatários recentes para resolução de targeting.

        Retorna lista ordenada por recência:
        [{"session_id", "channel", "recipient", "recipient_at"}, ...]

        Args:
            participant_phone: Filtrar por participante (opcional)
            limit: Máximo de resultados
            max_age_hours: Idade máxima em horas
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()

        cur = self._conn.cursor()

        if participant_phone:
            safe_phone = validate_phone_number(participant_phone)
            if not safe_phone:
                return []

            cur.execute("""
                SELECT id, last_channel, last_recipient, last_recipient_at
                FROM sessions
                WHERE participant_phone = ?
                AND last_recipient IS NOT NULL
                AND last_recipient_at > ?
                AND status = 'active'
                ORDER BY last_recipient_at DESC
                LIMIT ?
            """, (safe_phone, cutoff, limit))
        else:
            cur.execute("""
                SELECT id, last_channel, last_recipient, last_recipient_at
                FROM sessions
                WHERE last_recipient IS NOT NULL
                AND last_recipient_at > ?
                AND status = 'active'
                ORDER BY last_recipient_at DESC
                LIMIT ?
            """, (cutoff, limit))

        return [
            {
                "session_id": row[0],
                "channel": row[1],
                "recipient": row[2],
                "recipient_at": row[3],
            }
            for row in cur.fetchall()
        ]

    def get_last_recipient_for_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Obtém o último destinatário usado numa sessão específica.

        Retorna None se não houver recipient tracking.
        """
        session = self.get(session_id)
        if not session or not session.last_recipient:
            return None

        return {
            "channel": session.last_channel,
            "recipient": session.last_recipient,
            "recipient_at": session.last_recipient_at,
        }

    def stats(self) -> dict[str, Any]:
        """Retorna estatísticas das sessões."""
        cur = self._conn.cursor()

        cur.execute("SELECT COUNT(*) as total FROM sessions")
        total = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) as active FROM sessions WHERE status = 'active'")
        active = cur.fetchone()["active"]

        cur.execute("SELECT SUM(message_count) as messages FROM sessions")
        messages = cur.fetchone()["messages"] or 0

        cur.execute("SELECT SUM(input_tokens) as input, SUM(output_tokens) as output FROM sessions")
        tokens = cur.fetchone()

        return {
            "total_sessions": total,
            "active_sessions": active,
            "total_messages": messages,
            "total_input_tokens": tokens["input"] or 0,
            "total_output_tokens": tokens["output"] or 0,
        }


# === Recipient Resolution (Phase 4 - moltbot pattern) ===

@dataclass
class ResolvedRecipient:
    """Resultado da resolução de destinatário."""
    channel: str
    recipient: str
    source: Literal["explicit", "session", "recent", "allowlist", "fallback"]
    session_id: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "recipient": self.recipient,
            "source": self.source,
            "session_id": self.session_id,
            "confidence": self.confidence,
        }


def resolve_recipient(
    store: SessionStore,
    *,
    explicit_recipient: str | None = None,
    explicit_channel: str | None = None,
    session_id: str | None = None,
    participant_phone: str | None = None,
    allowlist: list[str] | None = None,
    default_channel: str = "whatsapp",
) -> ResolvedRecipient | None:
    """
    Resolve o destinatário para envio de mensagens/reminders.

    Prioridade de resolução (inspirado no moltbot whatsapp-heartbeat):
    1. Explícito - se recipient foi especificado diretamente
    2. Sessão - último destinatário da sessão específica
    3. Recente - destinatário mais recente do participante
    4. Allowlist - primeiro número da lista de permitidos
    5. Fallback - None (falha na resolução)

    Args:
        store: SessionStore para buscar histórico
        explicit_recipient: Destinatário especificado explicitamente
        explicit_channel: Canal especificado explicitamente
        session_id: ID da sessão para buscar último recipient
        participant_phone: Telefone do participante para buscar recentes
        allowlist: Lista de números permitidos como fallback
        default_channel: Canal padrão se não especificado

    Returns:
        ResolvedRecipient com informações de targeting, ou None se falha
    """
    # 1. Prioridade: Explícito
    if explicit_recipient:
        safe_recipient = validate_phone_number(explicit_recipient)
        if safe_recipient:
            return ResolvedRecipient(
                channel=explicit_channel or default_channel,
                recipient=safe_recipient,
                source="explicit",
                confidence=1.0,
            )

    # 2. Sessão específica
    if session_id:
        last = store.get_last_recipient_for_session(session_id)
        if last and last.get("recipient"):
            return ResolvedRecipient(
                channel=last.get("channel") or default_channel,
                recipient=last["recipient"],
                source="session",
                session_id=session_id,
                confidence=0.9,
            )

    # 3. Recentes do participante
    if participant_phone:
        recents = store.get_recent_recipients(
            participant_phone=participant_phone,
            limit=1,
            max_age_hours=24,
        )
        if recents:
            recent = recents[0]
            return ResolvedRecipient(
                channel=recent.get("channel") or default_channel,
                recipient=recent["recipient"],
                source="recent",
                session_id=recent.get("session_id"),
                confidence=0.8,
            )

    # 4. Allowlist fallback
    if allowlist:
        for phone in allowlist:
            safe_phone = validate_phone_number(phone)
            if safe_phone:
                return ResolvedRecipient(
                    channel=default_channel,
                    recipient=safe_phone,
                    source="allowlist",
                    confidence=0.5,
                )

    # 5. Falha na resolução
    return None


# === Singleton global para uso simplificado ===

_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Obtém instância global do SessionStore."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


# === Exemplo de uso ===

if __name__ == "__main__":
    store = SessionStore(db_path="./data/shadow.db")

    # Criar/obter sessão
    session = store.get_or_create(
        chat_id="5511999999999@s.whatsapp.net",
        participant_phone="+5511999999999",
        kind="direct",
        display_name="João",
    )
    print(f"Sessão: {session.id}")

    # Adicionar mensagens
    store.add_message(session.id, ContextMessage(
        role="user",
        content="Olá, preciso criar uma tarefa",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    store.add_message(session.id, ContextMessage(
        role="assistant",
        content="Claro! Qual tarefa você gostaria de criar?",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    # Obter contexto
    context = store.get_context_for_llm(session.id)
    print(f"Contexto: {context}")

    # Stats
    print(f"Stats: {store.stats()}")
