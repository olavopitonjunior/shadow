import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from config import resolve_db_path
from crypto import get_crypto
from storage.types import Task, Appointment

class SqliteStorage:
    def __init__(self, db_path: str | None = None, owner_id: str | None = None, _conn: sqlite3.Connection | None = None) -> None:
        self.owner_id = owner_id
        if _conn is not None:
            self._conn = _conn
            self.db_path = db_path or ""
            self.crypto = get_crypto()
        else:
            self.db_path = db_path or resolve_db_path()
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self.crypto = get_crypto()
            self._ensure_schema()

    def for_owner(self, owner_id: str) -> "SqliteStorage":
        """Return a view of this storage filtered by owner_id. Shares the DB connection."""
        return SqliteStorage(db_path=self.db_path, owner_id=owner_id, _conn=self._conn)

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                name TEXT,
                last_interaction_at TEXT,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE,
                chat_type TEXT,
                contact_phone TEXT,
                last_message_at TEXT,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remind_at TEXT NOT NULL,
                message TEXT NOT NULL,
                task_id INTEGER,
                appointment_id INTEGER,
                sent INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                chat_id TEXT,
                sender_phone TEXT,
                direction TEXT,
                content TEXT,
                timestamp TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT,
                user_message TEXT,
                shadow_response TEXT,
                intent TEXT,
                timestamp TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )
        # Entity extraction tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_extracted_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                source_chat_id TEXT NOT NULL,
                source_message_id TEXT,
                entity_type TEXT NOT NULL,
                entity_data TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                extracted_at TEXT,
                created_at TEXT,
                processed INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_contact_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                contact_name TEXT,
                last_interaction TEXT,
                interaction_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                summary TEXT,
                topics TEXT,
                sentiment TEXT,
                first_seen TEXT,
                updated_at TEXT,
                UNIQUE(owner_id, contact_phone)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_task_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                contact_phone TEXT,
                contact_name TEXT,
                relation_type TEXT DEFAULT 'mentioned',
                created_at TEXT
            )
            """
        )
        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_owner ON shadow_extracted_entities(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON shadow_extracted_entities(entity_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_context_owner ON shadow_contact_context(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_context_phone ON shadow_contact_context(contact_phone)")

        # Phase 5: Contact aliases table for name resolution
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_contact_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                alias TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(owner_id, alias)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_aliases_owner ON shadow_contact_aliases(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_aliases_alias ON shadow_contact_aliases(alias)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_aliases_phone ON shadow_contact_aliases(contact_phone)")

        # Phase 6: Contact memories table (backup for LanceDB)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_contact_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                contact_phone TEXT,
                text TEXT NOT NULL,
                category TEXT DEFAULT 'interaction',
                importance REAL DEFAULT 0.5,
                created_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_memories_owner ON shadow_contact_memories(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_memories_phone ON shadow_contact_memories(contact_phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_memories_category ON shadow_contact_memories(category)")

        # Shadow Instances table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_instances (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                owner_e164 TEXT,
                gateway_user_id TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'disconnected',
                created_at TEXT DEFAULT (datetime('now')),
                connected_at TEXT,
                disconnected_at TEXT
            )
            """
        )

        self._conn.commit()

        # Run migrations for existing tables
        self._migrate_contacts_phase5(cur)
        self._migrate_contact_context_phase5(cur)

    def _migrate_contacts_phase5(self, cur: sqlite3.Cursor) -> None:
        """Add Phase 5 columns to contacts table."""
        cur.execute("PRAGMA table_info(contacts)")
        existing = {row[1] for row in cur.fetchall()}

        migrations = [
            ("email", "TEXT"),
            ("notes", "TEXT"),
            ("tags", "TEXT DEFAULT '[]'"),  # JSON as text in SQLite
            ("source", "TEXT DEFAULT 'message'"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing:
                cur.execute(f"ALTER TABLE contacts ADD COLUMN {col_name} {col_type}")
        self._conn.commit()

    def _migrate_contact_context_phase5(self, cur: sqlite3.Cursor) -> None:
        """Add Phase 5 columns to shadow_contact_context table."""
        cur.execute("PRAGMA table_info(shadow_contact_context)")
        existing = {row[1] for row in cur.fetchall()}

        migrations = [
            ("relationship_type", "TEXT"),
            ("last_summary_at", "TEXT"),
            ("summary_message_count", "INTEGER DEFAULT 0"),
            ("email", "TEXT"),  # Phase 1 CRM: Email for duplicate detection
            # Phase 8: CRM Oculto - Context update fields
            ("company", "TEXT"),
            ("role", "TEXT"),
            ("has_pending_appointments", "INTEGER DEFAULT 0"),
            ("has_pending_tasks", "INTEGER DEFAULT 0"),
            ("notes", "TEXT"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing:
                cur.execute(f"ALTER TABLE shadow_contact_context ADD COLUMN {col_name} {col_type}")
        self._conn.commit()

        # Phase 1 CRM: Soft delete for contact_context
        self._migrate_contact_soft_delete(cur)

    def _migrate_contact_soft_delete(self, cur: sqlite3.Cursor) -> None:
        """Add soft delete columns to contact tables."""
        # contacts table
        cur.execute("PRAGMA table_info(contacts)")
        existing = {row[1] for row in cur.fetchall()}
        if "deleted_at" not in existing:
            cur.execute("ALTER TABLE contacts ADD COLUMN deleted_at TEXT")
            cur.execute("ALTER TABLE contacts ADD COLUMN deleted_by TEXT")

        # shadow_contact_context table
        cur.execute("PRAGMA table_info(shadow_contact_context)")
        existing = {row[1] for row in cur.fetchall()}
        if "deleted_at" not in existing:
            cur.execute("ALTER TABLE shadow_contact_context ADD COLUMN deleted_at TEXT")

        # Create merge history table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_contact_merges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                target_phone TEXT NOT NULL,
                source_phone TEXT NOT NULL,
                source_name TEXT,
                merged_at TEXT,
                merged_by TEXT
            )
            """
        )

        # Create duplicates table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_contact_duplicates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                phone_a TEXT NOT NULL,
                phone_b TEXT NOT NULL,
                similarity_score REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                detected_at TEXT,
                resolved_at TEXT,
                resolved_by TEXT,
                UNIQUE(owner_id, phone_a, phone_b)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_merges_owner ON shadow_contact_merges(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contact_duplicates_owner ON shadow_contact_duplicates(owner_id)")
        self._conn.commit()

        # Phase 2: Categories
        self._migrate_categories_phase2(cur)

        # Phase 3: User Settings
        self._migrate_user_settings(cur)

        # Phase 4: Scheduled Alerts
        self._migrate_scheduled_alerts(cur)

        # Phase 5: Learning System
        self._migrate_learning(cur)

        # Phase 7: Entity sender tracking
        self._migrate_entities_phase7(cur)

        # Phase 9: API usage tracking (migration 029)
        self._migrate_api_usage(cur)

        # Phase 10: Channel users/messages/templates (migration 031)
        self._migrate_channel_tables(cur)

    def _migrate_entities_phase7(self, cur: sqlite3.Cursor) -> None:
        """Add sender tracking columns to shadow_extracted_entities (migration 028)."""
        cur.execute("PRAGMA table_info(shadow_extracted_entities)")
        existing = {row[1] for row in cur.fetchall()}

        migrations = [
            ("sender_phone", "TEXT"),  # Real sender phone (E.164)
            ("sender_name", "TEXT"),   # Real sender name (push name)
        ]
        for col_name, col_type in migrations:
            if col_name not in existing:
                cur.execute(f"ALTER TABLE shadow_extracted_entities ADD COLUMN {col_name} {col_type}")

        # Index for efficient contact association
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_sender ON shadow_extracted_entities(sender_phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_sender_name ON shadow_extracted_entities(sender_name)")
        self._conn.commit()

    def _migrate_learning(self, cur: sqlite3.Cursor) -> None:
        """Add learning system tables (feedback, patterns, preferences)."""
        # Feedback table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                message_id TEXT,
                response_text TEXT,
                rating TEXT NOT NULL CHECK (rating IN ('positive', 'negative', 'correction')),
                correction_text TEXT,
                context TEXT DEFAULT '{}',
                created_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_owner ON shadow_feedback(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON shadow_feedback(owner_id, rating)")

        # Learned patterns table
        # Note: SQLite doesn't support expressions in UNIQUE, so we handle uniqueness in code
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                trigger_text TEXT DEFAULT '',
                trigger_regex TEXT,
                learned_action TEXT NOT NULL,
                tool_name TEXT DEFAULT '',
                example_input TEXT,
                example_correction TEXT,
                confidence REAL DEFAULT 0.5,
                occurrences INTEGER DEFAULT 1,
                last_matched_at TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Create a unique index with actual columns (empty string for NULL)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_patterns_unique ON shadow_learned_patterns(owner_id, pattern_type, trigger_text, tool_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_patterns_lookup ON shadow_learned_patterns(owner_id, pattern_type, is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_patterns_tool ON shadow_learned_patterns(owner_id, tool_name, is_active)")

        # Learned preferences table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_user_preferences_learned (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 1,
                last_observed_at TEXT,
                source TEXT DEFAULT 'auto',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(owner_id, preference_key)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_prefs_learned_owner ON shadow_user_preferences_learned(owner_id)")
        self._conn.commit()

    def _migrate_scheduled_alerts(self, cur: sqlite3.Cursor) -> None:
        """Add scheduled alerts table."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_scheduled_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                alert_time TEXT NOT NULL,
                timezone TEXT DEFAULT 'America/Sao_Paulo',
                recurrence TEXT DEFAULT 'daily',
                days_of_week TEXT DEFAULT '1,2,3,4,5,6,7',
                alert_type TEXT DEFAULT 'summary',
                custom_message TEXT,
                include_tasks INTEGER DEFAULT 1,
                include_appointments INTEGER DEFAULT 1,
                include_reminders INTEGER DEFAULT 1,
                include_overdue INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                last_sent_at TEXT,
                next_scheduled_at TEXT,
                name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_owner ON shadow_scheduled_alerts(owner_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_active ON shadow_scheduled_alerts(is_active)")

        # Alert history table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER REFERENCES shadow_scheduled_alerts(id),
                owner_id TEXT NOT NULL,
                content TEXT NOT NULL,
                sent_at TEXT,
                success INTEGER DEFAULT 1,
                error_message TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_owner ON shadow_alert_history(owner_id)")
        self._conn.commit()

    def _migrate_user_settings(self, cur: sqlite3.Cursor) -> None:
        """Add user settings table."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_user_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL UNIQUE,
                auto_create_from_conversations INTEGER DEFAULT 0,
                group_monitoring_enabled INTEGER DEFAULT 0,
                gcal_check_conflicts INTEGER DEFAULT 1,
                gcal_auto_sync INTEGER DEFAULT 1,
                default_reminder_minutes INTEGER DEFAULT 30,
                morning_summary_enabled INTEGER DEFAULT 0,
                morning_summary_time TEXT DEFAULT '07:00',
                always_ask_incomplete INTEGER DEFAULT 1,
                timezone TEXT DEFAULT 'America/Sao_Paulo',
                language TEXT DEFAULT 'pt-BR',
                use_emojis INTEGER DEFAULT 1,
                verbose_responses INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_owner ON shadow_user_settings(owner_id)")
        self._conn.commit()

    def _migrate_categories_phase2(self, cur: sqlite3.Cursor) -> None:
        """Add Phase 2 category tables and columns."""
        # Task categories table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_task_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                color TEXT DEFAULT '#3B82F6',
                icon TEXT DEFAULT 'task',
                is_default BOOLEAN DEFAULT 0,
                created_at TEXT,
                UNIQUE(owner_id, name)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_task_categories_owner ON shadow_task_categories(owner_id)")

        # Appointment types table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_appointment_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                default_duration INTEGER DEFAULT 60,
                location_type TEXT CHECK (location_type IN ('in_person', 'video_call', 'phone_call', 'other')),
                color TEXT DEFAULT '#10B981',
                is_default BOOLEAN DEFAULT 0,
                created_at TEXT,
                UNIQUE(owner_id, name)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_appointment_types_owner ON shadow_appointment_types(owner_id)")

        # Add columns to tasks table
        cur.execute("PRAGMA table_info(tasks)")
        existing = {row[1] for row in cur.fetchall()}
        if "category_id" not in existing:
            cur.execute("ALTER TABLE tasks ADD COLUMN category_id INTEGER")
        if "priority" not in existing:
            cur.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'normal'")
        if "owner_id" not in existing:
            cur.execute("ALTER TABLE tasks ADD COLUMN owner_id TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id)")

        # Add columns to appointments table
        cur.execute("PRAGMA table_info(appointments)")
        existing = {row[1] for row in cur.fetchall()}
        if "type_id" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN type_id INTEGER")
        if "location" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN location TEXT")
        if "video_link" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN video_link TEXT")
        if "owner_id" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN owner_id TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_appointments_owner ON appointments(owner_id)")

        # Add owner_id to reminders table
        cur.execute("PRAGMA table_info(reminders)")
        existing = {row[1] for row in cur.fetchall()}
        if "owner_id" not in existing:
            cur.execute("ALTER TABLE reminders ADD COLUMN owner_id TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_owner ON reminders(owner_id)")

        # Add owner_id to contacts table
        cur.execute("PRAGMA table_info(contacts)")
        existing = {row[1] for row in cur.fetchall()}
        if "owner_id" not in existing:
            cur.execute("ALTER TABLE contacts ADD COLUMN owner_id TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_id)")

        self._conn.commit()

    def _upsert_conversation(
        self,
        chat_id: str | None,
        chat_type: str,
        contact_phone: str | None,
    ) -> int | None:
        if not chat_id:
            return None
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute("SELECT id, contact_phone FROM conversations WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        if row:
            existing_phone = row["contact_phone"]
            resolved_phone = contact_phone or existing_phone
            cur.execute(
                "UPDATE conversations SET last_message_at = ?, contact_phone = ? WHERE chat_id = ?",
                (now, resolved_phone, chat_id),
            )
            self._conn.commit()
            return int(row["id"])
        cur.execute(
            "INSERT INTO conversations (chat_id, chat_type, contact_phone, last_message_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_type, contact_phone, now, now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def upsert_contact(self, phone: str | None, name: str | None = None) -> None:
        if not phone:
            return
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM contacts WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE contacts SET name = COALESCE(?, name), last_interaction_at = ? WHERE phone = ?",
                (name, now, phone),
            )
        else:
            cur.execute(
                "INSERT INTO contacts (phone, name, last_interaction_at, created_at) VALUES (?, ?, ?, ?)",
                (phone, name, now, now),
            )
        self._conn.commit()

    def ingest_message(
        self,
        chat_id: str | None,
        chat_type: str,
        sender: str | None,
        sender_name: str | None,
        content: str,
        direction: str,
        is_owner: bool,
    ) -> None:
        contact_phone = None if is_owner else sender
        if not is_owner:
            self.upsert_contact(sender, sender_name)
        conversation_id = self._upsert_conversation(chat_id, chat_type, contact_phone)
        cur = self._conn.cursor()
        encrypted = self.crypto.encrypt_text(
            content,
            aad=f"msg:{chat_id}:{direction}",
        )
        cur.execute(
            "INSERT INTO messages (conversation_id, chat_id, sender_phone, direction, content, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, chat_id, sender, direction, encrypted, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def record_message(self, chat_id: str | None, sender: str | None, content: str, direction: str) -> None:
        self.ingest_message(chat_id, "direct", sender, None, content, direction, False)

    def _owner_clause(self, table_alias: str = "") -> tuple[str, list]:
        """Returns (sql_clause, params) for owner_id filtering."""
        if self.owner_id is None:
            return "", []
        prefix = f"{table_alias}." if table_alias else ""
        return f" AND {prefix}owner_id = ?", [self.owner_id]

    def list_tasks(self, limit: int = 10) -> list[Task]:
        cur = self._conn.cursor()
        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, title, due_at, status FROM tasks WHERE status = 'pending'{owner_sql} ORDER BY due_at IS NULL, due_at LIMIT ?",
            (*owner_params, limit),
        )
        return [Task(**dict(row)) for row in cur.fetchall()]

    def list_appointments(self, limit: int = 10) -> list[Appointment]:
        cur = self._conn.cursor()
        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE 1=1{owner_sql} ORDER BY scheduled_at LIMIT ?",
            (*owner_params, limit),
        )
        return [Appointment(**dict(row)) for row in cur.fetchall()]

    def create_task(self, title: str, due_at: str | None) -> Task:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO tasks (title, due_at, status, created_at, owner_id) VALUES (?, ?, 'pending', ?, ?)",
            (title, due_at, datetime.utcnow().isoformat(), self.owner_id),
        )
        self._conn.commit()
        task_id = cur.lastrowid
        return Task(id=task_id, title=title, due_at=due_at, status="pending")

    def create_appointment(self, title: str, scheduled_at: str, duration_minutes: int = 60) -> Appointment:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO appointments (title, scheduled_at, duration_minutes, created_at, owner_id) VALUES (?, ?, ?, ?, ?)",
            (title, scheduled_at, duration_minutes, datetime.utcnow().isoformat(), self.owner_id),
        )
        self._conn.commit()
        appointment_id = cur.lastrowid
        return Appointment(id=appointment_id, title=title, scheduled_at=scheduled_at, duration_minutes=duration_minutes)

    # ============== Task Management ==============

    def get_task(self, task_id: int) -> Task | None:
        """Get a task by ID."""
        cur = self._conn.cursor()
        owner_sql, owner_params = self._owner_clause()
        cur.execute(f"SELECT id, title, due_at, status FROM tasks WHERE id = ?{owner_sql}", (task_id, *owner_params))
        row = cur.fetchone()
        return Task(**dict(row)) if row else None

    def update_task(
        self,
        task_id: int,
        title: str | None = None,
        due_at: str | None = None,
        status: str | None = None,
        category_id: int | None = None,
        priority: str | None = None,
    ) -> Task | None:
        """Update a task's fields."""
        cur = self._conn.cursor()

        owner_sql, owner_params = self._owner_clause()
        cur.execute(f"SELECT id, title, due_at, status FROM tasks WHERE id = ?{owner_sql}", (task_id, *owner_params))
        row = cur.fetchone()
        if not row:
            return None

        current = dict(row)
        updates = []
        values = []

        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if due_at is not None:
            updates.append("due_at = ?")
            values.append(due_at)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if category_id is not None:
            updates.append("category_id = ?")
            values.append(category_id)
        if priority is not None:
            updates.append("priority = ?")
            values.append(priority)

        if not updates:
            return Task(**current)

        values.append(task_id)
        values.extend(owner_params)
        cur.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?{owner_sql}", values)
        self._conn.commit()

        cur.execute(f"SELECT id, title, due_at, status FROM tasks WHERE id = ?{owner_sql}", (task_id, *owner_params))
        row = cur.fetchone()
        return Task(**dict(row)) if row else None

    def complete_task(self, task_id: int) -> Task | None:
        """Mark a task as completed."""
        return self.update_task(task_id, status="completed")

    def delete_task(self, task_id: int, hard_delete: bool = False) -> dict[str, Any]:
        """Delete a task (soft or hard)."""
        cur = self._conn.cursor()

        owner_sql, owner_params = self._owner_clause()
        cur.execute(f"SELECT id, title, due_at, status FROM tasks WHERE id = ?{owner_sql}", (task_id, *owner_params))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Tarefa não encontrada"}

        task = dict(row)

        if hard_delete:
            cur.execute(f"DELETE FROM tasks WHERE id = ?{owner_sql}", (task_id, *owner_params))
        else:
            cur.execute(f"UPDATE tasks SET status = 'deleted' WHERE id = ?{owner_sql}", (task_id, *owner_params))

        self._conn.commit()

        return {
            "success": True,
            "task_id": task_id,
            "title": task["title"],
            "hard_delete": hard_delete,
        }

    # ============== Appointment Management ==============

    def get_appointment(self, appointment_id: int) -> Appointment | None:
        """Get an appointment by ID."""
        cur = self._conn.cursor()
        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?{owner_sql}",
            (appointment_id, *owner_params),
        )
        row = cur.fetchone()
        return Appointment(**dict(row)) if row else None

    def update_appointment(
        self,
        appointment_id: int,
        title: str | None = None,
        scheduled_at: str | None = None,
        duration_minutes: int | None = None,
        type_id: int | None = None,
        location: str | None = None,
    ) -> Appointment | None:
        """Update an appointment's fields."""
        cur = self._conn.cursor()

        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?{owner_sql}",
            (appointment_id, *owner_params),
        )
        row = cur.fetchone()
        if not row:
            return None

        current = dict(row)
        updates = []
        values = []

        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if scheduled_at is not None:
            updates.append("scheduled_at = ?")
            values.append(scheduled_at)
        if duration_minutes is not None:
            updates.append("duration_minutes = ?")
            values.append(duration_minutes)
        if type_id is not None:
            updates.append("type_id = ?")
            values.append(type_id)
        if location is not None:
            updates.append("location = ?")
            values.append(location)

        if not updates:
            return Appointment(**current)

        values.append(appointment_id)
        values.extend(owner_params)
        cur.execute(f"UPDATE appointments SET {', '.join(updates)} WHERE id = ?{owner_sql}", values)
        self._conn.commit()

        cur.execute(
            f"SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?{owner_sql}",
            (appointment_id, *owner_params),
        )
        row = cur.fetchone()
        return Appointment(**dict(row)) if row else None

    def delete_appointment(self, appointment_id: int) -> dict[str, Any]:
        """Delete an appointment (hard delete)."""
        cur = self._conn.cursor()

        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?{owner_sql}",
            (appointment_id, *owner_params),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Compromisso não encontrado"}

        appointment = dict(row)
        cur.execute(f"DELETE FROM appointments WHERE id = ?{owner_sql}", (appointment_id, *owner_params))
        self._conn.commit()

        return {
            "success": True,
            "appointment_id": appointment_id,
            "title": appointment["title"],
        }

    # ============== Category Management ==============

    def list_task_categories(self, owner_id: str) -> list[dict[str, Any]]:
        """List all task categories for an owner."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, name, color, icon, is_default FROM shadow_task_categories WHERE owner_id = ? ORDER BY is_default DESC, name",
            (owner_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def list_appointment_types(self, owner_id: str) -> list[dict[str, Any]]:
        """List all appointment types for an owner."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, name, default_duration, location_type, color, is_default FROM shadow_appointment_types WHERE owner_id = ? ORDER BY is_default DESC, name",
            (owner_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def create_task_category(
        self,
        owner_id: str,
        name: str,
        color: str = "#3B82F6",
        icon: str = "task",
    ) -> dict[str, Any]:
        """Create a new task category."""
        cur = self._conn.cursor()
        now = datetime.utcnow().isoformat()
        try:
            cur.execute(
                "INSERT INTO shadow_task_categories (owner_id, name, color, icon, is_default, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (owner_id, name.lower(), color, icon, now),
            )
            self._conn.commit()
            return {"success": True, "id": cur.lastrowid, "name": name}
        except sqlite3.IntegrityError:
            return {"success": False, "error": f"Categoria '{name}' já existe"}

    def create_appointment_type(
        self,
        owner_id: str,
        name: str,
        default_duration: int = 60,
        location_type: str = "other",
        color: str = "#10B981",
    ) -> dict[str, Any]:
        """Create a new appointment type."""
        cur = self._conn.cursor()
        now = datetime.utcnow().isoformat()
        try:
            cur.execute(
                "INSERT INTO shadow_appointment_types (owner_id, name, default_duration, location_type, color, is_default, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (owner_id, name.lower(), default_duration, location_type, color, now),
            )
            self._conn.commit()
            return {"success": True, "id": cur.lastrowid, "name": name}
        except sqlite3.IntegrityError:
            return {"success": False, "error": f"Tipo '{name}' já existe"}

    def get_category_by_name(self, owner_id: str, name: str, category_type: str = "task") -> dict[str, Any] | None:
        """Get a category by name (fuzzy match)."""
        cur = self._conn.cursor()
        table = "shadow_task_categories" if category_type == "task" else "shadow_appointment_types"
        # Exact match first
        cur.execute(f"SELECT * FROM {table} WHERE owner_id = ? AND LOWER(name) = LOWER(?)", (owner_id, name))
        row = cur.fetchone()
        if row:
            return dict(row)
        # Partial match
        cur.execute(f"SELECT * FROM {table} WHERE owner_id = ? AND name LIKE ? LIMIT 1", (owner_id, f"%{name.lower()}%"))
        row = cur.fetchone()
        return dict(row) if row else None

    def seed_default_categories(self, owner_id: str) -> None:
        """Seed default task categories and appointment types for an owner."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Default task categories
        task_categories = [
            ("pessoal", "#8B5CF6", "user"),
            ("trabalho", "#3B82F6", "briefcase"),
            ("compras", "#F59E0B", "shopping-cart"),
            ("saude", "#EF4444", "heart"),
            ("financeiro", "#10B981", "dollar-sign"),
            ("urgente", "#DC2626", "alert-circle"),
        ]
        for name, color, icon in task_categories:
            cur.execute(
                "INSERT OR IGNORE INTO shadow_task_categories (owner_id, name, color, icon, is_default, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                (owner_id, name, color, icon, now),
            )

        # Default appointment types
        appointment_types = [
            ("reuniao", 60, "video_call", "#3B82F6"),
            ("call", 30, "phone_call", "#10B981"),
            ("presencial", 60, "in_person", "#F59E0B"),
            ("entrevista", 45, "video_call", "#8B5CF6"),
            ("medico", 30, "in_person", "#EF4444"),
            ("social", 120, "in_person", "#EC4899"),
        ]
        for name, duration, loc_type, color in appointment_types:
            cur.execute(
                "INSERT OR IGNORE INTO shadow_appointment_types (owner_id, name, default_duration, location_type, color, is_default, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (owner_id, name, duration, loc_type, color, now),
            )

        self._conn.commit()

    # ============== User Settings ==============

    def get_user_settings(self, owner_id: str) -> dict[str, Any]:
        """Get user settings, creating defaults if not exist."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_user_settings WHERE owner_id = ?", (owner_id,))
        row = cur.fetchone()
        if row:
            settings = dict(row)
            # Convert SQLite integers to booleans
            bool_fields = [
                "auto_create_from_conversations", "group_monitoring_enabled",
                "gcal_check_conflicts", "gcal_auto_sync", "morning_summary_enabled",
                "always_ask_incomplete", "use_emojis", "verbose_responses"
            ]
            for field in bool_fields:
                if field in settings:
                    settings[field] = bool(settings[field])
            return settings
        # Create default settings
        return self.ensure_user_settings(owner_id)

    def ensure_user_settings(self, owner_id: str) -> dict[str, Any]:
        """Ensure user settings exist, creating defaults if needed."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        try:
            cur.execute(
                """INSERT INTO shadow_user_settings
                   (owner_id, created_at, updated_at) VALUES (?, ?, ?)""",
                (owner_id, now, now),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already exists
        return self.get_user_settings(owner_id)

    def update_user_settings(self, owner_id: str, **kwargs) -> dict[str, Any]:
        """Update user settings."""
        # Ensure settings exist
        self.ensure_user_settings(owner_id)

        # Convert booleans to integers for SQLite
        bool_fields = [
            "auto_create_from_conversations", "group_monitoring_enabled",
            "gcal_check_conflicts", "gcal_auto_sync", "morning_summary_enabled",
            "always_ask_incomplete", "use_emojis", "verbose_responses"
        ]
        for field in bool_fields:
            if field in kwargs:
                kwargs[field] = 1 if kwargs[field] else 0

        # Build update query
        valid_fields = [
            "auto_create_from_conversations", "group_monitoring_enabled",
            "gcal_check_conflicts", "gcal_auto_sync", "default_reminder_minutes",
            "morning_summary_enabled", "morning_summary_time", "always_ask_incomplete",
            "timezone", "language", "use_emojis", "verbose_responses"
        ]
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return self.get_user_settings(owner_id)

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [owner_id]

        cur = self._conn.cursor()
        cur.execute(
            f"UPDATE shadow_user_settings SET {set_clause} WHERE owner_id = ?",
            values,
        )
        self._conn.commit()
        return self.get_user_settings(owner_id)

    # ============== Scheduled Alerts ==============

    def create_scheduled_alert(
        self,
        owner_id: str,
        alert_time: str,
        alert_type: str = "summary",
        recurrence: str = "daily",
        days_of_week: list[int] | None = None,
        custom_message: str | None = None,
        include_tasks: bool = True,
        include_appointments: bool = True,
        include_reminders: bool = True,
        include_overdue: bool = True,
        name: str | None = None,
        timezone: str = "America/Sao_Paulo",
    ) -> dict[str, Any]:
        """Create a new scheduled alert."""
        now = datetime.utcnow().isoformat()
        days_str = ",".join(str(d) for d in (days_of_week or [1, 2, 3, 4, 5, 6, 7]))
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_scheduled_alerts
               (owner_id, alert_time, timezone, recurrence, days_of_week, alert_type,
                custom_message, include_tasks, include_appointments, include_reminders,
                include_overdue, is_active, name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                owner_id, alert_time, timezone, recurrence, days_str, alert_type,
                custom_message, int(include_tasks), int(include_appointments),
                int(include_reminders), int(include_overdue), name, now, now
            ),
        )
        self._conn.commit()
        return {
            "success": True,
            "id": cur.lastrowid,
            "alert_time": alert_time,
            "alert_type": alert_type,
            "recurrence": recurrence,
        }

    def list_scheduled_alerts(self, owner_id: str, active_only: bool = True) -> list[dict[str, Any]]:
        """List all scheduled alerts for an owner."""
        cur = self._conn.cursor()
        query = "SELECT * FROM shadow_scheduled_alerts WHERE owner_id = ?"
        params: list[Any] = [owner_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY alert_time"
        cur.execute(query, params)
        alerts = []
        for row in cur.fetchall():
            alert = dict(row)
            # Convert integers to booleans
            for field in ["include_tasks", "include_appointments", "include_reminders", "include_overdue", "is_active"]:
                if field in alert:
                    alert[field] = bool(alert[field])
            # Convert days_of_week string to list
            if alert.get("days_of_week"):
                alert["days_of_week"] = [int(d) for d in alert["days_of_week"].split(",")]
            alerts.append(alert)
        return alerts

    def get_scheduled_alert(self, owner_id: str, alert_id: int) -> dict[str, Any] | None:
        """Get a specific scheduled alert."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM shadow_scheduled_alerts WHERE owner_id = ? AND id = ?",
            (owner_id, alert_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        alert = dict(row)
        for field in ["include_tasks", "include_appointments", "include_reminders", "include_overdue", "is_active"]:
            if field in alert:
                alert[field] = bool(alert[field])
        if alert.get("days_of_week"):
            alert["days_of_week"] = [int(d) for d in alert["days_of_week"].split(",")]
        return alert

    def update_scheduled_alert(self, owner_id: str, alert_id: int, **kwargs) -> dict[str, Any] | None:
        """Update a scheduled alert."""
        # Convert booleans to integers
        bool_fields = ["include_tasks", "include_appointments", "include_reminders", "include_overdue", "is_active"]
        for field in bool_fields:
            if field in kwargs:
                kwargs[field] = 1 if kwargs[field] else 0

        # Convert days_of_week list to string
        if "days_of_week" in kwargs and isinstance(kwargs["days_of_week"], list):
            kwargs["days_of_week"] = ",".join(str(d) for d in kwargs["days_of_week"])

        valid_fields = [
            "alert_time", "timezone", "recurrence", "days_of_week", "alert_type",
            "custom_message", "include_tasks", "include_appointments", "include_reminders",
            "include_overdue", "is_active", "name", "last_sent_at", "next_scheduled_at"
        ]
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return self.get_scheduled_alert(owner_id, alert_id)

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [owner_id, alert_id]

        cur = self._conn.cursor()
        cur.execute(
            f"UPDATE shadow_scheduled_alerts SET {set_clause} WHERE owner_id = ? AND id = ?",
            values,
        )
        self._conn.commit()
        return self.get_scheduled_alert(owner_id, alert_id)

    def delete_scheduled_alert(self, owner_id: str, alert_id: int, hard_delete: bool = False) -> bool:
        """Delete or deactivate a scheduled alert."""
        cur = self._conn.cursor()
        if hard_delete:
            cur.execute(
                "DELETE FROM shadow_scheduled_alerts WHERE owner_id = ? AND id = ?",
                (owner_id, alert_id),
            )
        else:
            cur.execute(
                "UPDATE shadow_scheduled_alerts SET is_active = 0, updated_at = ? WHERE owner_id = ? AND id = ?",
                (datetime.utcnow().isoformat(), owner_id, alert_id),
            )
        self._conn.commit()
        return cur.rowcount > 0

    def get_pending_alerts(self, now_iso: str) -> list[dict[str, Any]]:
        """Get all alerts that should be sent now."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT * FROM shadow_scheduled_alerts
               WHERE is_active = 1 AND (next_scheduled_at IS NULL OR next_scheduled_at <= ?)""",
            (now_iso,),
        )
        return [dict(row) for row in cur.fetchall()]

    def record_alert_sent(self, alert_id: int, owner_id: str, content: str, success: bool = True, error: str | None = None) -> None:
        """Record that an alert was sent."""
        now = datetime.utcnow().isoformat()
        enc_content = self.crypto.encrypt_text(content, aad="alert:content")
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO shadow_alert_history (alert_id, owner_id, content, sent_at, success, error_message) VALUES (?, ?, ?, ?, ?, ?)",
            (alert_id, owner_id, enc_content, now, int(success), error),
        )
        # Update last_sent_at on the alert
        cur.execute(
            "UPDATE shadow_scheduled_alerts SET last_sent_at = ? WHERE id = ?",
            (now, alert_id),
        )
        self._conn.commit()

    # ============== Learning System ==============

    def record_feedback(
        self,
        owner_id: str,
        rating: str,
        response_text: str | None = None,
        correction_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Record user feedback on a response."""
        import json
        now = datetime.utcnow().isoformat()
        enc_response = self.crypto.encrypt_text(response_text or "", aad="feedback:response")
        enc_correction = self.crypto.encrypt_text(correction_text or "", aad="feedback:correction")
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_feedback
               (owner_id, rating, response_text, correction_text, context, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (owner_id, rating, enc_response, enc_correction, json.dumps(context or {}), now),
        )
        self._conn.commit()
        return {"id": cur.lastrowid, "rating": rating}

    def learn_pattern(
        self,
        owner_id: str,
        pattern_type: str,
        trigger_text: str | None,
        learned_action: str,
        tool_name: str | None = None,
        confidence_boost: float = 0.1,
    ) -> dict[str, Any] | None:
        """Learn or update a pattern from user correction."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Check if pattern exists
        cur.execute(
            """SELECT id, confidence, occurrences FROM shadow_learned_patterns
               WHERE owner_id = ? AND pattern_type = ?
               AND COALESCE(trigger_text, '') = COALESCE(?, '')
               AND COALESCE(tool_name, '') = COALESCE(?, '')""",
            (owner_id, pattern_type, trigger_text or '', tool_name or ''),
        )
        existing = cur.fetchone()

        if existing:
            # Update existing pattern
            new_confidence = min(existing["confidence"] + confidence_boost, 1.0)
            cur.execute(
                """UPDATE shadow_learned_patterns
                   SET confidence = ?, occurrences = ?, last_matched_at = ?, updated_at = ?
                   WHERE id = ?""",
                (new_confidence, existing["occurrences"] + 1, now, now, existing["id"]),
            )
            self._conn.commit()
            return {"id": existing["id"], "confidence": new_confidence, "updated": True}
        else:
            # Insert new pattern (use empty string for None to match unique index)
            cur.execute(
                """INSERT INTO shadow_learned_patterns
                   (owner_id, pattern_type, trigger_text, learned_action, tool_name,
                    confidence, occurrences, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0.5, 1, 1, ?, ?)""",
                (owner_id, pattern_type, trigger_text or '', learned_action, tool_name or '', now, now),
            )
            self._conn.commit()
            return {"id": cur.lastrowid, "confidence": 0.5, "updated": False}

    def get_learned_patterns(
        self,
        owner_id: str,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Get learned patterns for a user."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT pattern_type, trigger_text, learned_action, tool_name, confidence
               FROM shadow_learned_patterns
               WHERE owner_id = ? AND is_active = 1 AND confidence >= ?
               ORDER BY confidence DESC, occurrences DESC""",
            (owner_id, min_confidence),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_learned_preference(
        self,
        owner_id: str,
        key: str,
        value: str,
        source: str = "auto",
        confidence_boost: float = 0.1,
    ) -> None:
        """Update or insert a learned preference."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Check if preference exists
        cur.execute(
            "SELECT id, confidence, evidence_count FROM shadow_user_preferences_learned WHERE owner_id = ? AND preference_key = ?",
            (owner_id, key),
        )
        existing = cur.fetchone()

        if existing:
            # Update existing
            new_confidence = 1.0 if source == "explicit" else min(existing["confidence"] + confidence_boost, 1.0)
            cur.execute(
                """UPDATE shadow_user_preferences_learned
                   SET preference_value = ?, confidence = ?, evidence_count = ?,
                   last_observed_at = ?, source = CASE WHEN ? = 'explicit' THEN 'explicit' ELSE source END,
                   updated_at = ?
                   WHERE id = ?""",
                (value, new_confidence, existing["evidence_count"] + 1, now, source, now, existing["id"]),
            )
        else:
            # Insert new
            confidence = 1.0 if source == "explicit" else 0.5
            cur.execute(
                """INSERT INTO shadow_user_preferences_learned
                   (owner_id, preference_key, preference_value, confidence, evidence_count,
                    source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                (owner_id, key, value, confidence, source, now, now),
            )
        self._conn.commit()

    def get_learned_preferences(
        self,
        owner_id: str,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Get learned preferences for a user."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT preference_key, preference_value, confidence, source
               FROM shadow_user_preferences_learned
               WHERE owner_id = ? AND confidence >= ?
               ORDER BY confidence DESC""",
            (owner_id, min_confidence),
        )
        return [dict(row) for row in cur.fetchall()]

    def create_reminder(
        self,
        remind_at: str,
        message: str,
        task_id: int | None = None,
        appointment_id: int | None = None,
        target_phone: str | None = None,
    ) -> None:
        enc_message = self.crypto.encrypt_text(message, aad="reminder:message")
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO reminders (remind_at, message, task_id, appointment_id, sent, created_at, owner_id) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (remind_at, enc_message, task_id, appointment_id, datetime.utcnow().isoformat(), self.owner_id),
        )
        self._conn.commit()

    def pending_reminders(self, now_iso: str) -> Iterable[dict]:
        cur = self._conn.cursor()
        owner_sql, owner_params = self._owner_clause()
        cur.execute(
            f"SELECT id, remind_at, message FROM reminders WHERE sent = 0 AND remind_at <= ?{owner_sql}",
            (now_iso, *owner_params),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["message"] = self.crypto.decrypt_text(row.get("message", ""), aad="reminder:message")
        return rows

    def mark_reminder_sent(self, reminder_id: int) -> None:
        cur = self._conn.cursor()
        cur.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        self._conn.commit()

    def record_interaction(self, user_phone: str | None, user_message: str, reply: str, intent: str) -> None:
        enc_message = self.crypto.encrypt_text(user_message, aad="interaction:user_message")
        enc_reply = self.crypto.encrypt_text(reply, aad="interaction:shadow_response")
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO interactions (user_phone, user_message, shadow_response, intent, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_phone, enc_message, enc_reply, intent, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def get_config(self, key: str) -> str | None:
        """Retorna um valor de configuração do Shadow."""
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM shadow_config WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_config(self, key: str, value: str) -> None:
        """Define um valor de configuração do Shadow."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO shadow_config (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?",
            (key, value, now, value, now),
        )
        self._conn.commit()

    def get_shadow_group_jid(self) -> str | None:
        """Retorna o JID do grupo Shadow se existir."""
        return self.get_config("shadow_group_jid")

    def set_shadow_group_jid(self, group_jid: str) -> None:
        """Salva o JID do grupo Shadow."""
        self.set_config("shadow_group_jid", group_jid)

    def list_contact_timeline(self, phone: str, limit: int = 20) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT messages.content, messages.direction, messages.timestamp
            FROM messages
            JOIN conversations ON conversations.id = messages.conversation_id
            WHERE conversations.contact_phone = ?
            ORDER BY messages.timestamp DESC
            LIMIT ?
            """,
            (phone, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["content"] = self.crypto.decrypt_text(row.get("content", ""), aad=None)
        return rows

    def list_recent_contacts(self, limit: int = 20) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT phone, name, last_interaction_at
            FROM contacts
            ORDER BY last_interaction_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ========== Entity Extraction Methods ==========

    def save_extracted_entity(
        self,
        owner_id: str,
        source_chat_id: str,
        source_message_id: str | None,
        entity_type: str,
        entity_data: dict[str, Any],
        confidence: float = 0.8,
        sender_phone: str | None = None,
        sender_name: str | None = None,
    ) -> int:
        """Save an extracted entity and return its ID.

        Args:
            owner_id: Owner's phone number
            source_chat_id: Chat JID/LID where entity was extracted
            source_message_id: Message ID (optional)
            entity_type: Type of entity (task, meeting, contact, reminder)
            entity_data: Extracted data from LLM
            confidence: Confidence score 0-1
            sender_phone: REAL sender phone (E.164) - not from entity_data
            sender_name: REAL sender name (push name) - not from entity_data
        """
        import json
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO shadow_extracted_entities
            (owner_id, source_chat_id, source_message_id, entity_type, entity_data,
             confidence, sender_phone, sender_name, extracted_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (owner_id, source_chat_id, source_message_id, entity_type,
             json.dumps(entity_data), confidence, sender_phone, sender_name, now, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_contact_context(
        self,
        owner_id: str,
        contact_phone: str,
        contact_name: str | None = None,
        message: str | None = None,
    ) -> None:
        """Update or create contact context with new interaction."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, interaction_count, message_count FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, contact_phone),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE shadow_contact_context
                SET contact_name = COALESCE(?, contact_name),
                    last_interaction = ?,
                    interaction_count = interaction_count + 1,
                    message_count = message_count + 1,
                    updated_at = ?
                WHERE owner_id = ? AND contact_phone = ?
                """,
                (contact_name, now, now, owner_id, contact_phone),
            )
        else:
            cur.execute(
                """
                INSERT INTO shadow_contact_context
                (owner_id, contact_phone, contact_name, last_interaction, interaction_count, message_count, first_seen, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (owner_id, contact_phone, contact_name, now, now, now),
            )
        self._conn.commit()

    def get_contact_context(
        self,
        owner_id: str,
        contact_phone: str | None = None,
        contact_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for a specific contact by phone or name."""
        cur = self._conn.cursor()
        if contact_phone:
            cur.execute(
                "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?",
                (owner_id, contact_phone),
            )
        elif contact_name:
            cur.execute(
                "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_name LIKE ?",
                (owner_id, f"%{contact_name}%"),
            )
        else:
            return None
        row = cur.fetchone()
        return dict(row) if row else None

    def update_contact_context_fields(
        self,
        owner_id: str,
        contact_phone: str,
        fields: dict[str, Any],
    ) -> bool:
        """
        Update specific fields in contact context.

        Phase 8F: CRM Oculto - Context update contínuo.
        Updates specific fields without resetting counters.

        Args:
            owner_id: Owner phone E.164
            contact_phone: Contact phone
            fields: Dict of fields to update (topics, email, company, etc)

        Returns:
            True if updated successfully
        """
        if not fields:
            return False

        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Check if context exists
        cur.execute(
            "SELECT id FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, contact_phone),
        )
        row = cur.fetchone()
        if not row:
            return False

        # Build update query dynamically
        # Only allow specific safe fields
        safe_fields = {
            "topics", "summary", "sentiment", "email", "company",
            "role", "has_pending_tasks", "has_pending_appointments",
            "relationship_type", "notes"
        }

        updates = []
        values = []
        for key, value in fields.items():
            if key in safe_fields:
                # Convert lists/dicts to JSON
                if isinstance(value, (list, dict)):
                    import json
                    value = json.dumps(value)
                elif isinstance(value, bool):
                    value = 1 if value else 0

                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return False

        # Add updated_at
        updates.append("updated_at = ?")
        values.append(now)

        # Add WHERE clause values
        values.extend([owner_id, contact_phone])

        query = f"""
            UPDATE shadow_contact_context
            SET {', '.join(updates)}
            WHERE owner_id = ? AND contact_phone = ?
        """

        cur.execute(query, values)
        self._conn.commit()
        return cur.rowcount > 0

    def list_tasks_for_contact(
        self,
        owner_id: str,
        contact_identifier: str,
    ) -> list[dict[str, Any]]:
        """List tasks related to a contact (by phone or name)."""
        cur = self._conn.cursor()
        # First check task_contacts table
        cur.execute(
            """
            SELECT DISTINCT t.id, t.title, t.due_at, t.status, tc.relation_type
            FROM tasks t
            JOIN shadow_task_contacts tc ON tc.task_id = t.id
            WHERE tc.contact_phone = ? OR tc.contact_name LIKE ?
            ORDER BY t.due_at IS NULL, t.due_at
            """,
            (contact_identifier, f"%{contact_identifier}%"),
        )
        results = [dict(row) for row in cur.fetchall()]

        # Also check extracted entities
        import json
        cur.execute(
            """
            SELECT entity_data, confidence, extracted_at
            FROM shadow_extracted_entities
            WHERE owner_id = ? AND entity_type = 'task'
            AND (entity_data LIKE ? OR entity_data LIKE ?)
            ORDER BY extracted_at DESC
            LIMIT 20
            """,
            (owner_id, f'%"{contact_identifier}"%', f"%{contact_identifier}%"),
        )
        for row in cur.fetchall():
            data = json.loads(row["entity_data"])
            results.append({
                "title": data.get("description", ""),
                "due_at": data.get("due_date"),
                "status": "extracted",
                "confidence": row["confidence"],
                "extracted_at": row["extracted_at"],
            })
        return results

    def list_today_tasks_with_contacts(self, owner_id: str) -> list[dict[str, Any]]:
        """List today's tasks with related contact information."""
        import json
        from datetime import date
        today = date.today().isoformat()
        cur = self._conn.cursor()

        # Get tasks from tasks table
        cur.execute(
            """
            SELECT t.id, t.title, t.due_at, t.status
            FROM tasks t
            WHERE t.status = 'pending'
            AND (t.due_at IS NULL OR t.due_at LIKE ?)
            ORDER BY t.due_at IS NULL, t.due_at
            """,
            (f"{today}%",),
        )
        tasks = []
        for row in cur.fetchall():
            task = dict(row)
            # Get related contacts
            cur.execute(
                "SELECT contact_phone, contact_name, relation_type FROM shadow_task_contacts WHERE task_id = ?",
                (row["id"],),
            )
            task["contacts"] = [dict(c) for c in cur.fetchall()]
            tasks.append(task)

        # Get extracted task entities for today
        cur.execute(
            """
            SELECT entity_data, confidence, extracted_at, source_chat_id
            FROM shadow_extracted_entities
            WHERE owner_id = ? AND entity_type = 'task'
            AND extracted_at LIKE ?
            ORDER BY extracted_at DESC
            """,
            (owner_id, f"{today}%"),
        )
        for row in cur.fetchall():
            data = json.loads(row["entity_data"])
            tasks.append({
                "title": data.get("description", ""),
                "due_at": data.get("due_date"),
                "status": "extracted",
                "confidence": row["confidence"],
                "extracted_at": row["extracted_at"],
                "source_chat_id": row["source_chat_id"],
                "contacts": [{"contact_name": data.get("assigned_to")}] if data.get("assigned_to") else [],
            })
        return tasks

    def search_conversations_with_contact(
        self,
        owner_id: str,
        contact_identifier: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search messages with a specific contact."""
        cur = self._conn.cursor()
        # Find contact phone by name if needed
        cur.execute(
            "SELECT phone FROM contacts WHERE phone = ? OR name LIKE ? LIMIT 1",
            (contact_identifier, f"%{contact_identifier}%"),
        )
        contact_row = cur.fetchone()
        contact_phone = contact_row["phone"] if contact_row else contact_identifier

        # Get messages
        cur.execute(
            """
            SELECT m.content, m.direction, m.timestamp, c.name as contact_name
            FROM messages m
            LEFT JOIN conversations conv ON conv.id = m.conversation_id
            LEFT JOIN contacts c ON c.phone = conv.contact_phone
            WHERE conv.contact_phone = ? OR m.sender_phone = ?
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (contact_phone, contact_phone, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["content"] = self.crypto.decrypt_text(row.get("content", ""), aad=None)
        return rows

    def link_task_to_contact(
        self,
        task_id: int,
        contact_phone: str | None = None,
        contact_name: str | None = None,
        relation_type: str = "mentioned",
    ) -> None:
        """Link a task to a contact."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO shadow_task_contacts
            (task_id, contact_phone, contact_name, relation_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, contact_phone, contact_name, relation_type, now),
        )
        self._conn.commit()

    def list_extracted_entities(
        self,
        owner_id: str,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List extracted entities, optionally filtered by type."""
        import json
        cur = self._conn.cursor()
        if entity_type:
            cur.execute(
                """
                SELECT * FROM shadow_extracted_entities
                WHERE owner_id = ? AND entity_type = ?
                ORDER BY extracted_at DESC
                LIMIT ?
                """,
                (owner_id, entity_type, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM shadow_extracted_entities
                WHERE owner_id = ?
                ORDER BY extracted_at DESC
                LIMIT ?
                """,
                (owner_id, limit),
            )
        results = []
        for row in cur.fetchall():
            item = dict(row)
            item["entity_data"] = json.loads(item["entity_data"])
            results.append(item)
        return results

    # ========== Phase 5: Alias Methods ==========

    def add_contact_alias(
        self,
        owner_id: str,
        contact_phone: str,
        alias: str,
    ) -> bool:
        """Add an alias for a contact. Returns True if added, False if exists."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO shadow_contact_aliases (owner_id, contact_phone, alias, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (owner_id, contact_phone, alias.lower(), now),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_contact_alias(self, owner_id: str, alias: str) -> bool:
        """Remove an alias. Returns True if deleted."""
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM shadow_contact_aliases WHERE owner_id = ? AND alias = ?",
            (owner_id, alias.lower()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def resolve_alias(self, owner_id: str, alias: str) -> str | None:
        """Resolve an alias to a phone number."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT contact_phone FROM shadow_contact_aliases WHERE owner_id = ? AND alias = ?",
            (owner_id, alias.lower()),
        )
        row = cur.fetchone()
        return row["contact_phone"] if row else None

    def list_aliases_for_contact(self, owner_id: str, contact_phone: str) -> list[str]:
        """List all aliases for a contact."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT alias FROM shadow_contact_aliases WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, contact_phone),
        )
        return [row["alias"] for row in cur.fetchall()]

    def find_contact_by_name(
        self,
        owner_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        """Find contact by name using exact match, alias, or fuzzy search."""
        # 1. Try alias first
        phone = self.resolve_alias(owner_id, name)
        if phone:
            return self.get_contact_context(owner_id, contact_phone=phone)

        # 2. Try exact name match in contact_context
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND LOWER(contact_name) = LOWER(?)",
            (owner_id, name),
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # 3. Try fuzzy match (LIKE)
        cur.execute(
            "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_name LIKE ? LIMIT 1",
            (owner_id, f"%{name}%"),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    # ========== Phase 3: Summary Methods ==========

    def update_contact_summary(
        self,
        owner_id: str,
        contact_phone: str,
        summary: str | None = None,
        topics: list[str] | None = None,
        sentiment: str | None = None,
    ) -> None:
        """Update summary, topics, and sentiment for a contact."""
        import json
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Get current message count
        cur.execute(
            "SELECT message_count FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, contact_phone),
        )
        row = cur.fetchone()
        msg_count = row["message_count"] if row else 0

        updates = ["last_summary_at = ?", "summary_message_count = ?", "updated_at = ?"]
        values: list[Any] = [now, msg_count, now]

        if summary is not None:
            updates.append("summary = ?")
            values.append(summary)
        if topics is not None:
            updates.append("topics = ?")
            values.append(json.dumps(topics))
        if sentiment is not None:
            updates.append("sentiment = ?")
            values.append(sentiment)

        values.extend([owner_id, contact_phone])
        cur.execute(
            f"""
            UPDATE shadow_contact_context
            SET {', '.join(updates)}
            WHERE owner_id = ? AND contact_phone = ?
            """,
            values,
        )
        self._conn.commit()

    def should_update_summary(self, owner_id: str, contact_phone: str, interval: int = 10) -> bool:
        """Check if summary should be updated (every N messages since last summary)."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT message_count, summary_message_count FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, contact_phone),
        )
        row = cur.fetchone()
        if not row:
            return False
        current = row["message_count"] or 0
        last_summary = row["summary_message_count"] or 0
        return (current - last_summary) >= interval

    # ========== Phase 6: Memory Methods (SQLite backup) ==========

    def save_contact_memory(
        self,
        owner_id: str,
        text: str,
        contact_phone: str | None = None,
        category: str = "interaction",
        importance: float = 0.5,
    ) -> int:
        """Save a memory entry (backup for LanceDB)."""
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO shadow_contact_memories (owner_id, contact_phone, text, category, importance, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (owner_id, contact_phone, text, category, importance, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_contact_memories(
        self,
        owner_id: str,
        contact_phone: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List memories, optionally filtered by contact and category."""
        cur = self._conn.cursor()
        query = "SELECT * FROM shadow_contact_memories WHERE owner_id = ?"
        params: list[Any] = [owner_id]

        if contact_phone:
            query += " AND contact_phone = ?"
            params.append(contact_phone)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    # ========== Phase 1 CRM: Contact Management ==========

    def delete_contact(
        self,
        owner_id: str,
        identifier: str,
        hard_delete: bool = False,
    ) -> dict[str, Any]:
        """
        Delete a contact (soft delete by default).
        Returns info about the deleted contact.
        """
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Find contact by phone or name
        cur.execute(
            """
            SELECT * FROM shadow_contact_context
            WHERE owner_id = ? AND deleted_at IS NULL
            AND (contact_phone = ? OR LOWER(contact_name) LIKE LOWER(?))
            """,
            (owner_id, identifier, f"%{identifier}%"),
        )
        row = cur.fetchone()

        if not row:
            return {"success": False, "error": "Contato não encontrado"}

        contact = dict(row)
        phone = contact["contact_phone"]
        name = contact.get("contact_name") or phone

        if hard_delete:
            # Hard delete - remove all data
            cur.execute("DELETE FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ?", (owner_id, phone))
            cur.execute("DELETE FROM shadow_contact_aliases WHERE owner_id = ? AND contact_phone = ?", (owner_id, phone))
            cur.execute("DELETE FROM shadow_contact_memories WHERE owner_id = ? AND contact_phone = ?", (owner_id, phone))
            cur.execute("DELETE FROM contacts WHERE phone = ?", (phone,))
        else:
            # Soft delete
            cur.execute(
                "UPDATE shadow_contact_context SET deleted_at = ?, deleted_by = ? WHERE owner_id = ? AND contact_phone = ?",
                (now, owner_id, owner_id, phone),
            )
            cur.execute(
                "UPDATE contacts SET deleted_at = ?, deleted_by = ? WHERE phone = ?",
                (now, owner_id, phone),
            )

        self._conn.commit()
        return {
            "success": True,
            "phone": phone,
            "name": name,
            "hard_delete": hard_delete,
        }

    def restore_contact(self, owner_id: str, phone: str) -> dict[str, Any]:
        """Restore a soft-deleted contact."""
        cur = self._conn.cursor()

        cur.execute(
            "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ? AND deleted_at IS NOT NULL",
            (owner_id, phone),
        )
        row = cur.fetchone()

        if not row:
            return {"success": False, "error": "Contato não encontrado ou não está excluído"}

        cur.execute(
            "UPDATE shadow_contact_context SET deleted_at = NULL WHERE owner_id = ? AND contact_phone = ?",
            (owner_id, phone),
        )
        cur.execute("UPDATE contacts SET deleted_at = NULL WHERE phone = ?", (phone,))
        self._conn.commit()

        return {"success": True, "phone": phone, "name": row["contact_name"]}

    def merge_contacts(
        self,
        owner_id: str,
        target_phone: str,
        source_phone: str,
    ) -> dict[str, Any]:
        """
        Merge source contact into target contact.
        - Transfers aliases, memories, tasks
        - Keeps merge history for undo
        """
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Verify both contacts exist
        cur.execute(
            "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ? AND deleted_at IS NULL",
            (owner_id, target_phone),
        )
        target = cur.fetchone()
        if not target:
            return {"success": False, "error": f"Contato alvo {target_phone} não encontrado"}

        cur.execute(
            "SELECT * FROM shadow_contact_context WHERE owner_id = ? AND contact_phone = ? AND deleted_at IS NULL",
            (owner_id, source_phone),
        )
        source = cur.fetchone()
        if not source:
            return {"success": False, "error": f"Contato origem {source_phone} não encontrado"}

        # Record merge history
        cur.execute(
            """
            INSERT INTO shadow_contact_merges (owner_id, target_phone, source_phone, source_name, merged_at, merged_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (owner_id, target_phone, source_phone, source["contact_name"], now, owner_id),
        )

        # Transfer aliases
        cur.execute(
            "UPDATE shadow_contact_aliases SET contact_phone = ? WHERE owner_id = ? AND contact_phone = ?",
            (target_phone, owner_id, source_phone),
        )

        # Add source name as alias of target
        if source["contact_name"]:
            try:
                cur.execute(
                    "INSERT INTO shadow_contact_aliases (owner_id, contact_phone, alias, created_at) VALUES (?, ?, ?, ?)",
                    (owner_id, target_phone, source["contact_name"].lower(), now),
                )
            except sqlite3.IntegrityError:
                pass  # Alias already exists

        # Transfer memories
        cur.execute(
            "UPDATE shadow_contact_memories SET contact_phone = ? WHERE owner_id = ? AND contact_phone = ?",
            (target_phone, owner_id, source_phone),
        )

        # Transfer task links
        cur.execute(
            "UPDATE shadow_task_contacts SET contact_phone = ? WHERE contact_phone = ?",
            (target_phone, source_phone),
        )

        # Update message counts on target
        source_count = source["message_count"] or 0
        source_interactions = source["interaction_count"] or 0
        cur.execute(
            """
            UPDATE shadow_contact_context
            SET message_count = message_count + ?,
                interaction_count = interaction_count + ?
            WHERE owner_id = ? AND contact_phone = ?
            """,
            (source_count, source_interactions, owner_id, target_phone),
        )

        # Soft delete source
        cur.execute(
            "UPDATE shadow_contact_context SET deleted_at = ? WHERE owner_id = ? AND contact_phone = ?",
            (now, owner_id, source_phone),
        )

        self._conn.commit()

        return {
            "success": True,
            "target_phone": target_phone,
            "target_name": target["contact_name"],
            "source_phone": source_phone,
            "source_name": source["contact_name"],
            "aliases_transferred": True,
            "memories_transferred": True,
        }

    def find_duplicate_contacts(
        self,
        owner_id: str,
        threshold: float = 0.7,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find potential duplicate contacts using multiple detection strategies.

        Detection priority:
        1. EMAIL MATCH (100% confidence) - Same email = same person
        2. NAME + SAME DDD (high confidence) - Similar name + same area code
        3. NAME SIMILARITY ONLY (lower confidence) - Similar names

        Args:
            owner_id: The owner's phone number
            threshold: Minimum name similarity (0.0 to 1.0)
            limit: Maximum results to return

        Returns:
            List of potential duplicates with type, confidence, and contact info
        """
        cur = self._conn.cursor()

        # Get all active contacts with email
        cur.execute(
            """
            SELECT contact_phone, contact_name, email FROM shadow_contact_context
            WHERE owner_id = ? AND deleted_at IS NULL
            """,
            (owner_id,),
        )
        contacts = [dict(row) for row in cur.fetchall()]

        if len(contacts) < 2:
            return []

        duplicates = []
        seen_pairs = set()  # Avoid duplicate pairs

        def add_duplicate(c1: dict, c2: dict, match_type: str, confidence: float) -> None:
            """Add a duplicate pair if not already seen."""
            pair_key = tuple(sorted([c1["contact_phone"], c2["contact_phone"]]))
            if pair_key in seen_pairs:
                return
            seen_pairs.add(pair_key)
            duplicates.append({
                "phone_a": c1["contact_phone"],
                "name_a": c1["contact_name"],
                "email_a": c1.get("email"),
                "phone_b": c2["contact_phone"],
                "name_b": c2["contact_name"],
                "email_b": c2.get("email"),
                "type": match_type,
                "similarity": round(confidence, 2),
            })

        # 1. EMAIL MATCHES (highest priority, 100% confidence)
        email_groups: dict[str, list[dict]] = {}
        for contact in contacts:
            email = (contact.get("email") or "").lower().strip()
            if email:
                email_groups.setdefault(email, []).append(contact)

        for email, group in email_groups.items():
            if len(group) > 1:
                # All contacts with same email are duplicates
                for i, c1 in enumerate(group):
                    for c2 in group[i + 1:]:
                        add_duplicate(c1, c2, "email_match", 1.0)

        # 2. NAME SIMILARITY (with DDD boost)
        for i, c1 in enumerate(contacts):
            for c2 in contacts[i + 1:]:
                name1 = (c1["contact_name"] or "").lower()
                name2 = (c2["contact_name"] or "").lower()

                if not name1 or not name2:
                    continue

                # Calculate base similarity
                base_similarity = self._name_similarity(name1, name2)

                if base_similarity < threshold:
                    continue

                # Check if same DDD (area code) - Brazilian phones: +55XX...
                phone1 = c1["contact_phone"] or ""
                phone2 = c2["contact_phone"] or ""
                ddd1 = phone1[3:5] if len(phone1) >= 5 else ""
                ddd2 = phone2[3:5] if len(phone2) >= 5 else ""
                same_ddd = ddd1 and ddd2 and ddd1 == ddd2

                if same_ddd:
                    # Same DDD + similar name = higher confidence
                    match_type = "name_same_ddd"
                    # Boost similarity by 10% for same DDD
                    confidence = min(1.0, base_similarity + 0.1)
                else:
                    match_type = "name_similar"
                    confidence = base_similarity

                add_duplicate(c1, c2, match_type, confidence)

        # Sort by similarity descending, email matches first
        type_priority = {"email_match": 0, "name_same_ddd": 1, "name_similar": 2}
        duplicates.sort(key=lambda x: (type_priority.get(x["type"], 99), -x["similarity"]))

        return duplicates[:limit]

    def _name_similarity(self, s1: str, s2: str) -> float:
        """Calculate name similarity using various heuristics."""
        # Exact match
        if s1 == s2:
            return 1.0

        # One is substring of another
        if s1 in s2 or s2 in s1:
            return 0.9

        # First name match
        parts1 = s1.split()
        parts2 = s2.split()
        if parts1 and parts2 and parts1[0] == parts2[0]:
            return 0.8

        # Levenshtein distance
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0

        # Simple Levenshtein
        if len1 > len2:
            s1, s2 = s2, s1
            len1, len2 = len2, len1

        distances = range(len1 + 1)
        for i2, c2 in enumerate(s2):
            new_distances = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    new_distances.append(distances[i1])
                else:
                    new_distances.append(1 + min((distances[i1], distances[i1 + 1], new_distances[-1])))
            distances = new_distances

        distance = distances[-1]
        max_len = max(len1, len2)
        return 1.0 - (distance / max_len)

    def list_deleted_contacts(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List soft-deleted contacts for potential restoration."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT contact_phone, contact_name, deleted_at
            FROM shadow_contact_context
            WHERE owner_id = ? AND deleted_at IS NOT NULL
            ORDER BY deleted_at DESC
            LIMIT ?
            """,
            (owner_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def list_contact_merges(self, owner_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """List merge history."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM shadow_contact_merges
            WHERE owner_id = ?
            ORDER BY merged_at DESC
            LIMIT ?
            """,
            (owner_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    # ========== Phase 7: Proactive Suggestions ==========

    def _ensure_suggestions_schema(self) -> None:
        """Ensure suggestions tables exist (called during init)."""
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id INTEGER,
                source_chat_id TEXT,
                source_message_id TEXT,
                suggestion_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                suggestion_data TEXT,
                confidence REAL DEFAULT 0.5,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                batch_id TEXT,
                send_after TEXT,
                expires_at TEXT,
                sent_at TEXT,
                resolved_at TEXT,
                response_message_id TEXT,
                response_text TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_owner_status ON shadow_suggestions(owner_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_pending ON shadow_suggestions(status, send_after, priority DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_suggestion_daily_counts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                date TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                accepted_count INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(owner_id, date)
            )
            """
        )
        self._conn.commit()

    def create_suggestion(
        self,
        owner_id: str,
        source_type: str,
        source_id: int | None,
        suggestion_type: str,
        title: str,
        body: str | None,
        suggestion_data: dict[str, Any],
        confidence: float,
        priority: int = 0,
        source_chat_id: str | None = None,
        source_message_id: str | None = None,
        send_after: str | None = None,
        expires_at: str | None = None,
    ) -> int:
        """Create a new suggestion and return its ID."""
        import json
        self._ensure_suggestions_schema()
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO shadow_suggestions
            (owner_id, source_type, source_id, source_chat_id, source_message_id,
             suggestion_type, title, body, suggestion_data, confidence, priority,
             status, send_after, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (owner_id, source_type, source_id, source_chat_id, source_message_id,
             suggestion_type, title, body, json.dumps(suggestion_data), confidence, priority,
             send_after, expires_at, now, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_suggestion(self, suggestion_id: int) -> dict[str, Any] | None:
        """Get a suggestion by ID."""
        self._ensure_suggestions_schema()
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_suggestions WHERE id = ?", (suggestion_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_pending_suggestions(
        self,
        owner_id: str,
        limit: int = 10,
        min_priority: int = 0,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        """Get pending suggestions ready to send."""
        self._ensure_suggestions_schema()
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM shadow_suggestions
            WHERE owner_id = ? AND status = ? AND priority >= ?
            AND (send_after IS NULL OR send_after <= ?)
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (owner_id, status, min_priority, now, now, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_sent_suggestions(
        self,
        owner_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get suggestions that were sent and await response."""
        self._ensure_suggestions_schema()
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM shadow_suggestions
            WHERE owner_id = ? AND status = 'sent'
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (owner_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_suggestion_status(
        self,
        suggestion_id: int,
        status: str,
        response_text: str | None = None,
        response_message_id: str | None = None,
    ) -> bool:
        """Update suggestion status."""
        self._ensure_suggestions_schema()
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        resolved_at = now if status in ("accepted", "rejected", "expired") else None

        cur.execute(
            """
            UPDATE shadow_suggestions
            SET status = ?, response_text = ?, response_message_id = ?,
                resolved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, response_text, response_message_id, resolved_at, now, suggestion_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_suggestion_sent(self, suggestion_id: int) -> bool:
        """Mark a suggestion as sent."""
        self._ensure_suggestions_schema()
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE shadow_suggestions
            SET status = 'sent', sent_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, suggestion_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_entity_processed(self, entity_id: int, processed: bool = True) -> bool:
        """Mark an extracted entity as processed."""
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE shadow_extracted_entities
            SET processed = ?
            WHERE id = ?
            """,
            (1 if processed else 0, entity_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_unprocessed_entities(
        self,
        owner_id: str,
        entity_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get unprocessed entities for suggestion creation."""
        import json
        cur = self._conn.cursor()
        if entity_type:
            cur.execute(
                """
                SELECT * FROM shadow_extracted_entities
                WHERE owner_id = ? AND entity_type = ? AND processed = 0 AND confidence >= ?
                ORDER BY confidence DESC, extracted_at DESC
                LIMIT ?
                """,
                (owner_id, entity_type, min_confidence, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM shadow_extracted_entities
                WHERE owner_id = ? AND processed = 0 AND confidence >= ?
                ORDER BY confidence DESC, extracted_at DESC
                LIMIT ?
                """,
                (owner_id, min_confidence, limit),
            )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("entity_data"):
                try:
                    d["entity_data"] = json.loads(d["entity_data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_suggestion_daily_count(self, owner_id: str, date: str | None = None) -> dict[str, Any]:
        """Get daily suggestion count for rate limiting."""
        self._ensure_suggestions_schema()
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM shadow_suggestion_daily_counts
            WHERE owner_id = ? AND date = ?
            """,
            (owner_id, date),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return {"owner_id": owner_id, "date": date, "sent_count": 0, "accepted_count": 0, "rejected_count": 0}

    def increment_suggestion_count(
        self,
        owner_id: str,
        count_type: str = "sent",
        date: str | None = None,
    ) -> None:
        """Increment daily suggestion count (sent/accepted/rejected)."""
        self._ensure_suggestions_schema()
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()

        # Upsert pattern
        cur.execute(
            """
            INSERT INTO shadow_suggestion_daily_counts (owner_id, date, sent_count, accepted_count, rejected_count, created_at)
            VALUES (?, ?, 0, 0, 0, ?)
            ON CONFLICT(owner_id, date) DO NOTHING
            """,
            (owner_id, date, now),
        )

        column = f"{count_type}_count"
        if column not in ("sent_count", "accepted_count", "rejected_count"):
            column = "sent_count"

        cur.execute(
            f"""
            UPDATE shadow_suggestion_daily_counts
            SET {column} = {column} + 1
            WHERE owner_id = ? AND date = ?
            """,
            (owner_id, date),
        )
        self._conn.commit()

    def expire_old_suggestions(self, owner_id: str | None = None) -> int:
        """Expire suggestions past their expiry time. Returns count expired."""
        self._ensure_suggestions_schema()
        now = datetime.utcnow().isoformat()
        cur = self._conn.cursor()
        if owner_id:
            cur.execute(
                """
                UPDATE shadow_suggestions
                SET status = 'expired', resolved_at = ?, updated_at = ?
                WHERE owner_id = ? AND status IN ('pending', 'sent')
                AND expires_at IS NOT NULL AND expires_at < ?
                """,
                (now, now, owner_id, now),
            )
        else:
            cur.execute(
                """
                UPDATE shadow_suggestions
                SET status = 'expired', resolved_at = ?, updated_at = ?
                WHERE status IN ('pending', 'sent')
                AND expires_at IS NOT NULL AND expires_at < ?
                """,
                (now, now, now),
            )
        self._conn.commit()
        return cur.rowcount

    def get_monitored_groups(self, owner_id: str) -> list[str]:
        """Get list of monitored group JIDs for this owner."""
        settings = self.get_user_settings(owner_id)
        monitored = settings.get("monitored_groups", [])
        if isinstance(monitored, str):
            import json
            try:
                monitored = json.loads(monitored)
            except (json.JSONDecodeError, TypeError):
                monitored = []
        return monitored

    def add_monitored_group(self, owner_id: str, group_jid: str) -> bool:
        """Add a group to monitored list."""
        import json
        settings = self.get_user_settings(owner_id)
        monitored = settings.get("monitored_groups", [])
        if isinstance(monitored, str):
            try:
                monitored = json.loads(monitored)
            except (json.JSONDecodeError, TypeError):
                monitored = []
        if group_jid not in monitored:
            monitored.append(group_jid)
            self.update_user_settings(owner_id, {"monitored_groups": json.dumps(monitored)})
            return True
        return False

    # ── API Usage Tracking (Migration 029) ──────────────────────────

    def _migrate_api_usage(self, cur: sqlite3.Cursor) -> None:
        """Add API usage tracking tables (migration 029)."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shadow_api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                session_id TEXT,
                operation TEXT,
                cost_usd REAL DEFAULT 0.0,
                latency_ms INTEGER,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_provider ON shadow_api_usage(provider)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_created ON shadow_api_usage(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_session ON shadow_api_usage(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_operation ON shadow_api_usage(operation)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS shadow_provider_pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_price_per_mtok REAL NOT NULL,
                output_price_per_mtok REAL NOT NULL,
                effective_from TEXT DEFAULT (datetime('now')),
                UNIQUE(provider, model)
            )
        """)

        # Seed default pricing
        defaults = [
            ('anthropic', 'claude-sonnet-4-20250514', 3.0, 15.0),
            ('anthropic', 'claude-haiku-3-20240307', 0.25, 1.25),
            ('google', 'gemini-2.5-flash-lite', 0.0, 0.0),
            ('google', 'gemini-2.0-flash', 0.10, 0.40),
            ('openai', 'text-embedding-3-small', 0.02, 0.0),
        ]
        for provider, model, inp, out in defaults:
            cur.execute(
                "INSERT OR IGNORE INTO shadow_provider_pricing (provider, model, input_price_per_mtok, output_price_per_mtok) VALUES (?, ?, ?, ?)",
                (provider, model, inp, out),
            )
        self._conn.commit()

    def record_api_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        operation: str = "",
        session_id: str = "",
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        success: bool = True,
        error_message: str = "",
    ) -> None:
        """Registra um evento de uso de API."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_api_usage
               (provider, model, input_tokens, output_tokens, session_id, operation, cost_usd, latency_ms, success, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (provider, model, input_tokens, output_tokens, session_id, operation, cost_usd, latency_ms, 1 if success else 0, error_message),
        )
        self._conn.commit()

    def get_usage_summary(self, days: int = 30) -> list[dict[str, Any]]:
        """Retorna resumo de uso agrupado por provider."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT provider, model,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(cost_usd) as total_cost,
                      COUNT(*) as call_count,
                      AVG(latency_ms) as avg_latency,
                      SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count
               FROM shadow_api_usage
               WHERE created_at >= datetime('now', ?)
               GROUP BY provider, model
               ORDER BY total_cost DESC""",
            (f"-{days} days",),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_usage_history(self, days: int = 30, provider: str = "") -> list[dict[str, Any]]:
        """Retorna uso diario ao longo do tempo."""
        cur = self._conn.cursor()
        if provider:
            cur.execute(
                """SELECT date(created_at) as day, provider,
                          SUM(input_tokens) as input_tokens,
                          SUM(output_tokens) as output_tokens,
                          SUM(cost_usd) as cost,
                          COUNT(*) as calls
                   FROM shadow_api_usage
                   WHERE created_at >= datetime('now', ?) AND provider = ?
                   GROUP BY day, provider
                   ORDER BY day""",
                (f"-{days} days", provider),
            )
        else:
            cur.execute(
                """SELECT date(created_at) as day, provider,
                          SUM(input_tokens) as input_tokens,
                          SUM(output_tokens) as output_tokens,
                          SUM(cost_usd) as cost,
                          COUNT(*) as calls
                   FROM shadow_api_usage
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY day, provider
                   ORDER BY day""",
                (f"-{days} days",),
            )
        return [dict(row) for row in cur.fetchall()]

    def get_provider_pricing(self) -> list[dict[str, Any]]:
        """Retorna configuracao de precos por provider/modelo."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_provider_pricing ORDER BY provider, model")
        return [dict(row) for row in cur.fetchall()]

    def update_provider_pricing(self, provider: str, model: str, input_price: float, output_price: float) -> None:
        """Atualiza preco de um provider/modelo."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_provider_pricing (provider, model, input_price_per_mtok, output_price_per_mtok)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(provider, model) DO UPDATE SET
               input_price_per_mtok = excluded.input_price_per_mtok,
               output_price_per_mtok = excluded.output_price_per_mtok,
               effective_from = datetime('now')""",
            (provider, model, input_price, output_price),
        )
        self._conn.commit()

    def remove_monitored_group(self, owner_id: str, group_jid: str) -> bool:
        """Remove a group from monitored list."""
        import json
        settings = self.get_user_settings(owner_id)
        monitored = settings.get("monitored_groups", [])
        if isinstance(monitored, str):
            try:
                monitored = json.loads(monitored)
            except (json.JSONDecodeError, TypeError):
                monitored = []
        if group_jid in monitored:
            monitored.remove(group_jid)
            self.update_user_settings(owner_id, {"monitored_groups": json.dumps(monitored)})
            return True
        return False

    # ── Instance Management ──

    def create_instance(self, instance_id: str, name: str, gateway_user_id: str) -> dict:
        """Create a new instance record."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO shadow_instances (id, name, gateway_user_id, created_at) VALUES (?, ?, ?, ?)",
            (instance_id, name, gateway_user_id, now),
        )
        self._conn.commit()
        return self.get_instance(instance_id)

    def get_instance(self, instance_id: str) -> dict | None:
        """Get instance by ID."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_instances WHERE id = ?", (instance_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_instances(self) -> list[dict]:
        """List all instances."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_instances ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def update_instance(self, instance_id: str, **kwargs) -> dict | None:
        """Update instance fields."""
        if not kwargs:
            return self.get_instance(instance_id)
        allowed = {"name", "phone", "owner_e164", "status", "connected_at", "disconnected_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_instance(instance_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [instance_id]
        cur = self._conn.cursor()
        cur.execute(
            f"UPDATE shadow_instances SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        return self.get_instance(instance_id)

    def delete_instance(self, instance_id: str) -> bool:
        """Delete an instance."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM shadow_instances WHERE id = ?", (instance_id,))
        self._conn.commit()
        return True

    # ── Channel Tables (Migration 031) ────────────────────────────────

    def _migrate_channel_tables(self, cur: sqlite3.Cursor) -> None:
        """Create channel users, messages, and templates tables."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shadow_channel_users (
                id TEXT PRIMARY KEY,
                phone_e164 TEXT NOT NULL UNIQUE,
                owner_id TEXT NOT NULL,
                instance_id TEXT,
                display_name TEXT,
                user_type TEXT DEFAULT 'standalone',
                channel TEXT DEFAULT 'evolution',
                status TEXT DEFAULT 'active',
                last_message_at TEXT,
                last_window_opened_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                metadata TEXT DEFAULT '{}'
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_users_phone ON shadow_channel_users(phone_e164)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_users_owner ON shadow_channel_users(owner_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS shadow_channel_messages (
                id TEXT PRIMARY KEY,
                external_id TEXT UNIQUE,
                user_phone TEXT NOT NULL,
                direction TEXT NOT NULL,
                channel TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                content TEXT,
                template_name TEXT,
                status TEXT DEFAULT 'sent',
                cost_category TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_msgs_ext ON shadow_channel_messages(external_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_msgs_phone ON shadow_channel_messages(user_phone)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS shadow_channel_templates (
                id TEXT PRIMARY KEY,
                template_name TEXT NOT NULL UNIQUE,
                language TEXT DEFAULT 'pt_BR',
                category TEXT,
                status TEXT DEFAULT 'draft',
                body_text TEXT,
                components TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    # ── Channel User CRUD ─────────────────────────────────────────────

    def create_channel_user(
        self,
        phone_e164: str,
        owner_id: str,
        instance_id: str | None = None,
        display_name: str | None = None,
        user_type: str = "standalone",
        channel: str = "evolution",
        status: str = "active",
    ) -> dict:
        """Create a new channel user."""
        import uuid

        uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_channel_users
               (id, phone_e164, owner_id, instance_id, display_name, user_type, channel, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, phone_e164, owner_id, instance_id, display_name, user_type, channel, status, now),
        )
        self._conn.commit()
        return self.get_channel_user_by_phone(phone_e164) or {"id": uid}

    def get_channel_user_by_phone(self, phone_e164: str) -> dict | None:
        """Get channel user by phone number."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_channel_users WHERE phone_e164 = ?", (phone_e164,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_channel_user(self, phone_e164: str, **kwargs) -> dict | None:
        """Update channel user fields."""
        allowed = {
            "display_name", "user_type", "channel", "status",
            "instance_id", "last_message_at", "last_window_opened_at", "metadata",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_channel_user_by_phone(phone_e164)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [phone_e164]
        cur = self._conn.cursor()
        cur.execute(f"UPDATE shadow_channel_users SET {set_clause} WHERE phone_e164 = ?", values)
        self._conn.commit()
        return self.get_channel_user_by_phone(phone_e164)

    def list_channel_users(self, status: str | None = None, limit: int = 100) -> list[dict]:
        """List channel users, optionally filtered by status."""
        cur = self._conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM shadow_channel_users WHERE status = ? ORDER BY last_message_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cur.execute("SELECT * FROM shadow_channel_users ORDER BY last_message_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def find_instance_by_phone(self, phone_e164: str) -> dict | None:
        """Find an instance whose owner_e164 matches the given phone."""
        cur = self._conn.cursor()
        # Try with and without + prefix
        phone_clean = phone_e164.lstrip("+")
        cur.execute(
            "SELECT * FROM shadow_instances WHERE owner_e164 = ? OR owner_e164 = ?",
            (phone_e164, phone_clean),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    # ── Channel Message Log ───────────────────────────────────────────

    def log_channel_message(
        self,
        user_phone: str,
        direction: str,
        channel: str,
        content: str | None = None,
        external_id: str | None = None,
        message_type: str = "text",
        template_name: str | None = None,
        status: str = "sent",
        cost_category: str | None = None,
    ) -> str:
        """Log a channel message (inbound or outbound)."""
        import uuid

        msg_id = str(uuid.uuid4())
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_channel_messages
               (id, external_id, user_phone, direction, channel, message_type, content, template_name, status, cost_category)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, external_id, user_phone, direction, channel, message_type, content, template_name, status, cost_category),
        )
        self._conn.commit()
        return msg_id

    def get_channel_message_by_external_id(self, external_id: str) -> dict | None:
        """Get channel message by external_id (for dedup)."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_channel_messages WHERE external_id = ?", (external_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_channel_messages(
        self, user_phone: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """List channel messages, optionally filtered by phone."""
        cur = self._conn.cursor()
        if user_phone:
            cur.execute(
                "SELECT * FROM shadow_channel_messages WHERE user_phone = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_phone, limit, offset),
            )
        else:
            cur.execute(
                "SELECT * FROM shadow_channel_messages ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in cur.fetchall()]

    # ── Channel Templates ─────────────────────────────────────────────

    def create_channel_template(
        self,
        template_name: str,
        body_text: str,
        category: str = "UTILITY",
        language: str = "pt_BR",
        components: str | None = None,
    ) -> dict:
        """Create a channel template."""
        import uuid

        tid = str(uuid.uuid4())
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO shadow_channel_templates
               (id, template_name, language, category, status, body_text, components)
               VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
            (tid, template_name, language, category, body_text, components),
        )
        self._conn.commit()
        return {"id": tid, "template_name": template_name, "status": "draft"}

    def list_channel_templates(self) -> list[dict]:
        """List all channel templates."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM shadow_channel_templates ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def update_channel_template_status(self, template_name: str, status: str) -> dict | None:
        """Update template status (draft, submitted, approved, rejected)."""
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE shadow_channel_templates SET status = ? WHERE template_name = ?",
            (status, template_name),
        )
        self._conn.commit()
        cur.execute("SELECT * FROM shadow_channel_templates WHERE template_name = ?", (template_name,))
        row = cur.fetchone()
        return dict(row) if row else None


