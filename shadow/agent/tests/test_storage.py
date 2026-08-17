"""Tests for the storage layer (SQLite backend)."""

import pytest
from datetime import datetime, timezone


class TestTaskCRUD:
    """Task create, read, update, complete, delete."""

    def test_create_task(self, storage):
        task = storage.create_task("Buy groceries", None)
        assert task is not None
        assert task.title == "Buy groceries"
        assert task.status == "pending"

    def test_create_task_with_due_date(self, storage):
        task = storage.create_task("Submit report", "2026-02-15")
        assert task.due_at is not None
        assert "2026-02-15" in task.due_at

    def test_list_tasks(self, storage):
        storage.create_task("Task A", None)
        storage.create_task("Task B", None)
        tasks = storage.list_tasks()
        assert len(tasks) >= 2
        titles = [t.title for t in tasks]
        assert "Task A" in titles
        assert "Task B" in titles

    def test_get_task(self, storage):
        created = storage.create_task("Find me", None)
        found = storage.get_task(created.id)
        assert found is not None
        assert found.title == "Find me"

    def test_get_task_not_found(self, storage):
        result = storage.get_task(99999)
        assert result is None

    def test_complete_task(self, storage):
        task = storage.create_task("Complete me", None)
        storage.complete_task(task.id)
        updated = storage.get_task(task.id)
        assert updated.status == "completed"

    def test_delete_task_soft(self, storage):
        task = storage.create_task("Delete me soft", None)
        storage.delete_task(task.id)
        # Soft-deleted tasks should not appear in list
        tasks = storage.list_tasks()
        ids = [t.id for t in tasks]
        assert task.id not in ids

    def test_delete_task_hard(self, storage):
        task = storage.create_task("Delete me hard", None)
        storage.delete_task(task.id, hard_delete=True)
        result = storage.get_task(task.id)
        assert result is None


class TestAppointmentCRUD:
    """Appointment create, read, update, delete."""

    def test_create_appointment(self, storage):
        appt = storage.create_appointment("Team meeting", "2026-02-10 10:00")
        assert appt is not None
        assert appt.title == "Team meeting"

    def test_list_appointments(self, storage):
        storage.create_appointment("Meeting A", "2026-02-10 10:00")
        storage.create_appointment("Meeting B", "2026-02-11 14:00")
        appts = storage.list_appointments()
        assert len(appts) >= 2

    def test_get_appointment(self, storage):
        created = storage.create_appointment("Find appt", "2026-02-10 09:00")
        found = storage.get_appointment(created.id)
        assert found is not None
        assert found.title == "Find appt"

    def test_delete_appointment(self, storage):
        appt = storage.create_appointment("Cancel this", "2026-02-10 09:00")
        storage.delete_appointment(appt.id)
        # After hard delete, should be gone
        result = storage.get_appointment(appt.id)
        assert result is None


class TestUserSettings:
    """User settings CRUD."""

    def test_get_default_settings(self, storage, owner_id):
        settings = storage.get_user_settings(owner_id)
        assert isinstance(settings, dict)
        assert settings.get("timezone") == "America/Sao_Paulo"
        assert settings.get("language") == "pt-BR"

    def test_update_settings(self, storage, owner_id):
        storage.ensure_user_settings(owner_id)
        storage.update_user_settings(owner_id, timezone="America/New_York")
        settings = storage.get_user_settings(owner_id)
        assert settings["timezone"] == "America/New_York"

    def test_update_boolean_setting(self, storage, owner_id):
        storage.ensure_user_settings(owner_id)
        storage.update_user_settings(owner_id, use_emojis=False)
        settings = storage.get_user_settings(owner_id)
        assert settings["use_emojis"] is False


class TestLearningSystem:
    """Learning patterns and preferences."""

    def test_record_feedback(self, storage, owner_id):
        result = storage.record_feedback(
            owner_id,
            rating="positive",
        )
        assert result is not None

    def test_learn_and_get_patterns(self, storage, owner_id):
        storage.learn_pattern(
            owner_id,
            pattern_type="missing_date",
            trigger_text="tarefa sem data",
            learned_action="perguntar data",
        )
        patterns = storage.get_learned_patterns(owner_id, min_confidence=0.0)
        assert len(patterns) >= 1
        assert patterns[0]["pattern_type"] == "missing_date"

    def test_learned_preferences(self, storage, owner_id):
        storage.update_learned_preference(
            owner_id,
            key="preferred_meeting_time",
            value="morning",
            source="observation",
        )
        prefs = storage.get_learned_preferences(owner_id, min_confidence=0.0)
        assert len(prefs) >= 1
        assert prefs[0]["preference_key"] == "preferred_meeting_time"


class TestContactMemory:
    """Contact memory storage (SQLite backup)."""

    def test_save_and_list_memories(self, storage, owner_id):
        mem_id = storage.save_contact_memory(
            owner_id,
            contact_phone="+5511888880000",
            text="Prefers morning meetings",
            category="preference",
            importance=0.8,
        )
        assert mem_id is not None

        memories = storage.list_contact_memories(owner_id, contact_phone="+5511888880000")
        assert len(memories) >= 1
        assert memories[0]["text"] == "Prefers morning meetings"

    def test_list_memories_filtered_by_category(self, storage, owner_id):
        storage.save_contact_memory(
            owner_id, "+5511888880000", "Fact A", category="fact", importance=0.7
        )
        storage.save_contact_memory(
            owner_id, "+5511888880000", "Pref B", category="preference", importance=0.8
        )
        facts = storage.list_contact_memories(
            owner_id, contact_phone="+5511888880000", category="fact"
        )
        assert all(m["category"] == "fact" for m in facts)


class TestReminders:
    """Reminder creation and retrieval."""

    def test_create_reminder(self, storage):
        # create_reminder(remind_at, message, ...) - returns None
        storage.create_reminder("2026-02-10T14:00:00Z", "Take medicine")
        # No assertion on return - it returns None

    def test_pending_reminders(self, storage):
        storage.create_reminder("2020-01-01T00:00:00Z", "Past reminder")
        now = datetime.now(timezone.utc).isoformat()
        pending = list(storage.pending_reminders(now))
        assert len(pending) >= 1


class TestScheduledAlerts:
    """Scheduled alerts CRUD."""

    def test_create_alert(self, storage, owner_id):
        result = storage.create_scheduled_alert(
            owner_id, alert_time="07:00", alert_type="summary"
        )
        assert result is not None

    def test_list_alerts(self, storage, owner_id):
        storage.create_scheduled_alert(owner_id, alert_time="07:00", alert_type="summary")
        storage.create_scheduled_alert(owner_id, alert_time="18:00", alert_type="reminder")
        alerts = storage.list_scheduled_alerts(owner_id)
        assert len(alerts) >= 2

    def test_delete_alert(self, storage, owner_id):
        result = storage.create_scheduled_alert(
            owner_id, alert_time="09:00", alert_type="custom"
        )
        # create_scheduled_alert returns a dict with 'id'
        alert_id = result["id"] if isinstance(result, dict) else result
        storage.delete_scheduled_alert(owner_id, alert_id)
        alerts = storage.list_scheduled_alerts(owner_id)
        active_ids = [a["id"] for a in alerts if a.get("is_active", True)]
        assert alert_id not in active_ids


class TestCategories:
    """Task categories and appointment types."""

    def test_seed_and_list_categories(self, storage, owner_id):
        storage.seed_default_categories(owner_id)
        cats = storage.list_task_categories(owner_id)
        assert len(cats) >= 1

    def test_create_custom_category(self, storage, owner_id):
        storage.seed_default_categories(owner_id)
        cat_id = storage.create_task_category(owner_id, "projeto_x", color="#FF5733")
        assert cat_id is not None
        cats = storage.list_task_categories(owner_id)
        names = [c["name"] for c in cats]
        assert "projeto_x" in names

    def test_list_appointment_types(self, storage, owner_id):
        storage.seed_default_categories(owner_id)
        types = storage.list_appointment_types(owner_id)
        assert len(types) >= 1


class TestPackageImports:
    """Verify the storage package exports work correctly."""

    def test_import_from_package(self):
        from storage import Storage, SqliteStorage, SupabaseStorage, Task, Appointment

        assert Storage is not None
        assert SqliteStorage is not None
        assert Task is not None
        assert Appointment is not None

    def test_import_from_submodules(self):
        from storage.types import Task, Appointment
        from storage.sqlite_storage import SqliteStorage
        from storage.wrapper import Storage

        assert Task is not None

    def test_task_dataclass(self):
        from storage.types import Task

        t = Task(id=1, title="test", due_at=None, status="pending")
        assert t.title == "test"

    def test_appointment_dataclass(self):
        from storage.types import Appointment

        a = Appointment(
            id=1, title="meeting", scheduled_at="2026-01-01", duration_minutes=30
        )
        assert a.duration_minutes == 30


class TestMultiTenantIsolation:
    """Verify owner_id isolation across tasks, appointments, and reminders."""

    def test_tasks_isolated_by_owner(self, tmp_db):
        from storage.sqlite_storage import SqliteStorage

        base = SqliteStorage(db_path=tmp_db)
        owner_a = base.for_owner("+5511111111111")
        owner_b = base.for_owner("+5522222222222")

        owner_a.create_task("Task A", None)
        owner_b.create_task("Task B", None)

        tasks_a = owner_a.list_tasks()
        tasks_b = owner_b.list_tasks()

        assert len(tasks_a) == 1
        assert tasks_a[0].title == "Task A"
        assert len(tasks_b) == 1
        assert tasks_b[0].title == "Task B"

    def test_appointments_isolated_by_owner(self, tmp_db):
        from storage.sqlite_storage import SqliteStorage

        base = SqliteStorage(db_path=tmp_db)
        owner_a = base.for_owner("+5511111111111")
        owner_b = base.for_owner("+5522222222222")

        owner_a.create_appointment("Meeting A", "2026-03-15 10:00")
        owner_b.create_appointment("Meeting B", "2026-03-15 14:00")

        appts_a = owner_a.list_appointments()
        appts_b = owner_b.list_appointments()

        assert len(appts_a) == 1
        assert appts_a[0].title == "Meeting A"
        assert len(appts_b) == 1
        assert appts_b[0].title == "Meeting B"

    def test_reminders_isolated_by_owner(self, tmp_db):
        from storage.sqlite_storage import SqliteStorage

        base = SqliteStorage(db_path=tmp_db)
        owner_a = base.for_owner("+5511111111111")
        owner_b = base.for_owner("+5522222222222")

        owner_a.create_reminder("2020-01-01T00:00:00Z", "Reminder A")
        owner_b.create_reminder("2020-01-01T00:00:00Z", "Reminder B")

        pending_a = list(owner_a.pending_reminders("2026-12-31T00:00:00Z"))
        pending_b = list(owner_b.pending_reminders("2026-12-31T00:00:00Z"))

        assert len(pending_a) == 1
        assert "Reminder A" in pending_a[0]["message"]
        assert len(pending_b) == 1
        assert "Reminder B" in pending_b[0]["message"]

    def test_owner_cannot_access_other_tasks(self, tmp_db):
        from storage.sqlite_storage import SqliteStorage

        base = SqliteStorage(db_path=tmp_db)
        owner_a = base.for_owner("+5511111111111")
        owner_b = base.for_owner("+5522222222222")

        task = owner_a.create_task("Secret Task", None)
        # Owner B should NOT see or modify Owner A's task
        assert owner_b.get_task(task.id) is None
        assert owner_b.complete_task(task.id) is None
        result = owner_b.delete_task(task.id)
        assert result["success"] is False

    def test_no_owner_sees_all(self, tmp_db):
        from storage.sqlite_storage import SqliteStorage

        base = SqliteStorage(db_path=tmp_db)
        owner_a = base.for_owner("+5511111111111")

        owner_a.create_task("Owned Task", None)
        # Base storage (no owner_id) should see everything
        all_tasks = base.list_tasks()
        assert len(all_tasks) >= 1

    def test_for_owner_via_wrapper(self, tmp_db):
        from storage.wrapper import Storage
        from storage.sqlite_storage import SqliteStorage

        impl = SqliteStorage(db_path=tmp_db)
        wrapper = Storage(_impl=impl)

        scoped = wrapper.for_owner("+5511111111111")
        task = scoped.create_task("Wrapper Task", None)
        assert task.title == "Wrapper Task"

        tasks = scoped.list_tasks()
        assert len(tasks) == 1
