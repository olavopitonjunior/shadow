"""
Proactive Suggestions System for Shadow MVP.

This module provides intelligent suggestion generation from
entity extraction, contact detection, and conversation analysis.

Components:
- types: Data structures (Suggestion, SuggestionBatch, etc.)
- processor: Creates suggestions from extracted entities
- sender: Sends suggestions to Shadow group with rate limiting
- responder: Handles user responses to suggestions
- formatter: Message formatting utilities
"""

from .types import (
    # Enums
    SuggestionType,
    SuggestionStatus,
    SuggestionPriority,
    SourceType,
    # Dataclasses
    Suggestion,
    SuggestionResponse,
    SuggestionBatch,
    RateLimitState,
    SuggestionConfig,
    # Constants
    CONFIDENCE_THRESHOLDS,
    # Functions
    get_priority_for_confidence,
)

from .processor import SuggestionProcessor, create_summary_suggestion
from .sender import SuggestionSender, get_suggestion_sender, reset_suggestion_sender
from .formatter import (
    format_single_suggestion,
    format_suggestion_batch,
    format_suggestion_list,
    format_acceptance_confirmation,
    format_rejection_confirmation,
    format_batch_acceptance,
    format_edit_prompt,
)
from .responder import SuggestionResponder, get_pending_for_owner

__all__ = [
    # Enums
    "SuggestionType",
    "SuggestionStatus",
    "SuggestionPriority",
    "SourceType",
    # Dataclasses
    "Suggestion",
    "SuggestionResponse",
    "SuggestionBatch",
    "RateLimitState",
    "SuggestionConfig",
    # Constants
    "CONFIDENCE_THRESHOLDS",
    # Functions
    "get_priority_for_confidence",
    # Processor
    "SuggestionProcessor",
    "create_summary_suggestion",
    # Sender
    "SuggestionSender",
    "get_suggestion_sender",
    "reset_suggestion_sender",
    # Formatter
    "format_single_suggestion",
    "format_suggestion_batch",
    "format_suggestion_list",
    "format_acceptance_confirmation",
    "format_rejection_confirmation",
    "format_batch_acceptance",
    "format_edit_prompt",
    # Responder
    "SuggestionResponder",
    "get_pending_for_owner",
]
