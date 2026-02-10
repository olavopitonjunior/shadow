"""
Storage package - Dual-backend storage (SQLite + Supabase).

Backward-compatible: all existing imports continue to work.
"""

from storage.types import Task, Appointment
from storage.sqlite_storage import SqliteStorage
from storage.supabase_storage import SupabaseStorage
from storage.wrapper import Storage

__all__ = ["Storage", "SqliteStorage", "SupabaseStorage", "Task", "Appointment"]
