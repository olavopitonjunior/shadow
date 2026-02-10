import os

from storage.sqlite_storage import SqliteStorage
from storage.supabase_storage import SupabaseStorage

try:
    from supabase import create_client
except Exception:
    create_client = None


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
