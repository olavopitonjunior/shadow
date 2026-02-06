"""
Learning Module - Adaptive learning from user interactions.

Implements:
1. Feedback collection (positive, negative, correction)
2. Pattern learning from corrections
3. Preference detection from behavior
4. Memory promotion based on usage

Inspired by OpenClaw's learning architecture.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from storage import SqliteStorage, SupabaseStorage
    Storage = SqliteStorage | SupabaseStorage


@dataclass
class Feedback:
    """User feedback on a response."""

    rating: str  # 'positive', 'negative', 'correction'
    correction_text: str | None = None
    response_text: str | None = None
    context: dict[str, Any] | None = None


@dataclass
class LearnedPattern:
    """A pattern learned from user corrections."""

    pattern_type: str
    trigger_text: str | None
    learned_action: str
    tool_name: str | None
    confidence: float


@dataclass
class LearnedPreference:
    """An automatically learned preference."""

    key: str
    value: str
    confidence: float
    source: str  # 'auto', 'explicit', 'correction'


# Common correction patterns to detect
CORRECTION_PATTERNS = [
    # Missing date patterns
    (r"não[,.]?\s*(era\s+)?pra?\s+(hoje|amanhã|segunda|terça|quarta|quinta|sexta|sábado|domingo|\d+)",
     "missing_date", "ask_due_date"),
    (r"pra\s+quando|qual\s+dia|que\s+dia",
     "missing_date", "ask_due_date"),

    # Wrong contact patterns
    (r"não[,.]?\s*(era\s+)?pro?\s+(\w+)",
     "wrong_contact", "confirm_contact"),
    (r"era\s+pra?\s+(\w+)[,.]?\s+não\s+pro?\s+(\w+)",
     "wrong_contact", "confirm_contact"),

    # Wrong category patterns
    (r"categoria\s+errada|não\s+é\s+(trabalho|pessoal|compras|urgente)",
     "wrong_category", "suggest_category"),

    # Missing time patterns
    (r"(que\s+horas?|qual\s+horário|não\s+era\s+às?\s+\d+)",
     "missing_time", "ask_time"),

    # Clarification needed
    (r"não\s+entend(eu|i)|confus|qual\s+(\w+)\s*\?",
     "ambiguous_request", "ask_clarification"),
]

# Preference detection patterns
PREFERENCE_PATTERNS = [
    # Meeting time preferences
    (r"reuni[ãõ]o.*(manhã|de\s+manhã|antes\s+d[ao]s?\s+\d{1,2}h?)",
     "preferred_meeting_time", "morning"),
    (r"reuni[ãõ]o.*(tarde|de\s+tarde|depois\s+d[ao]s?\s+\d{1,2}h?)",
     "preferred_meeting_time", "afternoon"),

    # Task category preferences
    (r"(sempre|geralmente|normalmente)\s+(trabalho|pessoal)",
     "default_task_category", None),  # Value extracted from match

    # Communication style
    (r"mais\s+(curto|breve|direto)",
     "response_style", "concise"),
    (r"mais\s+(detalh|explic|completo)",
     "response_style", "detailed"),
]


class LearningSystem:
    """Handles adaptive learning from user interactions."""

    def __init__(self, storage: Any):
        """
        Initialize the learning system.

        Args:
            storage: SqliteStorage or SupabaseStorage instance with learning methods
        """
        self.storage = storage
        self._pattern_cache: dict[str, list[LearnedPattern]] = {}

    # =========================================================================
    # Feedback Collection
    # =========================================================================

    def detect_feedback(self, message: str) -> Feedback | None:
        """
        Detect if a message is feedback on previous response.

        Args:
            message: User message text

        Returns:
            Feedback object if detected, None otherwise
        """
        message_lower = message.lower().strip()

        # Positive feedback indicators
        positive_patterns = [
            r"^(👍|ok|certo|isso|perfeito|obrigad[oa]?|valeu|beleza|show)[\s!.]*$",
            r"^(era\s+isso|isso\s+mesmo|exato|correto)[\s!.]*$",
        ]

        for pattern in positive_patterns:
            if re.match(pattern, message_lower):
                return Feedback(rating="positive")

        # Negative feedback indicators
        negative_patterns = [
            r"^(👎|não|errado|não\s+era\s+isso)[\s!.]*$",
            r"^(cancela|desfaz|volta)[\s!.]*$",
        ]

        for pattern in negative_patterns:
            if re.match(pattern, message_lower):
                return Feedback(rating="negative")

        # Correction patterns (extract what should have been)
        correction_patterns = [
            (r"não[,.]?\s*era\s+(.+)", 1),
            (r"queria\s+(.+)", 1),
            (r"era\s+pra\s+(.+)", 1),
            (r"deveria\s+ser\s+(.+)", 1),
            (r"o\s+certo\s+[ée]\s+(.+)", 1),
        ]

        for pattern, group in correction_patterns:
            match = re.search(pattern, message_lower)
            if match:
                correction_text = match.group(group).strip()
                return Feedback(rating="correction", correction_text=correction_text)

        return None

    def record_feedback(
        self,
        owner_id: str,
        feedback: Feedback,
        message_id: str | None = None,
    ) -> str | None:
        """
        Record user feedback in storage.

        Args:
            owner_id: User identifier
            feedback: Feedback object
            message_id: Optional message reference

        Returns:
            Feedback ID if recorded, None on error
        """
        try:
            result = self.storage.record_feedback(
                owner_id=owner_id,
                rating=feedback.rating,
                response_text=feedback.response_text,
                correction_text=feedback.correction_text,
                context=feedback.context or {},
            )
            return result.get("id") if result else None
        except Exception as e:
            print(f"[learning] Error recording feedback: {e}")
            return None

    # =========================================================================
    # Pattern Learning
    # =========================================================================

    def analyze_correction(
        self,
        original_message: str,
        correction: str,
        tool_used: str | None = None,
    ) -> LearnedPattern | None:
        """
        Analyze a correction to extract learning patterns.

        Args:
            original_message: The original user message
            correction: What the user said the correct action was
            tool_used: Which tool was used (if any)

        Returns:
            LearnedPattern if one can be extracted, None otherwise
        """
        correction_lower = correction.lower()

        for pattern, pattern_type, action in CORRECTION_PATTERNS:
            match = re.search(pattern, correction_lower)
            if match:
                # Extract trigger from original message (simplified)
                trigger = self._extract_trigger(original_message, pattern_type)

                return LearnedPattern(
                    pattern_type=pattern_type,
                    trigger_text=trigger,
                    learned_action=action,
                    tool_name=tool_used,
                    confidence=0.5,
                )

        return None

    def _extract_trigger(self, message: str, pattern_type: str) -> str | None:
        """Extract a normalized trigger from the original message."""
        message_lower = message.lower()

        if pattern_type == "missing_date":
            # Look for task-like messages without dates
            match = re.search(r"(tarefa|criar|adicionar)\s+(.{10,50})", message_lower)
            if match:
                return match.group(2)[:30]

        elif pattern_type == "wrong_contact":
            # Look for messages mentioning people
            match = re.search(r"(pra?o?|para|do)\s+(\w+)", message_lower)
            if match:
                return f"contact:{match.group(2)}"

        return None

    def learn_from_correction(
        self,
        owner_id: str,
        original_message: str,
        correction: str,
        tool_used: str | None = None,
    ) -> LearnedPattern | None:
        """
        Learn from a user correction and store the pattern.

        Args:
            owner_id: User identifier
            original_message: Original message that was misunderstood
            correction: User's correction
            tool_used: Which tool was involved

        Returns:
            LearnedPattern if learned, None otherwise
        """
        pattern = self.analyze_correction(original_message, correction, tool_used)

        if pattern:
            try:
                result = self.storage.learn_pattern(
                    owner_id=owner_id,
                    pattern_type=pattern.pattern_type,
                    trigger_text=pattern.trigger_text,
                    learned_action=pattern.learned_action,
                    tool_name=pattern.tool_name,
                )

                if result:
                    # Clear cache for this user
                    self._pattern_cache.pop(owner_id, None)
                    print(f"[learning] Learned pattern: {pattern.pattern_type} -> {pattern.learned_action}")
                    return pattern

            except Exception as e:
                print(f"[learning] Error learning pattern: {e}")

        return None

    def get_patterns(
        self,
        owner_id: str,
        min_confidence: float = 0.3,
    ) -> list[LearnedPattern]:
        """
        Get learned patterns for a user.

        Args:
            owner_id: User identifier
            min_confidence: Minimum confidence threshold

        Returns:
            List of learned patterns
        """
        # Check cache first
        cache_key = f"{owner_id}:{min_confidence}"
        if cache_key in self._pattern_cache:
            return self._pattern_cache[cache_key]

        try:
            patterns_data = self.storage.get_learned_patterns(
                owner_id=owner_id,
                min_confidence=min_confidence,
            )

            patterns = [
                LearnedPattern(
                    pattern_type=p["pattern_type"],
                    trigger_text=p.get("trigger_text"),
                    learned_action=p["learned_action"],
                    tool_name=p.get("tool_name"),
                    confidence=p.get("confidence", 0.5),
                )
                for p in patterns_data
            ]

            # Cache for 5 minutes
            self._pattern_cache[cache_key] = patterns
            return patterns

        except Exception as e:
            print(f"[learning] Error getting patterns: {e}")
            return []

    def check_patterns(
        self,
        owner_id: str,
        message: str,
        tool_name: str | None = None,
    ) -> str | None:
        """
        Check if any learned patterns apply to this message.

        Args:
            owner_id: User identifier
            message: Current user message
            tool_name: Tool about to be used

        Returns:
            Suggested action if a pattern matches, None otherwise
        """
        patterns = self.get_patterns(owner_id)
        message_lower = message.lower()

        for pattern in patterns:
            # Check if pattern applies
            matches = False

            if pattern.trigger_text:
                if pattern.trigger_text.startswith("contact:"):
                    contact_name = pattern.trigger_text[8:]
                    if contact_name in message_lower:
                        matches = True
                elif pattern.trigger_text in message_lower:
                    matches = True

            # Also match by tool name
            if tool_name and pattern.tool_name == tool_name:
                if pattern.pattern_type == "missing_date" and "tarefa" in message_lower:
                    # Check if message has a date
                    if not self._has_date(message_lower):
                        matches = True

            if matches and pattern.confidence >= 0.5:
                return pattern.learned_action

        return None

    def _has_date(self, message: str) -> bool:
        """Check if message contains a date reference."""
        date_patterns = [
            r"\d{1,2}/\d{1,2}",
            r"\d{1,2}\s+de\s+\w+",
            r"(hoje|amanhã|ontem)",
            r"(segunda|terça|quarta|quinta|sexta|sábado|domingo)",
            r"(próxim[ao]|semana\s+que\s+vem)",
            r"(\d{1,2}h|\d{1,2}:\d{2})",
        ]
        for pattern in date_patterns:
            if re.search(pattern, message):
                return True
        return False

    # =========================================================================
    # Preference Learning
    # =========================================================================

    def detect_preference(
        self,
        message: str,
        action_taken: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """
        Detect if message reveals a user preference.

        Args:
            message: User message
            action_taken: What action was taken

        Returns:
            Tuple of (preference_key, preference_value) or None
        """
        message_lower = message.lower()

        for pattern, pref_key, pref_value in PREFERENCE_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                # If value is None, extract from match
                if pref_value is None and match.lastindex:
                    pref_value = match.group(match.lastindex)

                return (pref_key, pref_value)

        # Learn from action context
        if action_taken:
            tool = action_taken.get("tool")
            params = action_taken.get("params", {})

            # Learn category preference from task creation
            if tool == "create_task":
                category = params.get("category")
                if category:
                    return ("frequently_used_category", category)

            # Learn time preference from appointments
            if tool == "create_appointment":
                scheduled_at = params.get("scheduled_at", "")
                hour_match = re.search(r"(\d{1,2})[:h]", scheduled_at)
                if hour_match:
                    hour = int(hour_match.group(1))
                    if hour < 12:
                        return ("preferred_meeting_time", "morning")
                    elif hour < 18:
                        return ("preferred_meeting_time", "afternoon")

        return None

    def learn_preference(
        self,
        owner_id: str,
        key: str,
        value: str,
        source: str = "auto",
    ) -> bool:
        """
        Record a learned preference.

        Args:
            owner_id: User identifier
            key: Preference key
            value: Preference value
            source: How it was learned

        Returns:
            True if recorded, False on error
        """
        try:
            self.storage.update_learned_preference(
                owner_id=owner_id,
                key=key,
                value=value,
                source=source,
            )
            return True
        except Exception as e:
            print(f"[learning] Error learning preference: {e}")
            return False

    def get_preferences(
        self,
        owner_id: str,
        min_confidence: float = 0.5,
    ) -> dict[str, LearnedPreference]:
        """
        Get learned preferences for a user.

        Args:
            owner_id: User identifier
            min_confidence: Minimum confidence threshold

        Returns:
            Dict of preference key -> LearnedPreference
        """
        try:
            prefs_data = self.storage.get_learned_preferences(
                owner_id=owner_id,
                min_confidence=min_confidence,
            )

            return {
                p["preference_key"]: LearnedPreference(
                    key=p["preference_key"],
                    value=p["preference_value"],
                    confidence=p.get("confidence", 0.5),
                    source=p.get("source", "auto"),
                )
                for p in prefs_data
            }

        except Exception as e:
            print(f"[learning] Error getting preferences: {e}")
            return {}

    # =========================================================================
    # Prompt Enhancement
    # =========================================================================

    def get_learning_context(self, owner_id: str) -> dict[str, Any]:
        """
        Get learning data to include in prompt context.

        Args:
            owner_id: User identifier

        Returns:
            Dict with patterns and preferences for prompt building
        """
        patterns = self.get_patterns(owner_id)
        preferences = self.get_preferences(owner_id)

        # Format patterns for prompt
        pattern_hints = []
        for p in patterns[:5]:  # Limit to 5 most confident
            if p.learned_action == "ask_due_date":
                pattern_hints.append("Quando criar tarefas, perguntar a data se não especificada")
            elif p.learned_action == "confirm_contact":
                pattern_hints.append("Confirmar nome do contato antes de atribuir tarefas")
            elif p.learned_action == "ask_time":
                pattern_hints.append("Perguntar horário para compromissos")

        # Format preferences for prompt
        pref_hints = {}
        for key, pref in preferences.items():
            if pref.confidence >= 0.7:
                pref_hints[key] = pref.value

        return {
            "patterns": patterns,
            "pattern_hints": pattern_hints,
            "preferences": pref_hints,
            "top_categories": pref_hints.get("frequently_used_category"),
            "time_preferences": pref_hints.get("preferred_meeting_time"),
            "communication_style": pref_hints.get("response_style", "normal"),
        }


# Singleton
_learning_system: LearningSystem | None = None


def get_learning_system(storage: Any) -> LearningSystem:
    """Get or create the learning system singleton."""
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem(storage)
    return _learning_system
