"""
Shadow Agent Plugin System

Provides extensibility for the Shadow agent through plugins.
"""

from .types import PluginDefinition, PluginApi, AgentHookName
from .registry import PluginRegistry
from .loader import load_shadow_plugins
from .hooks import HookRunner

__all__ = [
    "PluginDefinition",
    "PluginApi",
    "AgentHookName",
    "PluginRegistry",
    "load_shadow_plugins",
    "HookRunner",
]
