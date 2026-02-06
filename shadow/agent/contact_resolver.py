"""
ContactResolver - Resolves names mentioned in messages to known contacts.

Phase 2: Automatic task-contact linking via name resolution.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage import SqliteStorage, SupabaseStorage


class ResolvedContact:
    """Result of contact resolution."""

    def __init__(
        self,
        phone: str | None,
        name: str,
        source: str,
        confidence: float = 1.0,
    ):
        self.phone = phone
        self.name = name
        self.source = source  # "alias", "exact", "fuzzy", "none"
        self.confidence = confidence

    @property
    def resolved(self) -> bool:
        return self.phone is not None

    def __repr__(self) -> str:
        return f"ResolvedContact(phone={self.phone}, name={self.name}, source={self.source})"


class ContactResolver:
    """
    Resolves names mentioned in messages to known contact phones.

    Resolution priority:
    1. Exact match in shadow_contact_aliases
    2. Exact match in shadow_contact_context.contact_name
    3. Fuzzy match (LIKE %name%) in contact_context
    4. Return unresolved with original name
    """

    def __init__(self, storage: SqliteStorage | SupabaseStorage):
        self.storage = storage

    def resolve(self, owner_id: str, name: str) -> ResolvedContact:
        """
        Resolve a name to a contact phone.

        Args:
            owner_id: Owner's phone number (E164)
            name: Name or identifier to resolve

        Returns:
            ResolvedContact with phone (if found) and resolution source
        """
        if not name or not name.strip():
            return ResolvedContact(None, name, "none", 0.0)

        clean_name = name.strip()

        # 1. Check if it's already a phone number
        if self._is_phone_number(clean_name):
            normalized = self._normalize_phone(clean_name)
            return ResolvedContact(normalized, clean_name, "phone", 1.0)

        # 2. Try alias resolution
        phone = self.storage.resolve_alias(owner_id, clean_name)
        if phone:
            return ResolvedContact(phone, clean_name, "alias", 1.0)

        # 3. Try find_contact_by_name (handles exact + fuzzy)
        contact = self.storage.find_contact_by_name(owner_id, clean_name)
        if contact:
            phone = contact.get("contact_phone")
            resolved_name = contact.get("contact_name") or clean_name
            # Determine if exact or fuzzy match
            is_exact = resolved_name.lower() == clean_name.lower()
            source = "exact" if is_exact else "fuzzy"
            confidence = 1.0 if is_exact else 0.7
            return ResolvedContact(phone, resolved_name, source, confidence)

        # 4. Not found
        return ResolvedContact(None, clean_name, "none", 0.0)

    def resolve_multiple(
        self,
        owner_id: str,
        names: list[str],
    ) -> list[ResolvedContact]:
        """Resolve multiple names at once."""
        return [self.resolve(owner_id, name) for name in names]

    def extract_mentions(self, text: str) -> list[str]:
        """
        Extract potential name mentions from text.

        Looks for patterns like:
        - "para João"
        - "com Maria"
        - "ligar para o Pedro"
        - Names after common prepositions
        """
        mentions = []

        # Portuguese preposition patterns
        patterns = [
            r"(?:para|com|do|da|ao|à)\s+(?:o\s+|a\s+)?([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)?)",
            r"(?:ligar|falar|contatar|avisar|enviar)\s+(?:para\s+)?(?:o\s+|a\s+)?([A-ZÀ-Ú][a-zà-ú]+)",
            r"@([A-Za-z0-9_]+)",  # @mentions
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            mentions.extend(matches)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for m in mentions:
            if m.lower() not in seen:
                seen.add(m.lower())
                unique.append(m)

        return unique

    def _is_phone_number(self, text: str) -> bool:
        """Check if text looks like a phone number."""
        digits = re.sub(r"\D", "", text)
        return len(digits) >= 10 and len(digits) <= 15

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to E164 format."""
        digits = re.sub(r"\D", "", phone)
        if not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits
        return f"+{digits}"


def auto_link_task_contacts(
    storage: SqliteStorage | SupabaseStorage,
    owner_id: str,
    task_id: int | str,
    entity_data: dict,
    sender_phone: str | None,
    message_text: str | None = None,
) -> list[dict]:
    """
    Automatically link a task to relevant contacts.

    Called after entity extraction to create task-contact relationships.

    Args:
        storage: Storage instance
        owner_id: Owner's phone (E164)
        task_id: ID of the created task
        entity_data: Extracted entity data (contains assigned_to, etc.)
        sender_phone: Phone of message sender (requester)
        message_text: Original message for mention extraction

    Returns:
        List of linked contacts with their relation types
    """
    resolver = ContactResolver(storage)
    linked = []

    # 1. Link sender as "requester"
    if sender_phone:
        storage.link_task_to_contact(
            task_id=task_id,
            contact_phone=sender_phone,
            relation_type="requester",
        )
        linked.append({
            "phone": sender_phone,
            "relation": "requester",
            "source": "sender",
        })

    # 2. Link assigned_to as "assigned"
    assigned_to = entity_data.get("assigned_to")
    if assigned_to:
        resolved = resolver.resolve(owner_id, assigned_to)
        storage.link_task_to_contact(
            task_id=task_id,
            contact_phone=resolved.phone,
            contact_name=resolved.name,
            relation_type="assigned",
        )
        linked.append({
            "phone": resolved.phone,
            "name": resolved.name,
            "relation": "assigned",
            "source": resolved.source,
            "confidence": resolved.confidence,
        })

    # 3. Extract and link mentions from message
    if message_text:
        mentions = resolver.extract_mentions(message_text)
        for mention in mentions:
            # Skip if same as assigned_to
            if assigned_to and mention.lower() == assigned_to.lower():
                continue

            resolved = resolver.resolve(owner_id, mention)
            # Only link if we found a match
            if resolved.resolved:
                storage.link_task_to_contact(
                    task_id=task_id,
                    contact_phone=resolved.phone,
                    contact_name=resolved.name,
                    relation_type="mentioned",
                )
                linked.append({
                    "phone": resolved.phone,
                    "name": resolved.name,
                    "relation": "mentioned",
                    "source": resolved.source,
                    "confidence": resolved.confidence,
                })

    return linked
