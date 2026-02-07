"""
Suggestion Processor - Creates suggestions from extracted entities.

This module processes unprocessed entities from the entity extractor
and creates suggestions for the user to review.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from .types import (
    Suggestion,
    SuggestionType,
    SuggestionPriority,
    SuggestionStatus,
    SourceType,
    SuggestionConfig,
    get_priority_for_confidence,
    CONFIDENCE_THRESHOLDS,
)


# Patterns for detecting urgency
URGENT_PATTERNS = [
    r"\burgente\b",
    r"\bagora\b",
    r"\bimediato\b",
    r"\bjá\b",
    r"\bhoje\b",
    r"\bpreciso\b",
    r"\bemergência\b",
]

# Patterns for detecting deadlines
DEADLINE_PATTERNS = [
    r"\bamanhã\b",
    r"\bhoje\b",
    r"\bsexta\b",
    r"\bsegunda\b",
    r"\bterça\b",
    r"\bquarta\b",
    r"\bquinta\b",
    r"\bsábado\b",
    r"\bdomingo\b",
    r"\bàs?\s+\d{1,2}[h:]\d{0,2}",
    r"\b\d{1,2}/\d{1,2}\b",
    r"\baté\s+(o\s+)?dia\b",
]


class SuggestionProcessor:
    """
    Processes extracted entities and creates suggestions.

    Example:
        processor = SuggestionProcessor(storage)
        new_suggestions = processor.process_pending_entities(owner_id)
    """

    def __init__(self, storage: Any):
        """
        Initialize the processor.

        Args:
            storage: Storage instance for database access
        """
        self.storage = storage

    def process_pending_entities(
        self,
        owner_id: str,
        config: SuggestionConfig | None = None,
    ) -> list[Suggestion]:
        """
        Process all unprocessed entities for an owner and create suggestions.

        Args:
            owner_id: Owner's phone number (E.164)
            config: Suggestion configuration (uses defaults if not provided)

        Returns:
            List of created suggestions
        """
        if config is None:
            settings = self.storage.get_user_settings(owner_id)
            config = SuggestionConfig.from_settings(settings)

        if not config.enabled:
            return []

        # Get unprocessed entities
        entities = self.storage.get_unprocessed_entities(
            owner_id=owner_id,
            min_confidence=config.min_confidence,
            limit=50,
        )

        if not entities:
            return []

        print(f"[processor] Processing {len(entities)} unprocessed entities for {owner_id[:8]}...")

        created_suggestions = []
        for entity in entities:
            try:
                suggestion = self.create_suggestion_from_entity(entity, config)
                if suggestion:
                    # Save to database
                    suggestion_id = self.storage.create_suggestion(
                        owner_id=suggestion.owner_id,
                        source_type=suggestion.source_type.value,
                        source_id=suggestion.source_id,
                        suggestion_type=suggestion.suggestion_type.value,
                        title=suggestion.title,
                        body=suggestion.body,
                        suggestion_data=suggestion.suggestion_data,
                        confidence=suggestion.confidence,
                        priority=suggestion.priority.value,
                        source_chat_id=suggestion.source_chat_id,
                        source_message_id=suggestion.source_message_id,
                        send_after=suggestion.send_after.isoformat() if suggestion.send_after else None,
                        expires_at=suggestion.expires_at.isoformat() if suggestion.expires_at else None,
                    )
                    suggestion.id = suggestion_id
                    created_suggestions.append(suggestion)

                    print(f"[processor] Created suggestion: {suggestion.suggestion_type.value} - {suggestion.title[:30]}...")

                # Mark entity as processed regardless of whether suggestion was created
                self.storage.mark_entity_processed(entity["id"])

            except Exception as e:
                print(f"[processor] Error processing entity {entity.get('id')}: {e}")
                # Still mark as processed to avoid retrying forever
                try:
                    self.storage.mark_entity_processed(entity["id"])
                except Exception:
                    pass

        print(f"[processor] Created {len(created_suggestions)} suggestions")
        return created_suggestions

    def create_suggestion_from_entity(
        self,
        entity: dict[str, Any],
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """
        Create a suggestion from an extracted entity.

        Args:
            entity: Entity dict from storage
            config: Suggestion configuration

        Returns:
            Suggestion or None if entity doesn't warrant a suggestion
        """
        entity_type = entity.get("entity_type")
        entity_data = entity.get("entity_data", {})
        confidence = entity.get("confidence", 0.5)

        # Check minimum confidence
        if confidence < config.min_confidence:
            return None

        # Route to appropriate handler
        if entity_type == "task":
            return self._create_task_suggestion(entity, entity_data, confidence, config)
        elif entity_type == "meeting":
            return self._create_appointment_suggestion(entity, entity_data, confidence, config)
        elif entity_type == "contact":
            return self._create_contact_suggestion(entity, entity_data, confidence, config)
        elif entity_type == "reminder":
            return self._create_reminder_suggestion(entity, entity_data, confidence, config)

        return None

    def _create_task_suggestion(
        self,
        entity: dict[str, Any],
        entity_data: dict[str, Any],
        confidence: float,
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """Create a task creation suggestion."""
        description = entity_data.get("description", "").strip()
        if not description:
            return None

        # Check for deadline and urgency
        full_text = f"{description} {entity_data.get('due_date', '')}".lower()
        has_deadline = self._has_deadline(full_text)
        is_urgent = self._is_urgent(full_text)

        # Calculate priority
        priority = get_priority_for_confidence(
            SuggestionType.CREATE_TASK,
            confidence,
            has_deadline=has_deadline,
            is_urgent=is_urgent,
        )

        # Build suggestion data (pre-filled tool params)
        suggestion_data = {
            "title": description,
        }
        if entity_data.get("due_date"):
            suggestion_data["due_date"] = entity_data["due_date"]
        if entity_data.get("priority"):
            suggestion_data["priority"] = entity_data["priority"]
        if entity_data.get("assigned_to"):
            suggestion_data["assigned_to"] = entity_data["assigned_to"]

        # Build body text
        body = self._build_task_body(entity, entity_data)

        return Suggestion(
            owner_id=entity.get("owner_id", ""),
            source_type=SourceType.ENTITY,
            source_id=entity.get("id"),
            source_chat_id=entity.get("source_chat_id"),
            source_message_id=entity.get("source_message_id"),
            suggestion_type=SuggestionType.CREATE_TASK,
            title=description[:100],  # Truncate long titles
            body=body,
            suggestion_data=suggestion_data,
            confidence=confidence,
            priority=priority,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=config.expiry_hours),
        )

    def _create_appointment_suggestion(
        self,
        entity: dict[str, Any],
        entity_data: dict[str, Any],
        confidence: float,
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """Create an appointment creation suggestion."""
        title = entity_data.get("title", "").strip()
        if not title:
            return None

        datetime_str = entity_data.get("datetime") or entity_data.get("scheduled_at")
        if not datetime_str:
            # Appointments need a time
            return None

        # Check urgency
        full_text = f"{title} {datetime_str}".lower()
        is_urgent = self._is_urgent(full_text)

        priority = get_priority_for_confidence(
            SuggestionType.CREATE_APPOINTMENT,
            confidence,
            has_deadline=True,  # Appointments always have a time
            is_urgent=is_urgent,
        )

        suggestion_data = {
            "title": title,
            "scheduled_at": datetime_str,
        }
        if entity_data.get("duration"):
            suggestion_data["duration"] = entity_data["duration"]
        if entity_data.get("location"):
            suggestion_data["location"] = entity_data["location"]
        if entity_data.get("participants"):
            suggestion_data["participants"] = entity_data["participants"]

        body = self._build_appointment_body(entity, entity_data)

        return Suggestion(
            owner_id=entity.get("owner_id", ""),
            source_type=SourceType.ENTITY,
            source_id=entity.get("id"),
            source_chat_id=entity.get("source_chat_id"),
            source_message_id=entity.get("source_message_id"),
            suggestion_type=SuggestionType.CREATE_APPOINTMENT,
            title=title[:100],
            body=body,
            suggestion_data=suggestion_data,
            confidence=confidence,
            priority=priority,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=config.expiry_hours),
        )

    def _create_contact_suggestion(
        self,
        entity: dict[str, Any],
        entity_data: dict[str, Any],
        confidence: float,
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """Create a contact creation suggestion."""
        name = entity_data.get("name", "").strip()
        phone = entity_data.get("phone", "").strip()

        if not name and not phone:
            return None

        # Check if contact already exists
        if phone:
            existing = self.storage.get_contact_context(
                entity.get("owner_id", ""),
                contact_phone=phone,
            )
            if existing:
                # Contact exists, maybe suggest update instead
                return self._create_contact_update_suggestion(entity, entity_data, existing, confidence, config)

        priority = get_priority_for_confidence(
            SuggestionType.CREATE_CONTACT,
            confidence,
        )

        suggestion_data = {}
        if name:
            suggestion_data["name"] = name
        if phone:
            suggestion_data["phone"] = phone
        if entity_data.get("email"):
            suggestion_data["email"] = entity_data["email"]
        if entity_data.get("relation") or entity_data.get("relationship"):
            suggestion_data["relationship"] = entity_data.get("relation") or entity_data.get("relationship")

        title = f"Adicionar contato: {name or phone}"
        body = self._build_contact_body(entity, entity_data)

        return Suggestion(
            owner_id=entity.get("owner_id", ""),
            source_type=SourceType.ENTITY,
            source_id=entity.get("id"),
            source_chat_id=entity.get("source_chat_id"),
            source_message_id=entity.get("source_message_id"),
            suggestion_type=SuggestionType.CREATE_CONTACT,
            title=title[:100],
            body=body,
            suggestion_data=suggestion_data,
            confidence=confidence,
            priority=priority,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=config.expiry_hours),
        )

    def _create_contact_update_suggestion(
        self,
        entity: dict[str, Any],
        entity_data: dict[str, Any],
        existing_contact: dict[str, Any],
        confidence: float,
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """Create a contact update suggestion when new info detected for existing contact."""
        # Check what's new
        updates = {}

        if entity_data.get("email") and not existing_contact.get("email"):
            updates["email"] = entity_data["email"]

        if entity_data.get("relation") and not existing_contact.get("relationship_type"):
            updates["relationship_type"] = entity_data["relation"]

        if not updates:
            return None

        phone = existing_contact.get("contact_phone", "")
        name = existing_contact.get("contact_name", phone)

        title = f"Atualizar contato: {name}"
        body = f"Novas informações detectadas para {name}:\n"
        for key, value in updates.items():
            body += f"- {key}: {value}\n"

        suggestion_data = {"identifier": phone}
        suggestion_data.update(updates)

        return Suggestion(
            owner_id=entity.get("owner_id", ""),
            source_type=SourceType.ENTITY,
            source_id=entity.get("id"),
            source_chat_id=entity.get("source_chat_id"),
            source_message_id=entity.get("source_message_id"),
            suggestion_type=SuggestionType.UPDATE_CONTACT,
            title=title[:100],
            body=body,
            suggestion_data=suggestion_data,
            confidence=confidence,
            priority=SuggestionPriority.NORMAL,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=config.expiry_hours),
        )

    def _create_reminder_suggestion(
        self,
        entity: dict[str, Any],
        entity_data: dict[str, Any],
        confidence: float,
        config: SuggestionConfig,
    ) -> Suggestion | None:
        """Create a reminder as a task suggestion (reminders are tasks with alerts)."""
        message = entity_data.get("message", "").strip()
        when = entity_data.get("when") or entity_data.get("remind_at")

        if not message:
            return None

        # Treat reminders as tasks
        suggestion_data = {
            "title": message,
        }
        if when:
            suggestion_data["due_date"] = when

        title = f"Lembrete: {message[:50]}"
        body = f"Criar lembrete: {message}"
        if when:
            body += f"\nQuando: {when}"

        return Suggestion(
            owner_id=entity.get("owner_id", ""),
            source_type=SourceType.ENTITY,
            source_id=entity.get("id"),
            source_chat_id=entity.get("source_chat_id"),
            source_message_id=entity.get("source_message_id"),
            suggestion_type=SuggestionType.CREATE_TASK,
            title=title[:100],
            body=body,
            suggestion_data=suggestion_data,
            confidence=confidence,
            priority=SuggestionPriority.HIGH,  # Reminders are usually important
            expires_at=datetime.now(timezone.utc) + timedelta(hours=config.expiry_hours),
        )

    def _has_deadline(self, text: str) -> bool:
        """Check if text contains deadline patterns."""
        for pattern in DEADLINE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _is_urgent(self, text: str) -> bool:
        """Check if text contains urgency patterns."""
        for pattern in URGENT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _build_task_body(self, entity: dict, entity_data: dict) -> str:
        """Build descriptive body for task suggestion."""
        lines = []

        if entity_data.get("due_date"):
            lines.append(f"Data: {entity_data['due_date']}")

        if entity_data.get("assigned_to"):
            lines.append(f"Atribuído a: {entity_data['assigned_to']}")

        if entity_data.get("priority"):
            lines.append(f"Prioridade: {entity_data['priority']}")

        # Add origin info - use REAL sender phone/name (not from entity_data which may be invented)
        sender_name = entity.get("sender_name")
        sender_phone = entity.get("sender_phone")

        # Build origin string with real sender info
        origin_parts = []
        if sender_name:
            origin_parts.append(sender_name)
        if sender_phone:
            # Skip LID identifiers (WhatsApp internal IDs, not real phone numbers)
            if "@lid" in sender_phone or "@g.us" in sender_phone:
                pass  # Don't show LID, just use sender_name
            else:
                # Format phone nicely
                phone = sender_phone
                # Clean any JID suffix
                if "@" in phone:
                    phone = phone.split("@")[0]
                # Add +55 if no country code
                if phone and not phone.startswith("+"):
                    phone = f"+55{phone}"
                origin_parts.append(phone)

        if origin_parts:
            lines.append(f"De: {' - '.join(origin_parts)}")
        else:
            # Fallback to source_chat_id if no sender info
            source_chat = entity.get("source_chat_id", "")
            if source_chat:
                chat_name = source_chat.split("@")[0] if "@" in source_chat else source_chat
                lines.append(f"Origem: {chat_name}")

        extracted_at = entity.get("extracted_at", "")
        if extracted_at:
            time_part = extracted_at[11:16] if len(extracted_at) > 16 else ""
            if time_part:
                lines.append(f"Detectado às: {time_part}")

        return "\n".join(lines) if lines else "Detectado em conversa"

    def _build_appointment_body(self, entity: dict, entity_data: dict) -> str:
        """Build descriptive body for appointment suggestion."""
        lines = []

        datetime_str = entity_data.get("datetime") or entity_data.get("scheduled_at", "")
        if datetime_str:
            lines.append(f"Horário: {datetime_str}")

        if entity_data.get("duration"):
            lines.append(f"Duração: {entity_data['duration']} min")

        if entity_data.get("location"):
            lines.append(f"Local: {entity_data['location']}")

        if entity_data.get("participants"):
            participants = entity_data["participants"]
            if isinstance(participants, list):
                participants = ", ".join(participants)
            lines.append(f"Participantes: {participants}")

        # Add origin info - use REAL sender phone/name
        sender_name = entity.get("sender_name")
        sender_phone = entity.get("sender_phone")

        origin_parts = []
        if sender_name:
            origin_parts.append(sender_name)
        if sender_phone:
            # Skip LID identifiers (WhatsApp internal IDs, not real phone numbers)
            if "@lid" in sender_phone or "@g.us" in sender_phone:
                pass  # Don't show LID, just use sender_name
            else:
                phone = sender_phone
                if "@" in phone:
                    phone = phone.split("@")[0]
                if phone and not phone.startswith("+"):
                    phone = f"+55{phone}"
                origin_parts.append(phone)

        if origin_parts:
            lines.append(f"De: {' - '.join(origin_parts)}")
        else:
            source_chat = entity.get("source_chat_id", "")
            if source_chat:
                chat_name = source_chat.split("@")[0] if "@" in source_chat else source_chat
                lines.append(f"Origem: {chat_name}")

        return "\n".join(lines) if lines else "Detectado em conversa"

    def _build_contact_body(self, entity: dict, entity_data: dict) -> str:
        """Build descriptive body for contact suggestion."""
        lines = []

        # For contact suggestions, use sender info as the contact's real phone/name
        sender_name = entity.get("sender_name")
        sender_phone = entity.get("sender_phone")

        # Prefer real sender info over entity_data (which may be invented by LLM)
        name = sender_name or entity_data.get("name")
        phone = sender_phone or entity_data.get("phone")

        if name:
            lines.append(f"Nome: {name}")

        if phone:
            # Skip LID identifiers (WhatsApp internal IDs, not real phone numbers)
            if "@lid" not in phone and "@g.us" not in phone:
                if "@" in phone:
                    phone = phone.split("@")[0]
                if not phone.startswith("+"):
                    phone = f"+55{phone}"
                lines.append(f"Telefone: {phone}")

        if entity_data.get("email"):
            lines.append(f"Email: {entity_data['email']}")

        if entity_data.get("relation") or entity_data.get("relationship"):
            rel = entity_data.get("relation") or entity_data.get("relationship")
            lines.append(f"Relação: {rel}")

        if entity_data.get("context"):
            lines.append(f"Contexto: {entity_data['context']}")

        return "\n".join(lines) if lines else "Detectado em conversa"

    def calculate_priority(
        self,
        entity_type: str,
        confidence: float,
        has_deadline: bool = False,
        is_urgent: bool = False,
    ) -> SuggestionPriority:
        """
        Calculate suggestion priority.

        Args:
            entity_type: Type of entity
            confidence: Confidence score (0-1)
            has_deadline: Whether entity has a deadline
            is_urgent: Whether urgent keywords detected

        Returns:
            Priority level
        """
        suggestion_type_map = {
            "task": SuggestionType.CREATE_TASK,
            "meeting": SuggestionType.CREATE_APPOINTMENT,
            "contact": SuggestionType.CREATE_CONTACT,
            "reminder": SuggestionType.CREATE_TASK,
        }
        suggestion_type = suggestion_type_map.get(entity_type, SuggestionType.CREATE_TASK)

        return get_priority_for_confidence(
            suggestion_type,
            confidence,
            has_deadline=has_deadline,
            is_urgent=is_urgent,
        )


def create_summary_suggestion(
    storage: Any,
    owner_id: str,
    contact_phone: str,
    contact_name: str | None,
    summary_text: str,
    topics: list[str] | None = None,
) -> Suggestion | None:
    """
    Create a conversation summary suggestion.

    Called by the summarizer when a conversation reaches the summary threshold.

    Args:
        storage: Storage instance
        owner_id: Owner's phone
        contact_phone: Contact's phone
        contact_name: Contact's name (optional)
        summary_text: Generated summary
        topics: Discussion topics

    Returns:
        Created suggestion or None
    """
    name = contact_name or contact_phone

    title = f"Resumo: conversa com {name}"
    body = summary_text
    if topics:
        body += f"\n\nTópicos: {', '.join(topics[:5])}"

    suggestion_data = {
        "contact_phone": contact_phone,
        "contact_name": contact_name,
        "summary": summary_text,
        "topics": topics or [],
    }

    try:
        suggestion_id = storage.create_suggestion(
            owner_id=owner_id,
            source_type="summary",
            source_id=None,
            suggestion_type="conversation_summary",
            title=title[:100],
            body=body,
            suggestion_data=suggestion_data,
            confidence=0.8,
            priority=SuggestionPriority.LOW.value,  # Summaries are informational
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
        )

        return Suggestion(
            id=suggestion_id,
            owner_id=owner_id,
            source_type=SourceType.SUMMARY,
            suggestion_type=SuggestionType.CONVERSATION_SUMMARY,
            title=title,
            body=body,
            suggestion_data=suggestion_data,
            confidence=0.8,
            priority=SuggestionPriority.LOW,
        )
    except Exception as e:
        print(f"[processor] Error creating summary suggestion: {e}")
        return None
