"""
Shadow Agent Plugin System - Plugin Loader

Discovers and loads plugins from the plugins directory.
"""

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .types import PluginDefinition
from .registry import (
    PluginRegistry,
    create_plugin_api,
    create_plugin_record,
)


def discover_plugins(plugins_dir: Path) -> list[dict[str, Any]]:
    """
    Discover plugin candidates in a directory.

    Returns a list of dicts with:
    - path: Path to the plugin entry file
    - type: 'file' or 'directory'
    """
    candidates = []

    if not plugins_dir.exists():
        return candidates

    for entry in plugins_dir.iterdir():
        if entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
            # Direct .py file
            candidates.append({"path": entry, "type": "file"})
        elif entry.is_dir() and not entry.name.startswith("_"):
            # Directory - look for __init__.py or index.py
            init_path = entry / "__init__.py"
            index_path = entry / "index.py"

            if index_path.exists():
                candidates.append({"path": index_path, "type": "directory"})
            elif init_path.exists():
                candidates.append({"path": init_path, "type": "directory"})

    return candidates


def load_plugin_module(plugin_path: Path) -> Any:
    """
    Load a plugin module from a file path.

    Returns the module or None if loading fails.
    """
    try:
        # Create a unique module name
        module_name = f"shadow_plugin_{plugin_path.stem}_{id(plugin_path)}"

        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return module
    except Exception:
        return None


def extract_definition(module: Any) -> PluginDefinition | None:
    """
    Extract plugin definition from a module.

    Supports:
    - module.plugin: PluginDefinition object
    - module.PLUGIN: PluginDefinition object
    - module with id and register attributes directly
    """
    # Check for explicit plugin object
    definition = getattr(module, "plugin", None) or getattr(module, "PLUGIN", None)

    if definition is not None:
        if hasattr(definition, "id") and hasattr(definition, "register"):
            return definition
        return None

    # Check if module itself is a plugin definition
    if hasattr(module, "id") and hasattr(module, "register"):
        return module

    # Check for register function and derive id from module name
    if hasattr(module, "register") and callable(module.register):
        plugin_id = getattr(module, "id", None) or getattr(module, "ID", None)
        if plugin_id:
            return PluginDefinition(
                id=plugin_id,
                name=getattr(module, "name", None) or getattr(module, "NAME", None),
                version=getattr(module, "version", None) or getattr(module, "VERSION", None),
                description=getattr(module, "description", None),
                register=module.register,
            )

    return None


def load_plugins_config(config_path: Path) -> dict[str, Any]:
    """Load plugin configuration from JSON file."""
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("plugins", {})
    except Exception:
        return {}


def is_plugin_enabled(plugin_id: str, plugins_config: dict[str, Any]) -> bool:
    """Check if a plugin is enabled based on configuration."""
    enabled_list = plugins_config.get("enabled", [])
    disabled_list = plugins_config.get("disabled", [])

    # If there's an enabled list, only those plugins are enabled
    if enabled_list:
        return plugin_id in enabled_list

    # If there's a disabled list, check if plugin is in it
    if disabled_list:
        return plugin_id not in disabled_list

    # Default: enabled
    return True


def load_shadow_plugins(
    config: dict,
    logger: logging.Logger,
    plugins_dir: Path | str | None = None,
    config_path: Path | str | None = None,
) -> PluginRegistry:
    """
    Load all plugins from the plugins directory.

    Args:
        config: Agent configuration dict
        logger: Logger instance
        plugins_dir: Path to plugins directory (default: ./plugins/installed)
        config_path: Path to plugins config file (default: ./shadow.plugins.json)

    Returns:
        PluginRegistry with loaded plugins
    """
    if plugins_dir is None:
        plugins_dir = Path(__file__).parent / "installed"
    else:
        plugins_dir = Path(plugins_dir)

    if config_path is None:
        config_path = Path(__file__).parent.parent / "shadow.plugins.json"
    else:
        config_path = Path(config_path)

    registry = PluginRegistry()
    plugins_config = load_plugins_config(config_path)

    logger.info(f"Loading plugins from: {plugins_dir}")

    candidates = discover_plugins(plugins_dir)

    if not candidates:
        logger.info("No plugins found")
        return registry

    logger.info(f"Found {len(candidates)} plugin candidate(s)")

    for candidate in candidates:
        plugin_path = candidate["path"]

        module = load_plugin_module(plugin_path)
        if module is None:
            logger.warning(f"Failed to load plugin module: {plugin_path}")
            continue

        definition = extract_definition(module)
        if definition is None:
            logger.warning(f"Invalid plugin definition: {plugin_path}")
            continue

        # Check if plugin is enabled
        if not is_plugin_enabled(definition.id, plugins_config):
            logger.info(f"Plugin disabled by configuration: {definition.id}")
            continue

        # Create plugin record
        record = create_plugin_record(definition, str(plugin_path))

        # Get plugin-specific config
        plugin_config = plugins_config.get("config", {}).get(definition.id, {})

        # Create plugin API
        api = create_plugin_api(
            record=record,
            registry=registry,
            config=config,
            plugin_config=plugin_config,
            logger=logger,
            plugins_dir=plugins_dir,
        )

        # Call register function
        try:
            if definition.register:
                definition.register(api)
            registry.plugins.append(record)
            logger.info(
                f"Plugin loaded: {definition.id} "
                f"(hooks={record.hook_names}, tools={record.tool_names})"
            )
        except Exception as err:
            record.status = "error"
            logger.error(f"Plugin registration failed: {definition.id} - {err}")

    summary = registry.get_summary()
    logger.info(
        f"Plugins loaded: {summary['plugin_count']} plugins, "
        f"{summary['hook_count']} hooks, {summary['tool_count']} tools"
    )

    return registry
