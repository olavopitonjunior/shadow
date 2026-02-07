"""
Suggestion System Types - Data structures for proactive suggestions.

This module defines the core data types used throughout the suggestion system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Literal


class SuggestionType(str, Enum):
    """Types of suggestions the system can generate."""
    CREATE_TASK = "create_task"
    CREATE_APPOINTMENT = "create_appointment"
    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    CONVERSATION_SUMMARY = "conversation_summary"


class SuggestionStatus(str, Enum):
    """Status of a suggestion in its lifecycle."""
    PENDING = "pending"      # Created, waiting to be sent
    SENT = "sent"            # Sent to user, awaiting response
    ACCEPTED = "accepted"    # User accepted the suggestion
    REJECTED = "rejected"    # User rejected the suggestion
    EXPIRED = "expired"      # No response within timeout


class SuggestionPriority(int, Enum):
    """Priority levels for suggestions."""
    LOW = 0       # Include in daily summary only
    NORMAL = 1    # Batch with others
    HIGH = 2      # Send soon
    URGENT = 3    # Send immediately


class SourceType(str, Enum):
    """Source of the suggestion."""
    ENTITY = "entity"        # From extracted entity
    CONTACT = "contact"      # From contact detection
    SUMMARY = "summary"      # From conversation analysis
    PATTERN = "pattern"      # From learned pattern


@dataclass
class Suggestion:
    """
    Represents a proactive suggestion to be sent to the user.

    Example:
        suggestion = Suggestion(
            owner_id="+5511999999999",
            source_type=SourceType.ENTITY,
            source_id=123,
            suggestion_type=SuggestionType.CREATE_TASK,
            title="Ligar para João sobre o contrato",
            body="Detectado na conversa com Maria às 14:32",
            suggestion_data={"title": "Ligar para João", "due_date": "amanhã 15h"},
            confidence=0.92,
            priority=SuggestionPriority.HIGH,
        )
    """
    owner_id: str
    source_type: SourceType
    suggestion_type: SuggestionType
    title: str
    confidence: float = 0.5

    # Optional fields
    id: int | None = None
    source_id: int | None = None
    source_chat_id: str | None = None
    source_message_id: str | None = None
    body: str | None = None
    suggestion_data: dict[str, Any] = field(default_factory=dict)
    priority: SuggestionPriority = SuggestionPriority.NORMAL
    status: SuggestionStatus = SuggestionStatus.PENDING
    batch_id: str | None = None

    # Timing
    send_after: datetime | None = None
    expires_at: datetime | None = None
    sent_at: datetime | None = None
    resolved_at: datetime | None = None

    # Response tracking
    response_message_id: str | None = None
    response_text: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "source_type": self.source_type.value if isinstance(self.source_type, SourceType) else self.source_type,
            "source_id": self.source_id,
            "source_chat_id": self.source_chat_id,
            "source_message_id": self.source_message_id,
            "suggestion_type": self.suggestion_type.value if isinstance(self.suggestion_type, SuggestionType) else self.suggestion_type,
            "title": self.title,
            "body": self.body,
            "suggestion_data": self.suggestion_data,
            "confidence": self.confidence,
            "priority": self.priority.value if isinstance(self.priority, SuggestionPriority) else self.priority,
            "status": self.status.value if isinstance(self.status, SuggestionStatus) else self.status,
            "batch_id": self.batch_id,
            "send_after": self.send_after.isoformat() if self.send_after else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "response_message_id": self.response_message_id,
            "response_text": self.response_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Suggestion":
        """Create from dictionary (e.g., from database)."""
        def parse_datetime(val: str | None) -> datetime | None:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        def parse_priority(val: Any) -> SuggestionPriority:
            if isinstance(val, SuggestionPriority):
                return val
            if isinstance(val, int):
                return SuggestionPriority(val)
            return SuggestionPriority.NORMAL

        suggestion_data = data.get("suggestion_data", {})
        if isinstance(suggestion_data, str):
            import json
            try:
                suggestion_data = json.loads(suggestion_data)
            except (json.JSONDecodeError, TypeError):
                suggestion_data = {}

        return cls(
            id=data.get("id"),
            owner_id=data.get("owner_id", ""),
            source_type=SourceType(data.get("source_type", "entity")),
            source_id=data.get("source_id"),
            source_chat_id=data.get("source_chat_id"),
            source_message_id=data.get("source_message_id"),
            suggestion_type=SuggestionType(data.get("suggestion_type", "create_task")),
            title=data.get("title", ""),
            body=data.get("body"),
            suggestion_data=suggestion_data,
            confidence=data.get("confidence", 0.5),
            priority=parse_priority(data.get("priority", 1)),
            status=SuggestionStatus(data.get("status", "pending")),
            batch_id=data.get("batch_id"),
            send_after=parse_datetime(data.get("send_after")),
            expires_at=parse_datetime(data.get("expires_at")),
            sent_at=parse_datetime(data.get("sent_at")),
            resolved_at=parse_datetime(data.get("resolved_at")),
            response_message_id=data.get("response_message_id"),
            response_text=data.get("response_text"),
            created_at=parse_datetime(data.get("created_at")) or datetime.now(timezone.utc),
            updated_at=parse_datetime(data.get("updated_at")) or datetime.now(timezone.utc),
        )

    def is_expired(self) -> bool:
        """Check if the suggestion has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def can_send(self) -> bool:
        """Check if the suggestion can be sent now."""
        if self.status != SuggestionStatus.PENDING:
            return False
        if self.is_expired():
            return False
        if self.send_after and datetime.now(timezone.utc) < self.send_after:
            return False
        return True


@dataclass
class SuggestionResponse:
    """
    Represents a user's response to a suggestion.

    Used by the responder to track what action the user wants to take.
    """
    suggestion_id: int
    action: Literal["accept", "reject", "edit", "accept_multiple", "reject_all", "correction"]
    selected_indices: list[int] = field(default_factory=list)  # For batch responses
    correction_text: str | None = None  # For corrections like "não, era X"
    raw_message: str = ""


@dataclass
class SuggestionBatch:
    """
    A batch of suggestions to be sent together.

    Used for grouping medium-confidence suggestions.
    """
    batch_id: str
    owner_id: str
    suggestions: list[Suggestion] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add(self, suggestion: Suggestion) -> None:
        """Add a suggestion to the batch."""
        suggestion.batch_id = self.batch_id
        self.suggestions.append(suggestion)

    @property
    def size(self) -> int:
        """Number of suggestions in the batch."""
        return len(self.suggestions)


@dataclass
class RateLimitState:
    """
    Tracks rate limiting state for suggestions.

    Used to prevent overwhelming users with too many suggestions.
    """
    owner_id: str
    date: str  # YYYY-MM-DD
    sent_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    max_per_day: int = 20

    @property
    def remaining(self) -> int:
        """Remaining suggestions allowed today."""
        return max(0, self.max_per_day - self.sent_count)

    def can_send(self) -> bool:
        """Check if more suggestions can be sent today."""
        return self.sent_count < self.max_per_day

    def increment_sent(self) -> None:
        """Increment sent counter."""
        self.sent_count += 1


@dataclass
class SuggestionConfig:
    """
    Configuration for the suggestion system.

    Loaded from user settings or defaults.
    """
    enabled: bool = True
    min_confidence: float = 0.60
    max_per_day: int = 20
    immediate_threshold: float = 0.85
    batch_interval_minutes: int = 30
    expiry_hours: int = 24
    monitored_groups: list[str] = field(default_factory=list)
    monitor_all_groups: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "SuggestionConfig":
        """Create config from user settings dict."""
        monitored = settings.get("monitored_groups", [])
        if isinstance(monitored, str):
            import json
            try:
                monitored = json.loads(monitored)
            except (json.JSONDecodeError, TypeError):
                monitored = []

        return cls(
            enabled=settings.get("suggestions_enabled", True),
            min_confidence=settings.get("suggestion_min_confidence", 0.60),
            max_per_day=settings.get("suggestion_max_per_day", 20),
            immediate_threshold=settings.get("suggestion_immediate_threshold", 0.85),
            monitored_groups=monitored,
            monitor_all_groups=settings.get("monitor_all_groups", False),
        )


# Confidence thresholds by suggestion type
CONFIDENCE_THRESHOLDS = {
    SuggestionType.CREATE_TASK: {
        "immediate": 0.85,
        "batch": 0.65,
        "minimum": 0.50,
    },
    SuggestionType.CREATE_APPOINTMENT: {
        "immediate": 0.80,
        "batch": 0.60,
        "minimum": 0.50,
    },
    SuggestionType.CREATE_CONTACT: {
        "immediate": 0.90,
        "batch": 0.70,
        "minimum": 0.60,
    },
    SuggestionType.UPDATE_CONTACT: {
        "immediate": 0.90,
        "batch": 0.70,
        "minimum": 0.60,
    },
    SuggestionType.CONVERSATION_SUMMARY: {
        "immediate": 0.95,  # Almost always batch summaries
        "batch": 0.70,
        "minimum": 0.60,
    },
}


def get_priority_for_confidence(
    suggestion_type: SuggestionType,
    confidence: float,
    has_deadline: bool = False,
    is_urgent: bool = False,
) -> SuggestionPriority:
    """
    Calculate priority based on confidence and context.

    Args:
        suggestion_type: Type of suggestion
        confidence: Confidence score (0-1)
        has_deadline: Whether the suggestion has a deadline
        is_urgent: Whether urgent keywords were detected

    Returns:
        Priority level for the suggestion
    """
    thresholds = CONFIDENCE_THRESHOLDS.get(suggestion_type, {
        "immediate": 0.85,
        "batch": 0.65,
        "minimum": 0.50,
    })

    # Urgent keywords always bump priority
    if is_urgent:
        return SuggestionPriority.URGENT

    # High confidence = high priority
    if confidence >= thresholds["immediate"]:
        return SuggestionPriority.HIGH if has_deadline else SuggestionPriority.HIGH

    # Medium confidence = normal priority
    if confidence >= thresholds["batch"]:
        return SuggestionPriority.NORMAL

    # Low confidence = low priority (daily summary only)
    return SuggestionPriority.LOW
