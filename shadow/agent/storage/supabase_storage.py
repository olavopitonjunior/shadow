import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from storage.types import Task, Appointment

try:
    from supabase import create_client
except Exception:
    create_client = None

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

    # ── Instance Management ──

    def create_instance(self, instance_id: str, name: str, gateway_user_id: str) -> dict:
        """Create a new instance record."""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": instance_id,
            "name": name,
            "gateway_user_id": gateway_user_id,
            "created_at": now,
        }
        result = self.client.table("shadow_instances").insert(data).execute()
        return result.data[0] if result.data else None

    def get_instance(self, instance_id: str) -> dict | None:
        """Get instance by ID."""
        result = self.client.table("shadow_instances").select("*").eq("id", instance_id).execute()
        return result.data[0] if result.data else None

    def list_instances(self) -> list[dict]:
        """List all instances."""
        result = self.client.table("shadow_instances").select("*").order("created_at", desc=True).execute()
        return result.data if result.data else []

    def update_instance(self, instance_id: str, **kwargs) -> dict | None:
        """Update instance fields."""
        if not kwargs:
            return self.get_instance(instance_id)
        allowed = {"name", "phone", "owner_e164", "status", "connected_at", "disconnected_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_instance(instance_id)
        result = self.client.table("shadow_instances").update(updates).eq("id", instance_id).execute()
        return result.data[0] if result.data else None

    def delete_instance(self, instance_id: str) -> bool:
        """Delete an instance."""
        self.client.table("shadow_instances").delete().eq("id", instance_id).execute()
        return True

