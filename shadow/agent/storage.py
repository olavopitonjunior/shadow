import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import resolve_db_path
from crypto import get_crypto

try:
    from supabase import create_client
except Exception:  # optional dependency
    create_client = None


@dataclass
class Task:
    id: int | str
    title: str
    due_at: str | None
    status: str


@dataclass
class Appointment:
    id: int | str
    title: str
    scheduled_at: str
    duration_minutes: int


class SqliteStorage:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or resolve_db_path()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.crypto = get_crypto()
        self._ensure_schema()

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

        # Add columns to appointments table
        cur.execute("PRAGMA table_info(appointments)")
        existing = {row[1] for row in cur.fetchall()}
        if "type_id" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN type_id INTEGER")
        if "location" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN location TEXT")
        if "video_link" not in existing:
            cur.execute("ALTER TABLE appointments ADD COLUMN video_link TEXT")

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

    def list_tasks(self, limit: int = 10) -> list[Task]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, title, due_at, status FROM tasks WHERE status = 'pending' ORDER BY due_at IS NULL, due_at LIMIT ?",
            (limit,),
        )
        return [Task(**dict(row)) for row in cur.fetchall()]

    def list_appointments(self, limit: int = 10) -> list[Appointment]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, title, scheduled_at, duration_minutes FROM appointments ORDER BY scheduled_at LIMIT ?",
            (limit,),
        )
        return [Appointment(**dict(row)) for row in cur.fetchall()]

    def create_task(self, title: str, due_at: str | None) -> Task:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO tasks (title, due_at, status, created_at) VALUES (?, ?, 'pending', ?)",
            (title, due_at, datetime.utcnow().isoformat()),
        )
        self._conn.commit()
        task_id = cur.lastrowid
        return Task(id=task_id, title=title, due_at=due_at, status="pending")

    def create_appointment(self, title: str, scheduled_at: str, duration_minutes: int = 60) -> Appointment:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO appointments (title, scheduled_at, duration_minutes, created_at) VALUES (?, ?, ?, ?)",
            (title, scheduled_at, duration_minutes, datetime.utcnow().isoformat()),
        )
        self._conn.commit()
        appointment_id = cur.lastrowid
        return Appointment(id=appointment_id, title=title, scheduled_at=scheduled_at, duration_minutes=duration_minutes)

    # ============== Task Management ==============

    def get_task(self, task_id: int) -> Task | None:
        """Get a task by ID."""
        cur = self._conn.cursor()
        cur.execute("SELECT id, title, due_at, status FROM tasks WHERE id = ?", (task_id,))
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

        # Check if task exists
        cur.execute("SELECT id, title, due_at, status FROM tasks WHERE id = ?", (task_id,))
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
        cur.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        self._conn.commit()

        # Return updated task
        cur.execute("SELECT id, title, due_at, status FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        return Task(**dict(row)) if row else None

    def complete_task(self, task_id: int) -> Task | None:
        """Mark a task as completed."""
        return self.update_task(task_id, status="completed")

    def delete_task(self, task_id: int, hard_delete: bool = False) -> dict[str, Any]:
        """Delete a task (soft or hard)."""
        cur = self._conn.cursor()

        # Check if task exists
        cur.execute("SELECT id, title, due_at, status FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Tarefa não encontrada"}

        task = dict(row)

        if hard_delete:
            cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        else:
            cur.execute("UPDATE tasks SET status = 'deleted' WHERE id = ?", (task_id,))

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
        cur.execute(
            "SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?",
            (appointment_id,),
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

        # Check if appointment exists
        cur.execute(
            "SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?",
            (appointment_id,),
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
        cur.execute(f"UPDATE appointments SET {', '.join(updates)} WHERE id = ?", values)
        self._conn.commit()

        # Return updated appointment
        cur.execute(
            "SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?",
            (appointment_id,),
        )
        row = cur.fetchone()
        return Appointment(**dict(row)) if row else None

    def delete_appointment(self, appointment_id: int) -> dict[str, Any]:
        """Delete an appointment (hard delete)."""
        cur = self._conn.cursor()

        # Check if appointment exists
        cur.execute(
            "SELECT id, title, scheduled_at, duration_minutes FROM appointments WHERE id = ?",
            (appointment_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Compromisso não encontrado"}

        appointment = dict(row)
        cur.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
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
        # Note: SQLite version doesn't use target_phone yet (Supabase does)
        cur.execute(
            "INSERT INTO reminders (remind_at, message, task_id, appointment_id, sent, created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (remind_at, enc_message, task_id, appointment_id, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def pending_reminders(self, now_iso: str) -> Iterable[dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, remind_at, message FROM reminders WHERE sent = 0 AND remind_at <= ?",
            (now_iso,),
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


class SupabaseStorage:
    def __init__(self, url: str, key: str, owner_phone: str) -> None:
        if create_client is None:
            raise RuntimeError("supabase client not installed")
        if not owner_phone:
            raise RuntimeError("SHADOW_OWNER_E164 is required for Supabase storage")
        self.client = create_client(url, key)
        self.owner_phone = owner_phone
        self.crypto = get_crypto()
        self.user_id, self.org_id = self._ensure_owner_records(owner_phone)

    def _ensure_owner_records(self, owner_phone: str) -> tuple[str, str]:
        digits = re.sub(r"\D", "", owner_phone) or "default"
        slug = f"org-{digits}"
        org_res = self.client.table("shadow_organizations").select("id").eq("slug", slug).limit(1).execute()
        if org_res.data:
            org_id = org_res.data[0]["id"]
        else:
            org_payload = {
                "name": "Default",
                "slug": slug,
                "plan": "starter",
            }
            org_id = self.client.table("shadow_organizations").insert(org_payload).execute().data[0]["id"]

        user_res = self.client.table("shadow_users").select("id").eq("phone_number", owner_phone).limit(1).execute()
        if user_res.data:
            user_id = user_res.data[0]["id"]
        else:
            user_payload = {
                "organization_id": org_id,
                "phone_number": owner_phone,
                "whatsapp_type": "personal",
                "role_in_org": "owner",
            }
            user_id = self.client.table("shadow_users").insert(user_payload).execute().data[0]["id"]
        return user_id, org_id

    def _ensure_conversation(
        self,
        chat_id: str | None,
        chat_type: str,
        contact_id: str | None,
    ) -> str | None:
        if not chat_id:
            return None
        payload = {
            "user_id": self.user_id,
            "organization_id": self.org_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "contact_id": contact_id,
            "last_message_at": datetime.utcnow().isoformat(),
        }
        data = (
            self.client.table("shadow_conversations")
            .upsert(payload, on_conflict="user_id,chat_id")
            .execute()
            .data
        )
        if data:
            return data[0]["id"]
        return None

    def upsert_contact(self, phone: str | None, name: str | None = None) -> str | None:
        if not phone:
            return None
        payload = {
            "user_id": self.user_id,
            "organization_id": self.org_id,
            "phone_number": phone,
            "name": name or phone,
            "last_interaction_at": datetime.utcnow().isoformat(),
        }
        data = (
            self.client.table("shadow_contacts")
            .upsert(payload, on_conflict="user_id,phone_number")
            .execute()
            .data
        )
        if data:
            return data[0]["id"]
        return None

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
        contact_id = None if is_owner else self.upsert_contact(sender, sender_name)
        conversation_id = self._ensure_conversation(chat_id, chat_type, contact_id)
        encrypted = self.crypto.encrypt_text(
            content,
            user_id=self.user_id,
            aad=f"msg:{chat_id}:{direction}",
        )
        payload = {
            "conversation_id": conversation_id,
            "direction": direction,
            "content": encrypted,
            "content_type": "text",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.client.table("shadow_messages").insert(payload).execute()

    def record_message(self, chat_id: str | None, sender: str | None, content: str, direction: str) -> None:
        self.ingest_message(chat_id, "direct", sender, None, content, direction, False)

    def list_tasks(self, limit: int = 10) -> list[Task]:
        data = (
            self.client.table("shadow_tasks")
            .select("id,title,due_date,status")
            .eq("user_id", self.user_id)
            .eq("status", "pending")
            .order("due_date", desc=False)
            .limit(limit)
            .execute()
            .data
        )
        return [Task(id=row["id"], title=row["title"], due_at=row.get("due_date"), status=row["status"]) for row in data]

    def list_appointments(self, limit: int = 10) -> list[Appointment]:
        data = (
            self.client.table("shadow_appointments")
            .select("id,title,scheduled_at,duration_minutes")
            .eq("user_id", self.user_id)
            .order("scheduled_at", desc=False)
            .limit(limit)
            .execute()
            .data
        )
        return [
            Appointment(
                id=row["id"],
                title=row["title"],
                scheduled_at=row["scheduled_at"],
                duration_minutes=row.get("duration_minutes", 60),
            )
            for row in data
        ]

    def create_task(self, title: str, due_at: str | None) -> Task:
        payload = {
            "user_id": self.user_id,
            "organization_id": self.org_id,
            "title": title,
            "due_date": due_at,
            "status": "pending",
        }
        data = self.client.table("shadow_tasks").insert(payload).execute().data[0]
        return Task(id=data["id"], title=data["title"], due_at=data.get("due_date"), status=data["status"])

    def create_appointment(self, title: str, scheduled_at: str, duration_minutes: int = 60) -> Appointment:
        payload = {
            "user_id": self.user_id,
            "organization_id": self.org_id,
            "title": title,
            "scheduled_at": scheduled_at,
            "duration_minutes": duration_minutes,
        }
        data = self.client.table("shadow_appointments").insert(payload).execute().data[0]
        return Appointment(
            id=data["id"],
            title=data["title"],
            scheduled_at=data["scheduled_at"],
            duration_minutes=data.get("duration_minutes", 60),
        )

    # ============== Task Management ==============

    def get_task(self, task_id: int | str) -> Task | None:
        """Get a task by ID."""
        res = (
            self.client.table("shadow_tasks")
            .select("id,title,due_date,status")
            .eq("id", task_id)
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return Task(id=row["id"], title=row["title"], due_at=row.get("due_date"), status=row["status"])
        return None

    def update_task(
        self,
        task_id: int | str,
        title: str | None = None,
        due_at: str | None = None,
        status: str | None = None,
        category_id: str | None = None,
        priority: str | None = None,
    ) -> Task | None:
        """Update a task's fields."""
        # Check if task exists
        existing = self.get_task(task_id)
        if not existing:
            return None

        updates = {}
        if title is not None:
            updates["title"] = title
        if due_at is not None:
            updates["due_date"] = due_at
        if status is not None:
            updates["status"] = status
        if category_id is not None:
            updates["category_id"] = category_id
        if priority is not None:
            updates["priority"] = priority

        if not updates:
            return existing

        self.client.table("shadow_tasks").update(updates).eq("id", task_id).eq("user_id", self.user_id).execute()
        return self.get_task(task_id)

    def complete_task(self, task_id: int | str) -> Task | None:
        """Mark a task as completed."""
        return self.update_task(task_id, status="completed")

    def delete_task(self, task_id: int | str, hard_delete: bool = False) -> dict[str, Any]:
        """Delete a task (soft or hard)."""
        existing = self.get_task(task_id)
        if not existing:
            return {"success": False, "error": "Tarefa não encontrada"}

        if hard_delete:
            self.client.table("shadow_tasks").delete().eq("id", task_id).eq("user_id", self.user_id).execute()
        else:
            self.client.table("shadow_tasks").update({"status": "deleted"}).eq("id", task_id).eq("user_id", self.user_id).execute()

        return {
            "success": True,
            "task_id": task_id,
            "title": existing.title,
            "hard_delete": hard_delete,
        }

    # ============== Appointment Management ==============

    def get_appointment(self, appointment_id: int | str) -> Appointment | None:
        """Get an appointment by ID."""
        res = (
            self.client.table("shadow_appointments")
            .select("id,title,scheduled_at,duration_minutes")
            .eq("id", appointment_id)
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return Appointment(
                id=row["id"],
                title=row["title"],
                scheduled_at=row["scheduled_at"],
                duration_minutes=row.get("duration_minutes", 60),
            )
        return None

    def update_appointment(
        self,
        appointment_id: int | str,
        title: str | None = None,
        scheduled_at: str | None = None,
        duration_minutes: int | None = None,
        type_id: str | None = None,
        location: str | None = None,
    ) -> Appointment | None:
        """Update an appointment's fields."""
        existing = self.get_appointment(appointment_id)
        if not existing:
            return None

        updates = {}
        if title is not None:
            updates["title"] = title
        if scheduled_at is not None:
            updates["scheduled_at"] = scheduled_at
        if duration_minutes is not None:
            updates["duration_minutes"] = duration_minutes
        if type_id is not None:
            updates["type_id"] = type_id
        if location is not None:
            updates["location"] = location

        if not updates:
            return existing

        self.client.table("shadow_appointments").update(updates).eq("id", appointment_id).eq("user_id", self.user_id).execute()
        return self.get_appointment(appointment_id)

    def delete_appointment(self, appointment_id: int | str) -> dict[str, Any]:
        """Delete an appointment (hard delete)."""
        existing = self.get_appointment(appointment_id)
        if not existing:
            return {"success": False, "error": "Compromisso não encontrado"}

        self.client.table("shadow_appointments").delete().eq("id", appointment_id).eq("user_id", self.user_id).execute()

        return {
            "success": True,
            "appointment_id": appointment_id,
            "title": existing.title,
        }

    # ============== Category Management ==============

    def list_task_categories(self, owner_id: str) -> list[dict[str, Any]]:
        """List all task categories for an owner."""
        res = (
            self.client.table("shadow_task_categories")
            .select("id,name,color,icon,is_default")
            .eq("owner_id", owner_id)
            .order("is_default", desc=True)
            .order("name")
            .execute()
        )
        return res.data or []

    def list_appointment_types(self, owner_id: str) -> list[dict[str, Any]]:
        """List all appointment types for an owner."""
        res = (
            self.client.table("shadow_appointment_types")
            .select("id,name,default_duration,location_type,color,is_default")
            .eq("owner_id", owner_id)
            .order("is_default", desc=True)
            .order("name")
            .execute()
        )
        return res.data or []

    def create_task_category(
        self,
        owner_id: str,
        name: str,
        color: str = "#3B82F6",
        icon: str = "task",
    ) -> dict[str, Any]:
        """Create a new task category."""
        try:
            res = (
                self.client.table("shadow_task_categories")
                .insert({
                    "owner_id": owner_id,
                    "name": name.lower(),
                    "color": color,
                    "icon": icon,
                    "is_default": False,
                })
                .execute()
            )
            if res.data:
                return {"success": True, "id": res.data[0]["id"], "name": name}
            return {"success": False, "error": "Erro ao criar categoria"}
        except Exception as e:
            if "duplicate" in str(e).lower():
                return {"success": False, "error": f"Categoria '{name}' já existe"}
            return {"success": False, "error": str(e)}

    def create_appointment_type(
        self,
        owner_id: str,
        name: str,
        default_duration: int = 60,
        location_type: str = "other",
        color: str = "#10B981",
    ) -> dict[str, Any]:
        """Create a new appointment type."""
        try:
            res = (
                self.client.table("shadow_appointment_types")
                .insert({
                    "owner_id": owner_id,
                    "name": name.lower(),
                    "default_duration": default_duration,
                    "location_type": location_type,
                    "color": color,
                    "is_default": False,
                })
                .execute()
            )
            if res.data:
                return {"success": True, "id": res.data[0]["id"], "name": name}
            return {"success": False, "error": "Erro ao criar tipo"}
        except Exception as e:
            if "duplicate" in str(e).lower():
                return {"success": False, "error": f"Tipo '{name}' já existe"}
            return {"success": False, "error": str(e)}

    def get_category_by_name(self, owner_id: str, name: str, category_type: str = "task") -> dict[str, Any] | None:
        """Get a category by name (fuzzy match)."""
        table = "shadow_task_categories" if category_type == "task" else "shadow_appointment_types"
        # Exact match first
        res = self.client.table(table).select("*").eq("owner_id", owner_id).ilike("name", name).limit(1).execute()
        if res.data:
            return res.data[0]
        # Partial match
        res = self.client.table(table).select("*").eq("owner_id", owner_id).ilike("name", f"%{name}%").limit(1).execute()
        return res.data[0] if res.data else None

    def seed_default_categories(self, owner_id: str) -> None:
        """Seed default task categories and appointment types for an owner."""
        # Use the Supabase function
        self.client.rpc("shadow_seed_default_categories", {"p_owner_id": owner_id}).execute()

    # ============== User Settings ==============

    def get_user_settings(self, owner_id: str) -> dict[str, Any]:
        """Get user settings, creating defaults if not exist."""
        res = (
            self.client.table("shadow_user_settings")
            .select("*")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
        # Create default settings
        return self.ensure_user_settings(owner_id)

    def ensure_user_settings(self, owner_id: str) -> dict[str, Any]:
        """Ensure user settings exist, creating defaults if needed."""
        res = (
            self.client.table("shadow_user_settings")
            .upsert({"owner_id": owner_id}, on_conflict="owner_id")
            .execute()
        )
        return self.get_user_settings(owner_id)

    def update_user_settings(self, owner_id: str, **kwargs) -> dict[str, Any]:
        """Update user settings."""
        # Ensure settings exist
        self.ensure_user_settings(owner_id)

        # Filter to valid fields only
        valid_fields = [
            "auto_create_from_conversations", "group_monitoring_enabled",
            "gcal_check_conflicts", "gcal_auto_sync", "default_reminder_minutes",
            "morning_summary_enabled", "morning_summary_time", "always_ask_incomplete",
            "timezone", "language", "use_emojis", "verbose_responses"
        ]
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return self.get_user_settings(owner_id)

        self.client.table("shadow_user_settings").update(updates).eq("owner_id", owner_id).execute()
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
        payload = {
            "owner_id": owner_id,
            "alert_time": alert_time,
            "timezone": timezone,
            "recurrence": recurrence,
            "days_of_week": days_of_week or [1, 2, 3, 4, 5, 6, 7],
            "alert_type": alert_type,
            "custom_message": custom_message,
            "include_tasks": include_tasks,
            "include_appointments": include_appointments,
            "include_reminders": include_reminders,
            "include_overdue": include_overdue,
            "is_active": True,
            "name": name,
        }
        res = self.client.table("shadow_scheduled_alerts").insert(payload).execute()
        if res.data:
            return {"success": True, "id": res.data[0]["id"], **res.data[0]}
        return {"success": False, "error": "Erro ao criar alerta"}

    def list_scheduled_alerts(self, owner_id: str, active_only: bool = True) -> list[dict[str, Any]]:
        """List all scheduled alerts for an owner."""
        query = self.client.table("shadow_scheduled_alerts").select("*").eq("owner_id", owner_id)
        if active_only:
            query = query.eq("is_active", True)
        res = query.order("alert_time").execute()
        return res.data or []

    def get_scheduled_alert(self, owner_id: str, alert_id: int | str) -> dict[str, Any] | None:
        """Get a specific scheduled alert."""
        res = (
            self.client.table("shadow_scheduled_alerts")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("id", alert_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def update_scheduled_alert(self, owner_id: str, alert_id: int | str, **kwargs) -> dict[str, Any] | None:
        """Update a scheduled alert."""
        valid_fields = [
            "alert_time", "timezone", "recurrence", "days_of_week", "alert_type",
            "custom_message", "include_tasks", "include_appointments", "include_reminders",
            "include_overdue", "is_active", "name", "last_sent_at", "next_scheduled_at"
        ]
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return self.get_scheduled_alert(owner_id, alert_id)

        self.client.table("shadow_scheduled_alerts").update(updates).eq("owner_id", owner_id).eq("id", alert_id).execute()
        return self.get_scheduled_alert(owner_id, alert_id)

    def delete_scheduled_alert(self, owner_id: str, alert_id: int | str, hard_delete: bool = False) -> bool:
        """Delete or deactivate a scheduled alert."""
        if hard_delete:
            res = self.client.table("shadow_scheduled_alerts").delete().eq("owner_id", owner_id).eq("id", alert_id).execute()
        else:
            res = self.client.table("shadow_scheduled_alerts").update({"is_active": False}).eq("owner_id", owner_id).eq("id", alert_id).execute()
        return bool(res.data)

    def get_pending_alerts(self, now_iso: str) -> list[dict[str, Any]]:
        """Get all alerts that should be sent now."""
        res = (
            self.client.table("shadow_scheduled_alerts")
            .select("*")
            .eq("is_active", True)
            .or_(f"next_scheduled_at.is.null,next_scheduled_at.lte.{now_iso}")
            .execute()
        )
        return res.data or []

    def record_alert_sent(self, alert_id: int | str, owner_id: str, content: str, success: bool = True, error: str | None = None) -> None:
        """Record that an alert was sent."""
        now = datetime.utcnow().isoformat()
        enc_content = self.crypto.encrypt_text(content, user_id=self.user_id, aad="alert:content")
        # Insert into history
        self.client.table("shadow_alert_history").insert({
            "alert_id": alert_id,
            "owner_id": owner_id,
            "content": enc_content,
            "sent_at": now,
            "success": success,
            "error_message": error,
        }).execute()
        # Update last_sent_at on the alert
        self.client.table("shadow_scheduled_alerts").update({"last_sent_at": now}).eq("id", alert_id).execute()

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
        payload = {
            "owner_id": owner_id,
            "rating": rating,
            "response_text": response_text,
            "correction_text": correction_text,
            "context": context or {},
        }
        res = self.client.table("shadow_feedback").insert(payload).execute()
        return res.data[0] if res.data else None

    def learn_pattern(
        self,
        owner_id: str,
        pattern_type: str,
        trigger_text: str | None,
        learned_action: str,
        tool_name: str | None = None,
        confidence_boost: float = 0.1,
    ) -> dict[str, Any] | None:
        """Learn or update a pattern from user correction using Supabase function."""
        try:
            res = self.client.rpc(
                "shadow_learn_pattern",
                {
                    "p_owner_id": owner_id,
                    "p_pattern_type": pattern_type,
                    "p_trigger_text": trigger_text,
                    "p_learned_action": learned_action,
                    "p_tool_name": tool_name,
                    "p_confidence_boost": confidence_boost,
                }
            ).execute()
            if res.data:
                return {"id": res.data, "success": True}
            return None
        except Exception as e:
            print(f"[storage] Error learning pattern: {e}")
            return None

    def get_learned_patterns(
        self,
        owner_id: str,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Get learned patterns for a user."""
        try:
            res = self.client.rpc(
                "shadow_get_patterns",
                {"p_owner_id": owner_id, "p_min_confidence": min_confidence}
            ).execute()
            return res.data or []
        except Exception as e:
            print(f"[storage] Error getting patterns: {e}")
            return []

    def update_learned_preference(
        self,
        owner_id: str,
        key: str,
        value: str,
        source: str = "auto",
        confidence_boost: float = 0.1,
    ) -> None:
        """Update or insert a learned preference using Supabase function."""
        try:
            self.client.rpc(
                "shadow_update_preference",
                {
                    "p_owner_id": owner_id,
                    "p_key": key,
                    "p_value": value,
                    "p_source": source,
                    "p_confidence_boost": confidence_boost,
                }
            ).execute()
        except Exception as e:
            print(f"[storage] Error updating preference: {e}")

    def get_learned_preferences(
        self,
        owner_id: str,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Get learned preferences for a user."""
        try:
            res = self.client.rpc(
                "shadow_get_learned_preferences",
                {"p_owner_id": owner_id, "p_min_confidence": min_confidence}
            ).execute()
            return res.data or []
        except Exception as e:
            print(f"[storage] Error getting preferences: {e}")
            return []

    def create_reminder(
        self,
        remind_at: str,
        message: str,
        task_id: int | None = None,
        appointment_id: int | None = None,
        target_phone: str | None = None,
    ) -> None:
        enc_message = self.crypto.encrypt_text(message, user_id=self.user_id, aad="reminder:message")
        payload = {
            "user_id": self.user_id,
            "task_id": task_id,
            "appointment_id": appointment_id,
            "remind_at": remind_at,
            "message": enc_message,
            "sent": False,
        }
        # Add target_phone if specified (Phase 4 recipient resolution)
        if target_phone:
            payload["target_phone"] = target_phone
        self.client.table("shadow_reminders").insert(payload).execute()

    def pending_reminders(self, now_iso: str) -> Iterable[dict]:
        data = (
            self.client.table("shadow_reminders")
            .select("id,remind_at,message")
            .eq("user_id", self.user_id)
            .eq("sent", False)
            .lte("remind_at", now_iso)
            .execute()
            .data
        )
        for row in data:
            row["message"] = self.crypto.decrypt_text(row.get("message", ""), user_id=self.user_id, aad="reminder:message")
        return data

    def mark_reminder_sent(self, reminder_id: int) -> None:
        self.client.table("shadow_reminders").update({"sent": True}).eq("id", reminder_id).execute()

    def record_interaction(self, user_phone: str | None, user_message: str, reply: str, intent: str) -> None:
        enc_message = self.crypto.encrypt_text(user_message, user_id=self.user_id, aad="interaction:user_message")
        enc_reply = self.crypto.encrypt_text(reply, user_id=self.user_id, aad="interaction:shadow_response")
        payload = {
            "user_id": self.user_id,
            "user_message": enc_message,
            "shadow_response": enc_reply,
            "intent": intent,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.client.table("shadow_interactions").insert(payload).execute()

    def get_config(self, key: str) -> str | None:
        """Retorna um valor de configuração do Shadow."""
        res = (
            self.client.table("shadow_config")
            .select("value")
            .eq("user_id", self.user_id)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["value"]
        return None

    def set_config(self, key: str, value: str) -> None:
        """Define um valor de configuração do Shadow."""
        payload = {
            "user_id": self.user_id,
            "key": key,
            "value": value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.client.table("shadow_config").upsert(payload, on_conflict="user_id,key").execute()

    def get_shadow_group_jid(self) -> str | None:
        """Retorna o JID do grupo Shadow se existir."""
        return self.get_config("shadow_group_jid")

    def set_shadow_group_jid(self, group_jid: str) -> None:
        """Salva o JID do grupo Shadow."""
        self.set_config("shadow_group_jid", group_jid)

    def list_contact_timeline(self, phone: str, limit: int = 20) -> list[dict[str, Any]]:
        contact_res = (
            self.client.table("shadow_contacts")
            .select("id")
            .eq("user_id", self.user_id)
            .eq("phone_number", phone)
            .limit(1)
            .execute()
        )
        if not contact_res.data:
            return []
        contact_id = contact_res.data[0]["id"]
        conv_res = (
            self.client.table("shadow_conversations")
            .select("id")
            .eq("user_id", self.user_id)
            .eq("contact_id", contact_id)
            .execute()
        )
        conv_ids = [row["id"] for row in conv_res.data or []]
        if not conv_ids:
            return []
        msg_res = (
            self.client.table("shadow_messages")
            .select("content,direction,timestamp,conversation_id")
            .in_("conversation_id", conv_ids)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        rows = msg_res.data or []
        for row in rows:
            row["content"] = self.crypto.decrypt_text(row.get("content", ""), user_id=self.user_id, aad=None)
        return rows

    def list_recent_contacts(self, limit: int = 20) -> list[dict[str, Any]]:
        data = (
            self.client.table("shadow_contacts")
            .select("phone_number,name,last_interaction_at")
            .eq("user_id", self.user_id)
            .order("last_interaction_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return data or []

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
    ) -> str:
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
        payload = {
            "owner_id": owner_id,
            "source_chat_id": source_chat_id,
            "source_message_id": source_message_id,
            "entity_type": entity_type,
            "entity_data": entity_data,
            "confidence": confidence,
            "sender_phone": sender_phone,
            "sender_name": sender_name,
        }
        data = self.client.table("shadow_extracted_entities").insert(payload).execute().data
        return data[0]["id"] if data else None

    def update_contact_context(
        self,
        owner_id: str,
        contact_phone: str,
        contact_name: str | None = None,
        message: str | None = None,
    ) -> None:
        """Update or create contact context with new interaction."""
        now = datetime.utcnow().isoformat()
        # Check if exists
        res = (
            self.client.table("shadow_contact_context")
            .select("id,interaction_count,message_count")
            .eq("owner_id", owner_id)
            .eq("contact_phone", contact_phone)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            self.client.table("shadow_contact_context").update({
                "contact_name": contact_name,
                "last_interaction": now,
                "interaction_count": row["interaction_count"] + 1,
                "message_count": row["message_count"] + 1,
            }).eq("id", row["id"]).execute()
        else:
            self.client.table("shadow_contact_context").insert({
                "owner_id": owner_id,
                "contact_phone": contact_phone,
                "contact_name": contact_name,
                "last_interaction": now,
                "interaction_count": 1,
                "message_count": 1,
            }).execute()

    def get_contact_context(
        self,
        owner_id: str,
        contact_phone: str | None = None,
        contact_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for a specific contact by phone or name."""
        query = self.client.table("shadow_contact_context").select("*").eq("owner_id", owner_id)
        if contact_phone:
            query = query.eq("contact_phone", contact_phone)
        elif contact_name:
            query = query.ilike("contact_name", f"%{contact_name}%")
        else:
            return None
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    def list_tasks_for_contact(
        self,
        owner_id: str,
        contact_identifier: str,
    ) -> list[dict[str, Any]]:
        """List tasks related to a contact (by phone or name)."""
        # Get from task_contacts
        res = (
            self.client.table("shadow_task_contacts")
            .select("task_id,relation_type")
            .or_(f"contact_phone.eq.{contact_identifier},contact_name.ilike.%{contact_identifier}%")
            .execute()
        )
        task_ids = [r["task_id"] for r in res.data or []]

        tasks = []
        if task_ids:
            task_res = (
                self.client.table("shadow_tasks")
                .select("id,title,due_date,status")
                .in_("id", task_ids)
                .order("due_date", desc=False)
                .execute()
            )
            tasks = task_res.data or []

        # Also get from extracted entities
        entity_res = (
            self.client.table("shadow_extracted_entities")
            .select("entity_data,confidence,extracted_at")
            .eq("owner_id", owner_id)
            .eq("entity_type", "task")
            .limit(20)
            .execute()
        )
        for row in entity_res.data or []:
            data = row["entity_data"]
            if contact_identifier.lower() in str(data).lower():
                tasks.append({
                    "title": data.get("description", ""),
                    "due_at": data.get("due_date"),
                    "status": "extracted",
                    "confidence": row["confidence"],
                    "extracted_at": row["extracted_at"],
                })
        return tasks

    def list_today_tasks_with_contacts(self, owner_id: str) -> list[dict[str, Any]]:
        """List today's tasks with related contact information."""
        from datetime import date
        today = date.today().isoformat()

        # Get pending tasks
        task_res = (
            self.client.table("shadow_tasks")
            .select("id,title,due_date,status")
            .eq("user_id", self.user_id)
            .eq("status", "pending")
            .execute()
        )
        tasks = []
        for row in task_res.data or []:
            due = row.get("due_date") or ""
            if not due or due.startswith(today):
                task = dict(row)
                # Get contacts
                contact_res = (
                    self.client.table("shadow_task_contacts")
                    .select("contact_phone,contact_name,relation_type")
                    .eq("task_id", row["id"])
                    .execute()
                )
                task["contacts"] = contact_res.data or []
                tasks.append(task)

        # Get extracted entities for today
        entity_res = (
            self.client.table("shadow_extracted_entities")
            .select("entity_data,confidence,extracted_at,source_chat_id")
            .eq("owner_id", owner_id)
            .eq("entity_type", "task")
            .gte("extracted_at", f"{today}T00:00:00")
            .execute()
        )
        for row in entity_res.data or []:
            data = row["entity_data"]
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
        # Find contact
        contact_res = (
            self.client.table("shadow_contacts")
            .select("id,phone_number,name")
            .eq("user_id", self.user_id)
            .or_(f"phone_number.eq.{contact_identifier},name.ilike.%{contact_identifier}%")
            .limit(1)
            .execute()
        )
        if not contact_res.data:
            return []
        contact = contact_res.data[0]

        # Find conversations
        conv_res = (
            self.client.table("shadow_conversations")
            .select("id")
            .eq("user_id", self.user_id)
            .eq("contact_id", contact["id"])
            .execute()
        )
        conv_ids = [r["id"] for r in conv_res.data or []]
        if not conv_ids:
            return []

        # Get messages
        msg_res = (
            self.client.table("shadow_messages")
            .select("content,direction,timestamp")
            .in_("conversation_id", conv_ids)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        rows = [{"contact_name": contact["name"], **m} for m in msg_res.data or []]
        for row in rows:
            row["content"] = self.crypto.decrypt_text(row.get("content", ""), user_id=self.user_id, aad=None)
        return rows

    def link_task_to_contact(
        self,
        task_id: int | str,
        contact_phone: str | None = None,
        contact_name: str | None = None,
        relation_type: str = "mentioned",
    ) -> None:
        """Link a task to a contact."""
        self.client.table("shadow_task_contacts").upsert({
            "task_id": task_id,
            "contact_phone": contact_phone,
            "contact_name": contact_name,
            "relation_type": relation_type,
        }, on_conflict="task_id,contact_phone,contact_name").execute()

    def list_extracted_entities(
        self,
        owner_id: str,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List extracted entities, optionally filtered by type."""
        query = (
            self.client.table("shadow_extracted_entities")
            .select("*")
            .eq("owner_id", owner_id)
        )
        if entity_type:
            query = query.eq("entity_type", entity_type)
        res = query.order("extracted_at", desc=True).limit(limit).execute()
        return res.data or []

    # ========== Phase 5: Alias Methods ==========

    def add_contact_alias(
        self,
        owner_id: str,
        contact_phone: str,
        alias: str,
    ) -> bool:
        """Add an alias for a contact. Returns True if added, False if exists."""
        try:
            self.client.table("shadow_contact_aliases").insert({
                "owner_id": owner_id,
                "contact_phone": contact_phone,
                "alias": alias.lower(),
            }).execute()
            return True
        except Exception:
            return False

    def remove_contact_alias(self, owner_id: str, alias: str) -> bool:
        """Remove an alias. Returns True if deleted."""
        res = (
            self.client.table("shadow_contact_aliases")
            .delete()
            .eq("owner_id", owner_id)
            .eq("alias", alias.lower())
            .execute()
        )
        return len(res.data or []) > 0

    def resolve_alias(self, owner_id: str, alias: str) -> str | None:
        """Resolve an alias to a phone number."""
        res = (
            self.client.table("shadow_contact_aliases")
            .select("contact_phone")
            .eq("owner_id", owner_id)
            .eq("alias", alias.lower())
            .limit(1)
            .execute()
        )
        return res.data[0]["contact_phone"] if res.data else None

    def list_aliases_for_contact(self, owner_id: str, contact_phone: str) -> list[str]:
        """List all aliases for a contact."""
        res = (
            self.client.table("shadow_contact_aliases")
            .select("alias")
            .eq("owner_id", owner_id)
            .eq("contact_phone", contact_phone)
            .execute()
        )
        return [row["alias"] for row in res.data or []]

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
        res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .ilike("contact_name", name)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]

        # 3. Try fuzzy match (ILIKE with wildcards)
        res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .ilike("contact_name", f"%{name}%")
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

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
        now = datetime.utcnow().isoformat()

        # Get current message count
        res = (
            self.client.table("shadow_contact_context")
            .select("id,message_count")
            .eq("owner_id", owner_id)
            .eq("contact_phone", contact_phone)
            .limit(1)
            .execute()
        )
        if not res.data:
            return

        row = res.data[0]
        msg_count = row.get("message_count", 0)

        updates: dict[str, Any] = {
            "last_summary_at": now,
            "summary_message_count": msg_count,
        }
        if summary is not None:
            updates["summary"] = summary
        if topics is not None:
            updates["topics"] = topics  # JSONB in Supabase
        if sentiment is not None:
            updates["sentiment"] = sentiment

        self.client.table("shadow_contact_context").update(updates).eq("id", row["id"]).execute()

    def should_update_summary(self, owner_id: str, contact_phone: str, interval: int = 10) -> bool:
        """Check if summary should be updated (every N messages since last summary)."""
        res = (
            self.client.table("shadow_contact_context")
            .select("message_count,summary_message_count")
            .eq("owner_id", owner_id)
            .eq("contact_phone", contact_phone)
            .limit(1)
            .execute()
        )
        if not res.data:
            return False
        row = res.data[0]
        current = row.get("message_count") or 0
        last_summary = row.get("summary_message_count") or 0
        return (current - last_summary) >= interval

    # ========== Phase 6: Memory Methods (backup for LanceDB) ==========

    def save_contact_memory(
        self,
        owner_id: str,
        text: str,
        contact_phone: str | None = None,
        category: str = "interaction",
        importance: float = 0.5,
    ) -> str:
        """Save a memory entry (backup for LanceDB)."""
        res = self.client.table("shadow_contact_memories").insert({
            "owner_id": owner_id,
            "contact_phone": contact_phone,
            "text": text,
            "category": category,
            "importance": importance,
        }).execute()
        return res.data[0]["id"] if res.data else None

    def list_contact_memories(
        self,
        owner_id: str,
        contact_phone: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List memories, optionally filtered by contact and category."""
        query = (
            self.client.table("shadow_contact_memories")
            .select("*")
            .eq("owner_id", owner_id)
        )
        if contact_phone:
            query = query.eq("contact_phone", contact_phone)
        if category:
            query = query.eq("category", category)

        res = query.order("created_at", desc=True).limit(limit).execute()
        return res.data or []

    # ========== Phase 1 CRM: Contact Management ==========

    def delete_contact(
        self,
        owner_id: str,
        identifier: str,
        hard_delete: bool = False,
    ) -> dict[str, Any]:
        """Delete a contact (soft delete by default)."""
        now = datetime.utcnow().isoformat()

        # Find contact
        res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .is_("deleted_at", "null")
            .or_(f"contact_phone.eq.{identifier},contact_name.ilike.%{identifier}%")
            .limit(1)
            .execute()
        )

        if not res.data:
            return {"success": False, "error": "Contato não encontrado"}

        contact = res.data[0]
        phone = contact["contact_phone"]
        name = contact.get("contact_name") or phone

        if hard_delete:
            self.client.table("shadow_contact_context").delete().eq("owner_id", owner_id).eq("contact_phone", phone).execute()
            self.client.table("shadow_contact_aliases").delete().eq("owner_id", owner_id).eq("contact_phone", phone).execute()
            self.client.table("shadow_contact_memories").delete().eq("owner_id", owner_id).eq("contact_phone", phone).execute()
            self.client.table("shadow_contacts").delete().eq("user_id", self.user_id).eq("phone_number", phone).execute()
        else:
            self.client.table("shadow_contact_context").update({
                "deleted_at": now,
            }).eq("owner_id", owner_id).eq("contact_phone", phone).execute()
            self.client.table("shadow_contacts").update({
                "deleted_at": now,
                "deleted_by": owner_id,
            }).eq("user_id", self.user_id).eq("phone_number", phone).execute()

        return {
            "success": True,
            "phone": phone,
            "name": name,
            "hard_delete": hard_delete,
        }

    def restore_contact(self, owner_id: str, phone: str) -> dict[str, Any]:
        """Restore a soft-deleted contact."""
        res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("contact_phone", phone)
            .not_.is_("deleted_at", "null")
            .limit(1)
            .execute()
        )

        if not res.data:
            return {"success": False, "error": "Contato não encontrado ou não está excluído"}

        contact = res.data[0]
        self.client.table("shadow_contact_context").update({
            "deleted_at": None,
        }).eq("id", contact["id"]).execute()
        self.client.table("shadow_contacts").update({
            "deleted_at": None,
        }).eq("user_id", self.user_id).eq("phone_number", phone).execute()

        return {"success": True, "phone": phone, "name": contact.get("contact_name")}

    def merge_contacts(
        self,
        owner_id: str,
        target_phone: str,
        source_phone: str,
    ) -> dict[str, Any]:
        """Merge source contact into target contact."""
        now = datetime.utcnow().isoformat()

        # Verify target
        target_res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("contact_phone", target_phone)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not target_res.data:
            return {"success": False, "error": f"Contato alvo {target_phone} não encontrado"}
        target = target_res.data[0]

        # Verify source
        source_res = (
            self.client.table("shadow_contact_context")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("contact_phone", source_phone)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not source_res.data:
            return {"success": False, "error": f"Contato origem {source_phone} não encontrado"}
        source = source_res.data[0]

        # Record merge history
        self.client.table("shadow_contact_merges").insert({
            "owner_id": owner_id,
            "target_phone": target_phone,
            "source_phone": source_phone,
            "source_name": source.get("contact_name"),
            "merged_at": now,
            "merged_by": owner_id,
        }).execute()

        # Transfer aliases
        self.client.table("shadow_contact_aliases").update({
            "contact_phone": target_phone,
        }).eq("owner_id", owner_id).eq("contact_phone", source_phone).execute()

        # Add source name as alias
        if source.get("contact_name"):
            try:
                self.client.table("shadow_contact_aliases").insert({
                    "owner_id": owner_id,
                    "contact_phone": target_phone,
                    "alias": source["contact_name"].lower(),
                }).execute()
            except Exception:
                pass

        # Transfer memories
        self.client.table("shadow_contact_memories").update({
            "contact_phone": target_phone,
        }).eq("owner_id", owner_id).eq("contact_phone", source_phone).execute()

        # Transfer task links
        self.client.table("shadow_task_contacts").update({
            "contact_phone": target_phone,
        }).eq("contact_phone", source_phone).execute()

        # Update counts on target
        source_count = source.get("message_count") or 0
        source_interactions = source.get("interaction_count") or 0
        self.client.table("shadow_contact_context").update({
            "message_count": (target.get("message_count") or 0) + source_count,
            "interaction_count": (target.get("interaction_count") or 0) + source_interactions,
        }).eq("id", target["id"]).execute()

        # Soft delete source
        self.client.table("shadow_contact_context").update({
            "deleted_at": now,
        }).eq("id", source["id"]).execute()

        return {
            "success": True,
            "target_phone": target_phone,
            "target_name": target.get("contact_name"),
            "source_phone": source_phone,
            "source_name": source.get("contact_name"),
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
        """
        res = (
            self.client.table("shadow_contact_context")
            .select("contact_phone,contact_name,email")
            .eq("owner_id", owner_id)
            .is_("deleted_at", "null")
            .execute()
        )
        contacts = res.data or []

        if len(contacts) < 2:
            return []

        duplicates = []
        seen_pairs: set[tuple[str, str]] = set()

        def add_duplicate(c1: dict, c2: dict, match_type: str, confidence: float) -> None:
            pair_key = tuple(sorted([c1["contact_phone"], c2["contact_phone"]]))
            if pair_key in seen_pairs:
                return
            seen_pairs.add(pair_key)
            duplicates.append({
                "phone_a": c1["contact_phone"],
                "name_a": c1.get("contact_name"),
                "email_a": c1.get("email"),
                "phone_b": c2["contact_phone"],
                "name_b": c2.get("contact_name"),
                "email_b": c2.get("email"),
                "type": match_type,
                "similarity": round(confidence, 2),
            })

        # 1. EMAIL MATCHES (100% confidence)
        email_groups: dict[str, list[dict]] = {}
        for contact in contacts:
            email = (contact.get("email") or "").lower().strip()
            if email:
                email_groups.setdefault(email, []).append(contact)

        for email, group in email_groups.items():
            if len(group) > 1:
                for i, c1 in enumerate(group):
                    for c2 in group[i + 1:]:
                        add_duplicate(c1, c2, "email_match", 1.0)

        # 2. NAME SIMILARITY (with DDD boost)
        for i, c1 in enumerate(contacts):
            for c2 in contacts[i + 1:]:
                name1 = (c1.get("contact_name") or "").lower()
                name2 = (c2.get("contact_name") or "").lower()
                if not name1 or not name2:
                    continue

                base_similarity = self._name_similarity(name1, name2)
                if base_similarity < threshold:
                    continue

                phone1 = c1.get("contact_phone") or ""
                phone2 = c2.get("contact_phone") or ""
                ddd1 = phone1[3:5] if len(phone1) >= 5 else ""
                ddd2 = phone2[3:5] if len(phone2) >= 5 else ""
                same_ddd = ddd1 and ddd2 and ddd1 == ddd2

                if same_ddd:
                    match_type = "name_same_ddd"
                    confidence = min(1.0, base_similarity + 0.1)
                else:
                    match_type = "name_similar"
                    confidence = base_similarity

                add_duplicate(c1, c2, match_type, confidence)

        type_priority = {"email_match": 0, "name_same_ddd": 1, "name_similar": 2}
        duplicates.sort(key=lambda x: (type_priority.get(x["type"], 99), -x["similarity"]))
        return duplicates[:limit]

    def _name_similarity(self, s1: str, s2: str) -> float:
        """Calculate name similarity."""
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            return 0.9
        parts1, parts2 = s1.split(), s2.split()
        if parts1 and parts2 and parts1[0] == parts2[0]:
            return 0.8

        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        if len1 > len2:
            s1, s2 = s2, s1
            len1, len2 = len2, len1

        distances = list(range(len1 + 1))
        for i2, c2 in enumerate(s2):
            new_distances = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    new_distances.append(distances[i1])
                else:
                    new_distances.append(1 + min(distances[i1], distances[i1 + 1], new_distances[-1]))
            distances = new_distances

        return 1.0 - (distances[-1] / max(len1, len2))

    def list_deleted_contacts(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List soft-deleted contacts."""
        res = (
            self.client.table("shadow_contact_context")
            .select("contact_phone,contact_name,deleted_at")
            .eq("owner_id", owner_id)
            .not_.is_("deleted_at", "null")
            .order("deleted_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def list_contact_merges(self, owner_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """List merge history."""
        res = (
            self.client.table("shadow_contact_merges")
            .select("*")
            .eq("owner_id", owner_id)
            .order("merged_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    # ========== Phase 7: Proactive Suggestions ==========

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
    ) -> str:
        """Create a new suggestion and return its ID."""
        payload = {
            "owner_id": owner_id,
            "source_type": source_type,
            "source_id": source_id,
            "source_chat_id": source_chat_id,
            "source_message_id": source_message_id,
            "suggestion_type": suggestion_type,
            "title": title,
            "body": body,
            "suggestion_data": suggestion_data,
            "confidence": confidence,
            "priority": priority,
            "status": "pending",
            "send_after": send_after,
            "expires_at": expires_at,
        }
        data = self.client.table("shadow_suggestions").insert(payload).execute().data
        return data[0]["id"] if data else None

    def get_suggestion(self, suggestion_id: str) -> dict[str, Any] | None:
        """Get a suggestion by ID."""
        res = self.client.table("shadow_suggestions").select("*").eq("id", suggestion_id).execute()
        return res.data[0] if res.data else None

    def get_pending_suggestions(
        self,
        owner_id: str,
        limit: int = 10,
        min_priority: int = 0,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        """Get pending suggestions ready to send."""
        now = datetime.utcnow().isoformat()
        query = (
            self.client.table("shadow_suggestions")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("status", status)
            .gte("priority", min_priority)
        )
        # Supabase doesn't have easy OR for null checks, so we do post-filter
        res = query.order("priority", desc=True).order("created_at").limit(limit * 2).execute()
        results = []
        for row in res.data or []:
            send_after = row.get("send_after")
            expires_at = row.get("expires_at")
            if send_after and send_after > now:
                continue
            if expires_at and expires_at < now:
                continue
            results.append(row)
            if len(results) >= limit:
                break
        return results

    def get_sent_suggestions(
        self,
        owner_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get suggestions that were sent and await response."""
        res = (
            self.client.table("shadow_suggestions")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("status", "sent")
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def update_suggestion_status(
        self,
        suggestion_id: str,
        status: str,
        response_text: str | None = None,
        response_message_id: str | None = None,
    ) -> bool:
        """Update suggestion status."""
        now = datetime.utcnow().isoformat()
        payload = {
            "status": status,
            "response_text": response_text,
            "response_message_id": response_message_id,
            "updated_at": now,
        }
        if status in ("accepted", "rejected", "expired"):
            payload["resolved_at"] = now
        res = self.client.table("shadow_suggestions").update(payload).eq("id", suggestion_id).execute()
        return len(res.data or []) > 0

    def mark_suggestion_sent(self, suggestion_id: str) -> bool:
        """Mark a suggestion as sent."""
        now = datetime.utcnow().isoformat()
        res = (
            self.client.table("shadow_suggestions")
            .update({"status": "sent", "sent_at": now, "updated_at": now})
            .eq("id", suggestion_id)
            .execute()
        )
        return len(res.data or []) > 0

    def mark_entity_processed(self, entity_id: str, processed: bool = True) -> bool:
        """Mark an extracted entity as processed."""
        res = (
            self.client.table("shadow_extracted_entities")
            .update({"processed": processed})
            .eq("id", entity_id)
            .execute()
        )
        return len(res.data or []) > 0

    def get_unprocessed_entities(
        self,
        owner_id: str,
        entity_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get unprocessed entities for suggestion creation."""
        query = (
            self.client.table("shadow_extracted_entities")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("processed", False)
            .gte("confidence", min_confidence)
        )
        if entity_type:
            query = query.eq("entity_type", entity_type)
        res = query.order("confidence", desc=True).order("extracted_at", desc=True).limit(limit).execute()
        return res.data or []

    def get_suggestion_daily_count(self, owner_id: str, date: str | None = None) -> dict[str, Any]:
        """Get daily suggestion count for rate limiting."""
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        res = (
            self.client.table("shadow_suggestion_daily_counts")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("date", date)
            .execute()
        )
        if res.data:
            return res.data[0]
        return {"owner_id": owner_id, "date": date, "sent_count": 0, "accepted_count": 0, "rejected_count": 0}

    def increment_suggestion_count(
        self,
        owner_id: str,
        count_type: str = "sent",
        date: str | None = None,
    ) -> None:
        """Increment daily suggestion count (sent/accepted/rejected)."""
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        column = f"{count_type}_count"
        if column not in ("sent_count", "accepted_count", "rejected_count"):
            column = "sent_count"

        # Check if exists
        existing = self.get_suggestion_daily_count(owner_id, date)
        if existing.get("id"):
            # Update
            self.client.rpc(
                "increment_field",
                {"table_name": "shadow_suggestion_daily_counts", "field": column, "row_id": existing["id"]}
            ).execute()
        else:
            # Insert
            payload = {
                "owner_id": owner_id,
                "date": date,
                "sent_count": 1 if column == "sent_count" else 0,
                "accepted_count": 1 if column == "accepted_count" else 0,
                "rejected_count": 1 if column == "rejected_count" else 0,
            }
            self.client.table("shadow_suggestion_daily_counts").insert(payload).execute()

    def expire_old_suggestions(self, owner_id: str | None = None) -> int:
        """Expire suggestions past their expiry time. Returns count expired."""
        now = datetime.utcnow().isoformat()
        query = (
            self.client.table("shadow_suggestions")
            .update({"status": "expired", "resolved_at": now, "updated_at": now})
            .in_("status", ["pending", "sent"])
            .lt("expires_at", now)
        )
        if owner_id:
            query = query.eq("owner_id", owner_id)
        res = query.execute()
        return len(res.data or [])

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


class Storage:
    def __init__(self) -> None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        owner = os.getenv("SHADOW_OWNER_E164") or ""
        use_supabase = os.getenv("SHADOW_USE_SUPABASE", "true").lower() in {"1", "true", "yes"}
        if url and key and use_supabase and create_client is not None:
            self._impl = SupabaseStorage(url, key, owner)
        else:
            if use_supabase and create_client is None:
                print("[storage] Supabase client not installed, usando SQLite.")
            self._impl = SqliteStorage()

    def __getattr__(self, name: str):
        return getattr(self._impl, name)
