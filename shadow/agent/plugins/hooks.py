"""
Shadow Agent Plugin System - Hook Runner

Provides utilities for executing plugin lifecycle hooks.
"""

import asyncio
import logging
from typing import Any

from .types import AgentHookName
from .registry import PluginRegistry


class HookRunner:
    """
    Executes plugin hooks with proper error handling and priority ordering.
    """

    def __init__(
        self,
        registry: PluginRegistry,
        logger: logging.Logger | None = None,
        catch_errors: bool = True,
    ):
        self._registry = registry
        self._logger = logger or logging.getLogger(__name__)
        self._catch_errors = catch_errors

    async def _run_void_hook(
        self,
        hook_name: AgentHookName,
        *args,
        **kwargs,
    ) -> None:
        """
        Run a hook that doesn't return a value (fire-and-forget).
        All handlers are executed in parallel.
        """
        hooks = self._registry.get_hooks(hook_name)
        if not hooks:
            return

        self._logger.debug(f"Running void hook: {hook_name.value} ({len(hooks)} handlers)")

        async def run_handler(hook):
            try:
                result = hook.handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as err:
                msg = f"Hook {hook_name.value} handler from {hook.plugin_id} failed: {err}"
                if self._catch_errors:
                    self._logger.error(msg)
                else:
                    raise RuntimeError(msg) from err

        await asyncio.gather(
            *[run_handler(hook) for hook in hooks],
            return_exceptions=self._catch_errors,
        )

    async def _run_modifying_hook(
        self,
        hook_name: AgentHookName,
        *args,
        **kwargs,
    ) -> Any:
        """
        Run a hook that can return a modifying result.
        Handlers are executed sequentially in priority order.
        """
        hooks = self._registry.get_hooks(hook_name)
        if not hooks:
            return None

        self._logger.debug(
            f"Running modifying hook: {hook_name.value} ({len(hooks)} handlers)"
        )

        result = None

        for hook in hooks:
            try:
                handler_result = hook.handler(*args, **kwargs)
                if asyncio.iscoroutine(handler_result):
                    handler_result = await handler_result

                if handler_result is not None:
                    result = handler_result
            except Exception as err:
                msg = f"Hook {hook_name.value} handler from {hook.plugin_id} failed: {err}"
                if self._catch_errors:
                    self._logger.error(msg)
                else:
                    raise RuntimeError(msg) from err

        return result

    # =========================================================================
    # Message Processing Hooks
    # =========================================================================

    async def run_before_handle(self, payload: dict) -> dict | None:
        """
        Run before_handle hook.
        Allows plugins to intercept or modify the incoming payload.
        Returns early response if a plugin provides one.
        Runs sequentially.
        """
        return await self._run_modifying_hook(
            AgentHookName.BEFORE_HANDLE,
            payload,
        )

    async def run_after_handle(self, payload: dict, result: dict) -> None:
        """
        Run after_handle hook.
        Allows plugins to analyze completed processing.
        Runs in parallel (fire-and-forget).
        """
        await self._run_void_hook(
            AgentHookName.AFTER_HANDLE,
            payload,
            result,
        )

    # =========================================================================
    # Tool Hooks
    # =========================================================================

    async def run_tool_call(self, tool_name: str, params: dict) -> dict | None:
        """
        Run tool_call hook.
        Allows plugins to intercept or modify tool calls.
        Runs sequentially.
        """
        return await self._run_modifying_hook(
            AgentHookName.TOOL_CALL,
            tool_name,
            params,
        )

    # =========================================================================
    # Storage Hooks
    # =========================================================================

    async def run_storage_write(self, operation: str, data: dict) -> None:
        """
        Run storage_write hook.
        Allows plugins to react to storage operations.
        Runs in parallel (fire-and-forget).
        """
        await self._run_void_hook(
            AgentHookName.STORAGE_WRITE,
            operation,
            data,
        )

    # =========================================================================
    # Utility
    # =========================================================================

    def has_hooks(self, hook_name: AgentHookName) -> bool:
        """Check if any hooks are registered for a given hook name."""
        hooks = self._registry.hooks.get(hook_name, [])
        return len(hooks) > 0

    def get_hook_count(self, hook_name: AgentHookName) -> int:
        """Get count of registered hooks for a given hook name."""
        hooks = self._registry.hooks.get(hook_name, [])
        return len(hooks)


def create_hook_runner(
    registry: PluginRegistry,
    logger: logging.Logger | None = None,
    catch_errors: bool = True,
) -> HookRunner:
    """Create a hook runner for the given registry."""
    return HookRunner(
        registry=registry,
        logger=logger,
        catch_errors=catch_errors,
    )
