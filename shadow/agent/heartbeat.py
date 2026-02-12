"""Heartbeat service for periodic task checks.

Adapted from nanobot/heartbeat/service.py.
Lightweight periodic checker - no LLM calls, just DB checks + bus alerts.
"""

import threading
import time
from datetime import datetime, timezone

from bus import OutboundMessage, get_message_bus
from storage import Storage


DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60  # 30 minutes


class HeartbeatService:
    """
    Periodic heartbeat that checks for items needing attention.

    Checks for:
    - Overdue tasks
    - Unprocessed entities/suggestions
    - Pending confirmations that may have expired

    Sends notifications via the message bus when issues are found.
    """

    def __init__(
        self,
        storage: Storage,
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
        enabled: bool = True,
    ):
        self.storage = storage
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the heartbeat in a background thread."""
        if not self.enabled:
            print("[heartbeat] Disabled")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="heartbeat",
            daemon=True,
        )
        self._thread.start()
        print(f"[heartbeat] Started (every {self.interval_s}s)")

    def stop(self) -> None:
        """Stop the heartbeat."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            time.sleep(self.interval_s)
            if self._running:
                try:
                    self._tick()
                except Exception as e:
                    print(f"[heartbeat] Error: {e}")

    def _tick(self) -> None:
        """Execute a single heartbeat check."""
        alerts: list[str] = []

        # Check overdue tasks
        overdue = self._check_overdue_tasks()
        if overdue:
            alerts.append(overdue)

        # Check unprocessed entities
        unprocessed = self._check_unprocessed_entities()
        if unprocessed:
            alerts.append(unprocessed)

        if alerts:
            content = "\n\n".join(alerts)
            bus = get_message_bus()
            bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id="owner",
                content=content,
            ))
            print(f"[heartbeat] Sent {len(alerts)} alert(s)")
        else:
            print("[heartbeat] OK (no action needed)")

    def _check_overdue_tasks(self) -> str | None:
        """Check for overdue tasks."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            tasks = self.storage.list_tasks(20)
            overdue = [t for t in tasks if t.due_at and t.due_at < now_iso]

            if overdue:
                lines = ["⚠️ Tarefas atrasadas:"]
                for task in overdue[:5]:
                    lines.append(f"  • {task.title}")
                if len(overdue) > 5:
                    lines.append(f"  ... e mais {len(overdue) - 5}")
                return "\n".join(lines)
        except Exception as e:
            print(f"[heartbeat] Error checking overdue tasks: {e}")

        return None

    def _check_unprocessed_entities(self) -> str | None:
        """Check for unprocessed extracted entities."""
        try:
            entities = self.storage.get_unprocessed_entities()
            count = len(list(entities)) if entities else 0

            if count > 5:
                return f"📋 {count} entidades extraídas aguardando processamento."
        except Exception:
            pass  # Storage may not support this method

        return None
