"""3-tier user resolution for channel messages.

Resolution flow:
1. Lookup: Check shadow_channel_users for existing user
2. Auto-link: Match phone against Baileys instance owner_e164
3. Create: New standalone account (SaaS aberto)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ResolvedUser:
    """Result of user resolution."""

    owner_id: str
    is_new: bool
    user_type: str  # "standalone" | "baileys_linked"
    status: str  # "active" | "onboarding" | "blocked"


class UserResolver:
    """Resolves phone numbers to owner_ids via 3-tier lookup."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def resolve(
        self,
        phone_e164: str,
        display_name: str | None = None,
        channel: str = "evolution",
    ) -> ResolvedUser:
        """Resolve a phone number to an owner_id.

        Tier 1: Direct lookup in shadow_channel_users
        Tier 2: Auto-link if phone matches a Baileys instance owner_e164
        Tier 3: Create standalone account (SaaS aberto)
        """
        # Tier 1: Direct lookup
        user = self.storage.get_channel_user_by_phone(phone_e164)
        if user:
            # Update last_message_at
            now = datetime.now(timezone.utc).isoformat()
            self.storage.update_channel_user(
                phone_e164,
                last_message_at=now,
                last_window_opened_at=now,
            )
            if display_name and not user.get("display_name"):
                self.storage.update_channel_user(phone_e164, display_name=display_name)

            return ResolvedUser(
                owner_id=user["owner_id"],
                is_new=False,
                user_type=user.get("user_type", "standalone"),
                status=user.get("status", "active"),
            )

        # Tier 2: Auto-link by phone matching instance.owner_e164
        instance = self.storage.find_instance_by_phone(phone_e164)
        if instance:
            self.storage.create_channel_user(
                phone_e164=phone_e164,
                owner_id=phone_e164,
                instance_id=instance["id"],
                display_name=display_name,
                user_type="baileys_linked",
                channel=channel,
                status="active",
            )
            return ResolvedUser(
                owner_id=phone_e164,
                is_new=False,  # Not truly new - already has Baileys data
                user_type="baileys_linked",
                status="active",
            )

        # Tier 3: Create standalone account
        self.storage.create_channel_user(
            phone_e164=phone_e164,
            owner_id=phone_e164,
            display_name=display_name,
            user_type="standalone",
            channel=channel,
            status="onboarding",
        )
        return ResolvedUser(
            owner_id=phone_e164,
            is_new=True,
            user_type="standalone",
            status="onboarding",
        )
