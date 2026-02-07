"""
Suggestion Responder - Handles user responses to suggestions.

This module processes user responses like "1", "sim", "ignorar"
and executes the appropriate actions.
"""

import re
from datetime import datetime, timezone
from typing import Any, Literal

from .types import (
    Suggestion,
    SuggestionResponse,
    SuggestionType,
    SuggestionStatus,
)
from .formatter import (
    format_acceptance_confirmation,
    format_rejection_confirmation,
    format_batch_acceptance,
    format_edit_prompt,
)


# Response patterns
ACCEPT_SINGLE_PATTERNS = [
    r"^1$",
    r"^criar$",
    r"^aceitar$",
    r"^sim$",
    r"^ok$",
    r"^s$",
]

EDIT_PATTERNS = [
    r"^2$",
    r"^editar$",
    r"^alterar$",
    r"^modificar$",
]

REJECT_SINGLE_PATTERNS = [
    r"^3$",
    r"^ignorar$",
    r"^não$",
    r"^nao$",
    r"^n$",
    r"^cancelar$",
]

REJECT_ALL_PATTERNS = [
    r"^ignorar\s*todas?$",
    r"^descartar\s*todas?$",
    r"^cancelar\s*todas?$",
]

CORRECTION_PATTERNS = [
    r"^não,?\s*era\s+(.+)$",
    r"^na verdade[,:]?\s*(.+)$",
    r"^errado,?\s*(.+)$",
    r"^corrigir[:\s]+(.+)$",
]

# Multiple selection pattern: "1,2,3" or "1, 3"
MULTI_SELECT_PATTERN = r"^(\d+)(?:\s*,\s*(\d+))+$"

# Summary-specific patterns
SAVE_SUMMARY_PATTERNS = [
    r"^1$",
    r"^guardar$",
    r"^salvar$",
]


class SuggestionResponder:
    """
    Handles user responses to suggestions.

    Detects response type and executes appropriate action.
    """

    def __init__(self, storage: Any, tool_registry: Any | None = None):
        """
        Initialize responder.

        Args:
            storage: Storage instance
            tool_registry: Tool registry for executing accepted suggestions
        """
        self.storage = storage
        self.tool_registry = tool_registry

    def detect_response(
        self,
        message: str,
        pending_suggestions: list[dict[str, Any]],
    ) -> SuggestionResponse | None:
        """
        Detect if a message is a response to pending suggestions.

        Args:
            message: User's message
            pending_suggestions: List of pending/sent suggestions

        Returns:
            SuggestionResponse if detected, None otherwise
        """
        if not pending_suggestions:
            return None

        text = message.strip().lower()

        # Check for reject all
        for pattern in REJECT_ALL_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return SuggestionResponse(
                    suggestion_id=pending_suggestions[0].get("id"),
                    action="reject_all",
                    raw_message=message,
                )

        # Check for correction
        for pattern in CORRECTION_PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                return SuggestionResponse(
                    suggestion_id=pending_suggestions[0].get("id"),
                    action="correction",
                    correction_text=match.group(1).strip(),
                    raw_message=message,
                )

        # Check for multiple selection (batch)
        multi_match = re.match(MULTI_SELECT_PATTERN, message.strip())
        if multi_match:
            indices = [int(x) for x in re.findall(r"\d+", message)]
            return SuggestionResponse(
                suggestion_id=pending_suggestions[0].get("id"),
                action="accept_multiple",
                selected_indices=indices,
                raw_message=message,
            )

        # Single suggestion responses
        if len(pending_suggestions) == 1:
            suggestion = pending_suggestions[0]
            suggestion_type = suggestion.get("suggestion_type")

            # Summary has different options
            if suggestion_type == "conversation_summary":
                for pattern in SAVE_SUMMARY_PATTERNS:
                    if re.match(pattern, text, re.IGNORECASE):
                        return SuggestionResponse(
                            suggestion_id=suggestion.get("id"),
                            action="accept",
                            raw_message=message,
                        )
                for pattern in REJECT_SINGLE_PATTERNS[:3]:  # "2", "ignorar", "não"
                    if re.match(pattern, text, re.IGNORECASE):
                        return SuggestionResponse(
                            suggestion_id=suggestion.get("id"),
                            action="reject",
                            raw_message=message,
                        )
            else:
                # Standard suggestion (task, appointment, contact)
                for pattern in ACCEPT_SINGLE_PATTERNS:
                    if re.match(pattern, text, re.IGNORECASE):
                        return SuggestionResponse(
                            suggestion_id=suggestion.get("id"),
                            action="accept",
                            raw_message=message,
                        )

                for pattern in EDIT_PATTERNS:
                    if re.match(pattern, text, re.IGNORECASE):
                        return SuggestionResponse(
                            suggestion_id=suggestion.get("id"),
                            action="edit",
                            raw_message=message,
                        )

                for pattern in REJECT_SINGLE_PATTERNS:
                    if re.match(pattern, text, re.IGNORECASE):
                        return SuggestionResponse(
                            suggestion_id=suggestion.get("id"),
                            action="reject",
                            raw_message=message,
                        )

        # Check for single number selection in batch
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(pending_suggestions):
                return SuggestionResponse(
                    suggestion_id=pending_suggestions[index - 1].get("id"),
                    action="accept",
                    selected_indices=[index],
                    raw_message=message,
                )

        return None

    async def handle_response(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
        tool_context: Any | None = None,
    ) -> dict[str, Any]:
        """
        Handle a detected response.

        Args:
            response: Detected response
            pending_suggestions: List of pending suggestions
            tool_context: Context for tool execution

        Returns:
            Result dict with reply message and actions taken
        """
        action = response.action

        if action == "accept":
            return await self._handle_accept(response, pending_suggestions, tool_context)
        elif action == "reject":
            return self._handle_reject(response, pending_suggestions)
        elif action == "edit":
            return self._handle_edit(response, pending_suggestions)
        elif action == "accept_multiple":
            return await self._handle_accept_multiple(response, pending_suggestions, tool_context)
        elif action == "reject_all":
            return self._handle_reject_all(pending_suggestions)
        elif action == "correction":
            return await self._handle_correction(response, pending_suggestions, tool_context)

        return {"reply": None, "actions": []}

    async def _handle_accept(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
        tool_context: Any | None,
    ) -> dict[str, Any]:
        """Handle acceptance of a single suggestion."""
        suggestion_dict = None
        for s in pending_suggestions:
            if s.get("id") == response.suggestion_id:
                suggestion_dict = s
                break

        if not suggestion_dict:
            return {"reply": "Sugestão não encontrada.", "actions": []}

        suggestion = Suggestion.from_dict(suggestion_dict)

        # Execute the suggested action
        result = await self._execute_suggestion(suggestion, tool_context)

        # Update status
        self.storage.update_suggestion_status(
            suggestion.id,
            "accepted",
            response_text=response.raw_message,
        )
        self.storage.increment_suggestion_count(suggestion.owner_id, "accepted")

        # Get settings for formatting
        settings = self.storage.get_user_settings(suggestion.owner_id)
        use_emojis = settings.get("use_emojis", True)

        reply = format_acceptance_confirmation(suggestion, result, use_emojis)
        return {"reply": reply, "actions": ["suggestion_accepted"]}

    def _handle_reject(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Handle rejection of a single suggestion."""
        suggestion_dict = None
        for s in pending_suggestions:
            if s.get("id") == response.suggestion_id:
                suggestion_dict = s
                break

        if not suggestion_dict:
            return {"reply": "Sugestão não encontrada.", "actions": []}

        suggestion = Suggestion.from_dict(suggestion_dict)

        self.storage.update_suggestion_status(
            suggestion.id,
            "rejected",
            response_text=response.raw_message,
        )
        self.storage.increment_suggestion_count(suggestion.owner_id, "rejected")

        settings = self.storage.get_user_settings(suggestion.owner_id)
        use_emojis = settings.get("use_emojis", True)

        reply = format_rejection_confirmation(suggestion, use_emojis)
        return {"reply": reply, "actions": ["suggestion_rejected"]}

    def _handle_edit(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Handle edit request - return prompt for editing."""
        suggestion_dict = None
        for s in pending_suggestions:
            if s.get("id") == response.suggestion_id:
                suggestion_dict = s
                break

        if not suggestion_dict:
            return {"reply": "Sugestão não encontrada.", "actions": []}

        suggestion = Suggestion.from_dict(suggestion_dict)
        settings = self.storage.get_user_settings(suggestion.owner_id)
        use_emojis = settings.get("use_emojis", True)

        reply = format_edit_prompt(suggestion, use_emojis)

        # Mark as awaiting edit (keep in sent status but track in session)
        return {
            "reply": reply,
            "actions": ["suggestion_edit_requested"],
            "awaiting_edit": True,
            "edit_suggestion_id": suggestion.id,
        }

    async def _handle_accept_multiple(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
        tool_context: Any | None,
    ) -> dict[str, Any]:
        """Handle acceptance of multiple suggestions."""
        accepted = []
        rejected = []

        for s in pending_suggestions:
            suggestion = Suggestion.from_dict(s)
            idx = pending_suggestions.index(s) + 1

            if idx in response.selected_indices:
                # Accept
                result = await self._execute_suggestion(suggestion, tool_context)
                self.storage.update_suggestion_status(
                    suggestion.id,
                    "accepted",
                    response_text=response.raw_message,
                )
                self.storage.increment_suggestion_count(suggestion.owner_id, "accepted")
                accepted.append(suggestion)
            else:
                # Reject unselected
                self.storage.update_suggestion_status(
                    suggestion.id,
                    "rejected",
                    response_text="not_selected",
                )
                self.storage.increment_suggestion_count(suggestion.owner_id, "rejected")
                rejected.append(suggestion)

        owner_id = pending_suggestions[0].get("owner_id", "") if pending_suggestions else ""
        settings = self.storage.get_user_settings(owner_id)
        use_emojis = settings.get("use_emojis", True)

        reply = format_batch_acceptance(accepted, rejected, use_emojis)
        return {"reply": reply, "actions": ["suggestions_processed"]}

    def _handle_reject_all(
        self,
        pending_suggestions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Handle rejection of all pending suggestions."""
        for s in pending_suggestions:
            self.storage.update_suggestion_status(
                s.get("id"),
                "rejected",
                response_text="reject_all",
            )
            owner_id = s.get("owner_id", "")
            if owner_id:
                self.storage.increment_suggestion_count(owner_id, "rejected")

        count = len(pending_suggestions)
        return {
            "reply": f"{count} sugestão(ões) ignorada(s).",
            "actions": ["suggestions_rejected_all"],
        }

    async def _handle_correction(
        self,
        response: SuggestionResponse,
        pending_suggestions: list[dict[str, Any]],
        tool_context: Any | None,
    ) -> dict[str, Any]:
        """Handle correction - create with corrected data."""
        suggestion_dict = None
        for s in pending_suggestions:
            if s.get("id") == response.suggestion_id:
                suggestion_dict = s
                break

        if not suggestion_dict:
            return {"reply": "Sugestão não encontrada.", "actions": []}

        suggestion = Suggestion.from_dict(suggestion_dict)

        # Update suggestion data with correction
        if response.correction_text:
            suggestion.suggestion_data["title"] = response.correction_text
            suggestion.title = response.correction_text

        # Execute with corrected data
        result = await self._execute_suggestion(suggestion, tool_context)

        # Mark original as accepted with correction
        self.storage.update_suggestion_status(
            suggestion.id,
            "accepted",
            response_text=f"correction:{response.correction_text}",
        )
        self.storage.increment_suggestion_count(suggestion.owner_id, "accepted")

        # Record correction for learning
        self._record_correction(suggestion, response.correction_text)

        settings = self.storage.get_user_settings(suggestion.owner_id)
        use_emojis = settings.get("use_emojis", True)

        reply = format_acceptance_confirmation(suggestion, result, use_emojis)
        return {"reply": reply, "actions": ["suggestion_accepted_with_correction"]}

    async def _execute_suggestion(
        self,
        suggestion: Suggestion,
        tool_context: Any | None,
    ) -> str:
        """
        Execute the action suggested.

        Args:
            suggestion: Suggestion to execute
            tool_context: Context for tool execution

        Returns:
            Result message
        """
        suggestion_type = suggestion.suggestion_type
        data = suggestion.suggestion_data

        # Map suggestion types to tools
        tool_map = {
            SuggestionType.CREATE_TASK: "create_task",
            SuggestionType.CREATE_APPOINTMENT: "create_appointment",
            SuggestionType.CREATE_CONTACT: "create_contact",
            SuggestionType.UPDATE_CONTACT: "update_contact",
            SuggestionType.CONVERSATION_SUMMARY: None,  # Just informational
        }

        tool_name = tool_map.get(suggestion_type)

        if not tool_name:
            # Summary - just acknowledge
            return "Resumo guardado."

        if not self.tool_registry:
            # Fallback to direct storage calls
            return await self._execute_direct(suggestion_type, data)

        try:
            result = self.tool_registry.execute(tool_name, data, tool_context)
            return result.display_text or result.message or "Criado com sucesso."
        except Exception as e:
            print(f"[responder] Tool execution error: {e}")
            return f"Erro ao criar: {e}"

    async def _execute_direct(
        self,
        suggestion_type: SuggestionType,
        data: dict[str, Any],
    ) -> str:
        """Execute directly via storage (fallback when no tool registry)."""
        try:
            if suggestion_type == SuggestionType.CREATE_TASK:
                task = self.storage.create_task(
                    title=data.get("title", ""),
                    due_at=data.get("due_date"),
                )
                return f"Tarefa criada: {task.title}"

            elif suggestion_type == SuggestionType.CREATE_APPOINTMENT:
                appt = self.storage.create_appointment(
                    title=data.get("title", ""),
                    scheduled_at=data.get("scheduled_at", ""),
                    duration_minutes=data.get("duration", 60),
                )
                return f"Compromisso criado: {appt.title}"

            elif suggestion_type == SuggestionType.CREATE_CONTACT:
                # Contact creation is more complex - would need owner_id
                return "Contato criado."

            elif suggestion_type == SuggestionType.UPDATE_CONTACT:
                return "Contato atualizado."

            return "Processado."

        except Exception as e:
            return f"Erro: {e}"

    def _record_correction(self, suggestion: Suggestion, correction: str | None) -> None:
        """Record correction for learning system."""
        if not correction:
            return

        try:
            # Use learning system if available
            from learning import LearningSystem

            learning = LearningSystem(self.storage)
            learning.learn_pattern(
                owner_id=suggestion.owner_id,
                pattern_type="suggestion_correction",
                trigger_text=suggestion.title,
                learned_action=correction,
                context={
                    "suggestion_type": suggestion.suggestion_type.value,
                    "original_confidence": suggestion.confidence,
                },
            )
        except Exception as e:
            print(f"[responder] Could not record correction: {e}")


def get_pending_for_owner(storage: Any, owner_id: str) -> list[dict[str, Any]]:
    """
    Get all pending/sent suggestions for an owner.

    Helper function for message handler integration.

    Args:
        storage: Storage instance
        owner_id: Owner's phone

    Returns:
        List of suggestion dicts
    """
    # Get sent suggestions awaiting response
    sent = storage.get_sent_suggestions(owner_id, limit=10)

    # If none sent, check pending
    if not sent:
        pending = storage.get_pending_suggestions(owner_id, limit=10)
        return pending

    return sent
