"""
ReAct Agent - Agentic loop with multi-provider LLM support.

Implements the ReAct (Reasoning + Acting) pattern:
Think → Act → Observe → Repeat until done.

Uses LiteLLM via the providers/ package for multi-model support
(Anthropic, OpenAI, Gemini, DeepSeek).
"""

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from agent directory
_agent_dir = Path(__file__).parent
load_dotenv(_agent_dir / ".env")

from tools import ToolRegistry, ToolContext, get_tool_registry, setup_default_tools
from tool_adapter import (
    to_claude_tools,
    to_openai_tools,
    format_tool_result,
    format_tool_result_openai,
)
from agent_config import AgentConfig, SYSTEM_PROMPT
from prompt_builder import get_prompt_builder
from sessions import get_session_store
from providers import LLMProvider, LLMResponse, ToolCallRequest, get_provider

# Ensure tools are registered at import time
setup_default_tools()


class AgentStatus(str, Enum):
    """Status of the agent execution."""
    THINKING = "thinking"
    ACTING = "acting"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentStep:
    """A single step in the ReAct loop."""
    iteration: int
    status: AgentStatus
    thought: str | None = None
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    tool_result: str | None = None
    error: str | None = None


@dataclass
class AgentState:
    """State of a single agent invocation."""
    session_id: str
    message: str
    steps: list[AgentStep] = field(default_factory=list)
    status: AgentStatus = AgentStatus.THINKING
    final_response: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    @property
    def iteration(self) -> int:
        """Current iteration count."""
        return len(self.steps)

    @property
    def last_tool(self) -> str | None:
        """Name of the last tool executed."""
        for step in reversed(self.steps):
            if step.tool_name:
                return step.tool_name
        return None


class ReActAgent:
    """
    ReAct Agent using LiteLLM for multi-provider LLM support.

    Implements the same agentic pattern as OpenClaw:
    - Multi-turn conversation with tool results
    - Automatic iteration until goal is achieved
    - Error handling and recovery

    Supports: Anthropic Claude, OpenAI GPT, Google Gemini, DeepSeek.

    Example:
        agent = ReActAgent()
        state = agent.run("achar contato do João e criar tarefa", context)
        print(state.final_response)
    """

    def __init__(
        self,
        api_key: str | None = None,
        registry: ToolRegistry | None = None,
        config: AgentConfig | None = None,
        provider: LLMProvider | None = None,
    ):
        """
        Initialize the ReAct agent.

        Args:
            api_key: API key (uses env var if not provided)
            registry: Tool registry (uses global registry if not provided)
            config: Agent configuration (uses defaults if not provided)
            provider: LLM provider (auto-detected if not provided)
        """
        self.registry = registry or get_tool_registry()
        self.config = config or AgentConfig.from_env()

        # Initialize LLM provider
        if provider:
            self.provider = provider
        else:
            provider_name = self.config.provider if self.config.provider != "auto" else None
            self.provider = get_provider(
                provider_name=provider_name,
                model=self.config.model,
                api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            )

        # Progressive tool loading: start with Tier 1 only
        # Use OpenAI format (LiteLLM uses OpenAI format for all providers)
        self.tools = to_openai_tools(self.registry, tier=1)
        self._all_tools = to_openai_tools(self.registry)

        print(f"[react_agent] Initialized with {self.config.model}")
        print(f"[react_agent] Provider: {self.provider.__class__.__name__}")
        print(f"[react_agent] Tier 1 tools: {len(self.tools)}, Total available: {len(self._all_tools)}")

    def _build_dynamic_prompt(self, context: ToolContext) -> str:
        """
        Build a dynamic system prompt using PromptBuilder with user data.

        Falls back to the static SYSTEM_PROMPT if data cannot be loaded.
        """
        if not context.storage or not context.user_phone:
            return SYSTEM_PROMPT

        try:
            storage = context.storage
            owner_id = context.user_phone

            # Fetch user settings
            settings = storage.get_user_settings(owner_id)

            # Fetch learned patterns and convert to summary format
            learned_patterns: dict[str, Any] = {}
            try:
                preferences = storage.get_learned_preferences(owner_id)
                for pref in preferences:
                    key = pref.get("preference_key", "")
                    value = pref.get("preference_value", "")
                    if "time" in key or "horário" in key.lower():
                        learned_patterns["time_preferences"] = value
                    elif "categor" in key.lower():
                        learned_patterns["top_categories"] = value
                    elif "contact" in key.lower() or "contato" in key.lower():
                        learned_patterns["frequent_contacts"] = value
                    elif "style" in key.lower() or "estilo" in key.lower():
                        learned_patterns["communication_style"] = value
            except Exception as e:
                print(f"[react_agent] Could not load preferences: {e}")

            # Fetch recent corrections (patterns with high confidence)
            recent_corrections: list[dict] = []
            try:
                patterns = storage.get_learned_patterns(owner_id, min_confidence=0.5)
                recent_corrections = patterns[:5]
            except Exception as e:
                print(f"[react_agent] Could not load patterns: {e}")

            # Fetch important memories (high importance, no specific contact)
            important_memories: list[str] = []
            try:
                memories = storage.list_contact_memories(owner_id, limit=10)
                important_memories = [
                    m.get("text", "") for m in memories
                    if m.get("importance", 0) >= 0.7 and m.get("text")
                ][:10]
            except Exception as e:
                print(f"[react_agent] Could not load memories: {e}")

            builder = get_prompt_builder()
            prompt = builder.build_system_prompt(
                settings=settings,
                learned_patterns=learned_patterns if learned_patterns else None,
                recent_corrections=recent_corrections if recent_corrections else None,
                important_memories=important_memories if important_memories else None,
            )

            print(f"[react_agent] Built dynamic prompt ({len(prompt)} chars)")
            return prompt

        except Exception as e:
            print(f"[react_agent] Failed to build dynamic prompt, using static: {e}")
            return SYSTEM_PROMPT

    def run(self, message: str, context: ToolContext) -> AgentState:
        """
        Execute the ReAct loop for a user message.

        Args:
            message: User message to process
            context: Tool execution context

        Returns:
            AgentState with final response and execution trace
        """
        state = AgentState(
            session_id=context.session_id or "",
            message=message,
        )

        # Build dynamic system prompt with user preferences and learned patterns
        system_prompt = self._build_dynamic_prompt(context)

        # Retrieve conversation history from session for context continuity
        history: list[dict[str, Any]] = []
        if context.session_id:
            try:
                session_store = get_session_store()
                # Get last 10 messages for context
                history = session_store.get_context_for_llm(context.session_id, limit=10)
                if history:
                    print(f"[react_agent] Loaded {len(history)} messages from session history")
            except Exception as e:
                print(f"[react_agent] Warning: Could not load session history: {e}")

        # Build conversation: history + current message
        # Note: message_handler may have already added current message to session,
        # so check if last history message matches to avoid duplicates
        if history and history[-1].get("role") == "user" and history[-1].get("content") == message:
            # Current message already in history, use as-is
            messages: list[dict[str, Any]] = history
        else:
            # Add current message to history
            messages: list[dict[str, Any]] = history + [{"role": "user", "content": message}]

        print(f"[react_agent] Processing: {message[:50]}...")

        # Track dynamically loaded tools for this conversation
        _loaded_extra_tools: set[str] = set()
        # Start with tier 1 tools
        active_tools = self.tools

        while state.iteration < self.config.max_iterations:
            step = AgentStep(iteration=state.iteration, status=AgentStatus.THINKING)

            try:
                # Call LLM via provider
                _t0 = time.monotonic()
                response: LLMResponse = self.provider.chat(
                    messages=messages,
                    tools=active_tools,
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    system=system_prompt,
                )
                _latency = int((time.monotonic() - _t0) * 1000)

                # Track token usage
                state.total_input_tokens += response.input_tokens
                state.total_output_tokens += response.output_tokens

                # Record API usage for cost tracking
                try:
                    from usage_tracker import get_tracker, UsageRecord
                    get_tracker().record(UsageRecord(
                        provider=self.config.provider if self.config.provider != "auto" else "litellm",
                        model=self.config.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        operation="chat",
                        session_id=getattr(context, "session_id", ""),
                        latency_ms=_latency,
                    ))
                except Exception:
                    pass

                # Check for LLM error
                if response.finish_reason == "error":
                    print(f"[react_agent] LLM Error: {response.content}")
                    state.final_response = response.content or "Desculpe, ocorreu um erro de comunicação."
                    step.status = AgentStatus.ERROR
                    step.error = response.content
                    state.steps.append(step)
                    state.status = AgentStatus.ERROR
                    break

                # Process response
                text_response = response.content or ""
                step.thought = text_response if text_response else None

                # If no tool calls, LLM finished reasoning
                if not response.has_tool_calls:
                    state.final_response = text_response
                    step.status = AgentStatus.DONE
                    state.steps.append(step)
                    state.status = AgentStatus.DONE
                    print(f"[react_agent] Done after {state.iteration + 1} iteration(s)")
                    break

                # Execute tools
                step.status = AgentStatus.ACTING

                # Build assistant message with tool calls (OpenAI format)
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": text_response or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                # Execute each tool and add results
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    tool_input = tool_call.arguments

                    step.tool_name = tool_name
                    step.tool_params = tool_input

                    print(f"[react_agent] Executing: {tool_name}({tool_input})")

                    # Execute via registry
                    result = self.registry.execute(
                        tool_name,
                        tool_input,
                        context,
                    )

                    # Format result for conversation
                    result_text = result.display_text or result.message
                    step.tool_result = result_text

                    # Add tool result in OpenAI format
                    messages.append(format_tool_result_openai(
                        tool_call_id=tool_call.id,
                        tool_name=tool_name,
                        result=result_text,
                    ))

                    if not result.success:
                        print(f"[react_agent] Tool error: {result.error}")

                    # Dynamic tool injection: if load_tool was called,
                    # add the loaded tool to the active set for next iteration
                    if tool_name == "load_tool" and result.success:
                        loaded = result.data.get("loaded_tool")
                        if loaded and loaded not in _loaded_extra_tools:
                            _loaded_extra_tools.add(loaded)
                            active_tools = to_openai_tools(
                                self.registry, tier=1, extra_tools=_loaded_extra_tools
                            )
                            print(f"[react_agent] Dynamically loaded tool: {loaded} "
                                  f"(active: {len(active_tools)})")

                state.steps.append(step)

            except Exception as e:
                print(f"[react_agent] Error: {e}")
                step.status = AgentStatus.ERROR
                step.error = str(e)
                state.steps.append(step)
                state.status = AgentStatus.ERROR
                # Friendly error messages instead of raw exceptions
                err_str = str(e).lower()
                if "rate_limit" in err_str or "rate limit" in err_str or "429" in err_str:
                    state.final_response = "Estou sobrecarregado no momento. Tente novamente em alguns segundos."
                elif "timeout" in err_str or "timed out" in err_str:
                    state.final_response = "A requisição demorou demais. Tente novamente."
                elif "authentication" in err_str or "api_key" in err_str or "401" in err_str:
                    state.final_response = "Erro de configuração do assistente. Contate o administrador."
                else:
                    state.final_response = "Desculpe, ocorreu um erro ao processar. Tente novamente."
                break

        # If max iterations reached without finishing
        if state.status not in (AgentStatus.DONE, AgentStatus.ERROR):
            state.status = AgentStatus.DONE
            if not state.final_response:
                # Use the last text response if available
                for step in reversed(state.steps):
                    if step.thought:
                        state.final_response = step.thought
                        break
                else:
                    state.final_response = "Tarefa concluída."
            print(f"[react_agent] Max iterations ({self.config.max_iterations}) reached")

        print(f"[react_agent] Tokens used: {state.total_input_tokens} in, {state.total_output_tokens} out")

        return state

    def should_use_fast_path(self, message: str) -> bool:
        """
        Check if message should use fast-path (no LLM call).

        Fast-path is used for simple commands that can be handled
        by regex patterns in message_handler.py without Claude.

        Args:
            message: User message

        Returns:
            True if message matches a fast-path pattern
        """
        lower = message.lower().strip()

        # Exact matches
        if lower in self.config.fast_path_patterns:
            return True

        # Prefix matches
        for pattern in self.config.fast_path_patterns:
            if lower.startswith(pattern + " "):
                return True

        return False


# Singleton instance
_react_agent: ReActAgent | None = None


def get_react_agent() -> ReActAgent:
    """Get or create the ReAct agent singleton."""
    global _react_agent
    if _react_agent is None:
        _react_agent = ReActAgent()
    return _react_agent


def reset_react_agent() -> None:
    """Reset the singleton (useful for testing)."""
    global _react_agent
    _react_agent = None
