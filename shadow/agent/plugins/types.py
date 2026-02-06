"""
Shadow Agent Plugin System - Type Definitions

Defines the plugin interface and hook types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, TypeVar, Awaitable
import logging


class AgentHookName(str, Enum):
    """Available hook names for agent plugins."""
    # Message lifecycle
    BEFORE_HANDLE = "before_handle"
    AFTER_HANDLE = "after_handle"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"

    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_CONTEXT_UPDATE = "session_context_update"

    # Storage operations
    STORAGE_WRITE = "storage_write"
    TASK_CREATED = "task_created"
    APPOINTMENT_CREATED = "appointment_created"
    REMINDER_CREATED = "reminder_created"

    # Tool/Action lifecycle
    TOOL_CALL = "tool_call"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"

    # Scheduler
    CRON_JOB_START = "cron_job_start"
    CRON_JOB_END = "cron_job_end"

    # Security
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"


# Type aliases for hook handlers
BeforeHandleHandler = Callable[[dict], Awaitable[dict | None]]
AfterHandleHandler = Callable[[dict, dict], Awaitable[None]]
ToolCallHandler = Callable[[str, dict], Awaitable[dict | None]]
StorageWriteHandler = Callable[[str, dict], Awaitable[None]]


class PluginApi(Protocol):
    """
    Plugin API interface.

    Provides methods for plugins to register hooks, handlers, and tools.
    """

    @property
    def id(self) -> str:
        """Plugin identifier."""
        ...

    @property
    def name(self) -> str:
        """Plugin display name."""
        ...

    @property
    def config(self) -> dict:
        """Agent configuration."""
        ...

    @property
    def plugin_config(self) -> dict:
        """Plugin-specific configuration."""
        ...

    @property
    def logger(self) -> logging.Logger:
        """Plugin logger."""
        ...

    def register_handler(self, intent: str, handler: Callable) -> None:
        """Register a handler for a specific intent."""
        ...

    def register_tool(self, name: str, handler: Callable, schema: dict | None = None) -> None:
        """Register a custom tool."""
        ...

    def on(
        self,
        hook_name: AgentHookName | str,
        handler: Callable,
        priority: int = 0,
    ) -> None:
        """Register a hook handler."""
        ...


@dataclass
class PluginDefinition:
    """
    Plugin definition structure.

    Plugins must provide at least an id and register function.
    """
    id: str
    name: str | None = None
    version: str | None = None
    description: str | None = None
    register: Callable[[PluginApi], None] | None = None


@dataclass
class HookRegistration:
    """A registered hook handler."""
    plugin_id: str
    hook_name: AgentHookName
    handler: Callable
    priority: int = 0


@dataclass
class ToolRegistration:
    """A registered tool."""
    plugin_id: str
    name: str
    handler: Callable
    schema: dict = field(default_factory=dict)


@dataclass
class HandlerRegistration:
    """A registered intent handler."""
    plugin_id: str
    intent: str
    handler: Callable


@dataclass
class PluginRecord:
    """
    Record of a loaded plugin.
    """
    id: str
    name: str
    version: str | None
    source: str
    enabled: bool = True
    status: str = "loaded"  # "loaded", "disabled", "error"
    hook_names: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    handler_intents: list[str] = field(default_factory=list)


# Event types for hooks

@dataclass
class BeforeHandleEvent:
    """Event passed to before_handle hooks."""
    payload: dict


@dataclass
class AfterHandleEvent:
    """Event passed to after_handle hooks."""
    payload: dict
    result: dict


@dataclass
class ToolCallEvent:
    """Event passed to tool_call hooks."""
    tool_name: str
    params: dict


@dataclass
class StorageWriteEvent:
    """Event passed to storage_write hooks."""
    operation: str  # "task", "appointment", "message", etc.
    data: dict


@dataclass
class MessageReceivedEvent:
    """Event passed to message_received hooks."""
    chat_id: str | None
    sender: str | None
    content: str
    is_owner: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class MessageSendingEvent:
    """Event passed to message_sending hooks."""
    chat_id: str | None
    content: str
    intent: str
    metadata: dict = field(default_factory=dict)


@dataclass
class MessageSentEvent:
    """Event passed to message_sent hooks."""
    chat_id: str | None
    content: str
    success: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionStartEvent:
    """Event passed to session_start hooks."""
    session_id: str
    chat_id: str
    participant_phone: str | None
    kind: str  # "direct" or "group"


@dataclass
class SessionEndEvent:
    """Event passed to session_end hooks."""
    session_id: str
    chat_id: str
    reason: str  # "timeout", "explicit", "cleanup"


@dataclass
class SessionContextUpdateEvent:
    """Event passed to session_context_update hooks."""
    session_id: str
    message_role: str  # "user" or "assistant"
    message_content: str
    context_size: int


@dataclass
class TaskCreatedEvent:
    """Event passed to task_created hooks."""
    task_id: str | int
    title: str
    due_at: str | None


@dataclass
class AppointmentCreatedEvent:
    """Event passed to appointment_created hooks."""
    appointment_id: str | int
    title: str
    scheduled_at: str


@dataclass
class ReminderCreatedEvent:
    """Event passed to reminder_created hooks."""
    reminder_id: str | int
    message: str
    remind_at: str


@dataclass
class CronJobStartEvent:
    """Event passed to cron_job_start hooks."""
    job_id: str
    job_name: str
    action: str


@dataclass
class CronJobEndEvent:
    """Event passed to cron_job_end hooks."""
    job_id: str
    job_name: str
    action: str
    status: str  # "ok", "error", "skipped"
    duration_ms: int | None
    error: str | None = None


@dataclass
class AccessDeniedEvent:
    """Event passed to access_denied hooks."""
    phone: str
    reason: str
    policy_mode: str  # "owner_only", "allowlist", "open"


@dataclass
class RateLimitedEvent:
    """Event passed to rate_limited hooks."""
    client_key: str  # IP or phone
    remaining_seconds: float
