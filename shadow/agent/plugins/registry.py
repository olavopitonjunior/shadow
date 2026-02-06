"""
Shadow Agent Plugin System - Plugin Registry

Manages plugin registration and provides the Plugin API.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .types import (
    AgentHookName,
    HookRegistration,
    ToolRegistration,
    HandlerRegistration,
    PluginRecord,
)


@dataclass
class PluginRegistry:
    """
    Registry for all loaded plugins and their registrations.
    """
    plugins: list[PluginRecord] = field(default_factory=list)
    hooks: dict[AgentHookName, list[HookRegistration]] = field(default_factory=dict)
    tools: dict[str, ToolRegistration] = field(default_factory=dict)
    intent_handlers: dict[str, HandlerRegistration] = field(default_factory=dict)

    def get_hooks(self, hook_name: AgentHookName) -> list[HookRegistration]:
        """Get all hooks for a given hook name, sorted by priority (higher first)."""
        hooks = self.hooks.get(hook_name, [])
        return sorted(hooks, key=lambda h: -h.priority)

    def get_tool(self, name: str) -> ToolRegistration | None:
        """Get a registered tool by name."""
        return self.tools.get(name)

    def get_handler(self, intent: str) -> HandlerRegistration | None:
        """Get a registered intent handler."""
        return self.intent_handlers.get(intent)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the registry."""
        hook_count = sum(len(hooks) for hooks in self.hooks.values())
        return {
            "plugin_count": len(self.plugins),
            "hook_count": hook_count,
            "tool_count": len(self.tools),
            "handler_count": len(self.intent_handlers),
            "plugins": [
                {
                    "id": p.id,
                    "hooks": p.hook_names,
                    "tools": p.tool_names,
                    "handlers": p.handler_intents,
                }
                for p in self.plugins
            ],
        }


class PluginApiImpl:
    """
    Implementation of the Plugin API.

    Provides methods for plugins to register hooks, handlers, and tools.
    """

    def __init__(
        self,
        record: PluginRecord,
        registry: PluginRegistry,
        config: dict,
        plugin_config: dict,
        logger: logging.Logger,
        plugins_dir: Path,
    ):
        self._record = record
        self._registry = registry
        self._config = config
        self._plugin_config = plugin_config
        self._logger = logger.getChild(record.id)
        self._plugins_dir = plugins_dir

    @property
    def id(self) -> str:
        return self._record.id

    @property
    def name(self) -> str:
        return self._record.name

    @property
    def config(self) -> dict:
        return self._config

    @property
    def plugin_config(self) -> dict:
        return self._plugin_config

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def register_handler(self, intent: str, handler: Callable) -> None:
        """Register a handler for a specific intent."""
        if intent in self._registry.intent_handlers:
            self._logger.warning(
                f"Intent handler for '{intent}' already registered, overwriting"
            )

        registration = HandlerRegistration(
            plugin_id=self._record.id,
            intent=intent,
            handler=handler,
        )
        self._registry.intent_handlers[intent] = registration

        if intent not in self._record.handler_intents:
            self._record.handler_intents.append(intent)

        self._logger.debug(f"Registered handler for intent: {intent}")

    def register_tool(
        self,
        name: str,
        handler: Callable,
        schema: dict | None = None,
    ) -> None:
        """Register a custom tool."""
        if name in self._registry.tools:
            self._logger.warning(
                f"Tool '{name}' already registered, overwriting"
            )

        registration = ToolRegistration(
            plugin_id=self._record.id,
            name=name,
            handler=handler,
            schema=schema or {},
        )
        self._registry.tools[name] = registration

        if name not in self._record.tool_names:
            self._record.tool_names.append(name)

        self._logger.debug(f"Registered tool: {name}")

    def on(
        self,
        hook_name: AgentHookName | str,
        handler: Callable,
        priority: int = 0,
    ) -> None:
        """Register a hook handler."""
        # Convert string to enum if needed
        if isinstance(hook_name, str):
            try:
                hook_name = AgentHookName(hook_name)
            except ValueError:
                self._logger.warning(f"Unknown hook name: {hook_name}")
                return

        registration = HookRegistration(
            plugin_id=self._record.id,
            hook_name=hook_name,
            handler=handler,
            priority=priority,
        )

        if hook_name not in self._registry.hooks:
            self._registry.hooks[hook_name] = []
        self._registry.hooks[hook_name].append(registration)

        hook_str = hook_name.value if isinstance(hook_name, AgentHookName) else hook_name
        if hook_str not in self._record.hook_names:
            self._record.hook_names.append(hook_str)

        self._logger.debug(f"Registered hook: {hook_name} (priority={priority})")

    def resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the plugins directory."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self._plugins_dir / path


def create_plugin_api(
    record: PluginRecord,
    registry: PluginRegistry,
    config: dict,
    plugin_config: dict,
    logger: logging.Logger,
    plugins_dir: Path,
) -> PluginApiImpl:
    """Create a Plugin API instance for a plugin."""
    return PluginApiImpl(
        record=record,
        registry=registry,
        config=config,
        plugin_config=plugin_config,
        logger=logger,
        plugins_dir=plugins_dir,
    )


def create_plugin_record(definition: Any, source: str) -> PluginRecord:
    """Create a plugin record from a plugin definition."""
    return PluginRecord(
        id=definition.id,
        name=definition.name or definition.id,
        version=getattr(definition, "version", None),
        source=source,
        enabled=True,
        status="loaded",
        hook_names=[],
        tool_names=[],
        handler_intents=[],
    )
