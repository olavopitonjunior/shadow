"""
ReAct Agent - Agentic loop with Claude API.

Implements the ReAct (Reasoning + Acting) pattern:
Think → Act → Observe → Repeat until done.

Same architecture as OpenClaw/Claude Code for high-quality reasoning.
"""

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

import anthropic

from tools import ToolRegistry, ToolContext, get_tool_registry, setup_default_tools
from tool_adapter import to_claude_tools, format_tool_result
from agent_config import AgentConfig, SYSTEM_PROMPT
from prompt_builder import get_prompt_builder
from sessions import get_session_store

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
    ReAct Agent using Claude API with native tool use.

    Implements the same agentic pattern as OpenClaw:
    - Multi-turn conversation with tool results
    - Automatic iteration until goal is achieved
    - Error handling and recovery

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
    ):
        """
        Initialize the ReAct agent.

        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            registry: Tool registry (uses global registry if not provided)
            config: Agent configuration (uses defaults if not provided)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.registry = registry or get_tool_registry()
        self.config = config or AgentConfig.from_env()

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found. Set it in .env or pass api_key parameter.")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.tools = to_claude_tools(self.registry)

        print(f"[react_agent] Initialized with {self.config.model}")
        print(f"[react_agent] Tools available: {len(self.tools)}")

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

        while state.iteration < self.config.max_iterations:
            step = AgentStep(iteration=state.iteration, status=AgentStatus.THINKING)

            try:
                # Call Claude
                _t0 = time.monotonic()
                response = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system_prompt,
                    tools=self.tools,
                    messages=messages,
                )
                _latency = int((time.monotonic() - _t0) * 1000)

                # Track token usage
                state.total_input_tokens += response.usage.input_tokens
                state.total_output_tokens += response.usage.output_tokens

                # Record API usage for cost tracking
                try:
                    from usage_tracker import get_tracker, UsageRecord
                    get_tracker().record(UsageRecord(
                        provider="anthropic",
                        model=self.config.model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        operation="chat",
                        session_id=getattr(context, "session_id", ""),
                        latency_ms=_latency,
                    ))
                except Exception:
                    pass

                # Process response
                tool_calls = []
                text_response = ""

                for block in response.content:
                    if block.type == "text":
                        text_response += block.text
                        step.thought = block.text
                    elif block.type == "tool_use":
                        tool_calls.append(block)

                # If no tool calls, Claude finished reasoning
                if not tool_calls:
                    state.final_response = text_response
                    step.status = AgentStatus.DONE
                    state.steps.append(step)
                    state.status = AgentStatus.DONE
                    print(f"[react_agent] Done after {state.iteration + 1} iteration(s)")
                    break

                # Execute tools
                step.status = AgentStatus.ACTING
                tool_results = []

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_input = dict(tool_call.input)

                    step.tool_name = tool_name
                    step.tool_params = tool_input

                    print(f"[react_agent] Executing: {tool_name}({tool_input})")

                    # Execute via registry
                    result = self.registry.execute(
                        tool_name,
                        tool_input,
                        context,
                    )

                    # Format result for Claude
                    result_text = result.display_text or result.message
                    step.tool_result = result_text

                    tool_results.append(format_tool_result(
                        tool_use_id=tool_call.id,
                        result=result_text,
                        is_error=not result.success,
                    ))

                    if not result.success:
                        print(f"[react_agent] Tool error: {result.error}")

                # Add assistant response and tool results to conversation
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                state.steps.append(step)

            except anthropic.APIError as e:
                print(f"[react_agent] API Error: {e}")
                step.status = AgentStatus.ERROR
                step.error = str(e)
                state.steps.append(step)
                state.status = AgentStatus.ERROR
                state.final_response = "Desculpe, ocorreu um erro de comunicação. Tente novamente."
                break

            except Exception as e:
                print(f"[react_agent] Error: {e}")
                step.status = AgentStatus.ERROR
                step.error = str(e)
                state.steps.append(step)
                state.status = AgentStatus.ERROR
                state.final_response = f"Desculpe, ocorreu um erro: {str(e)}"
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
