/**
 * Shadow Gateway Plugin System - Plugin Registry
 *
 * Manages plugin registration and provides the Plugin API for plugins to use.
 */

import path from "node:path";
import { HOOK_NAMES } from "./types.js";

/**
 * Create an empty plugin registry.
 * @returns {import('./types.js').PluginRegistry}
 */
export function createPluginRegistry() {
  return {
    plugins: [],
    hooks: new Map(),
  };
}

/**
 * Create the plugin API for a specific plugin.
 * @param {Object} params
 * @param {import('./types.js').PluginRecord} params.record - Plugin record
 * @param {import('./types.js').PluginRegistry} params.registry - Plugin registry
 * @param {Object} params.config - Gateway configuration
 * @param {Object} [params.pluginConfig] - Plugin-specific configuration
 * @param {import('pino').Logger} params.logger - Base logger
 * @param {string} params.pluginsDir - Plugins directory path
 * @returns {import('./types.js').ShadowPluginApi}
 */
export function createPluginApi({ record, registry, config, pluginConfig, logger, pluginsDir }) {
  const pluginLogger = logger.child({ plugin: record.id });

  /**
   * Register a hook handler.
   * @param {import('./types.js').GatewayHookName} hookName
   * @param {Function} handler
   * @param {{ priority?: number }} [opts]
   */
  function on(hookName, handler, opts = {}) {
    if (!HOOK_NAMES.includes(hookName)) {
      pluginLogger.warn({ hookName }, `Unknown hook name: ${hookName}`);
      return;
    }

    /** @type {import('./types.js').HookRegistration} */
    const registration = {
      pluginId: record.id,
      hookName,
      handler,
      priority: opts.priority ?? 0,
    };

    if (!registry.hooks.has(hookName)) {
      registry.hooks.set(hookName, []);
    }
    registry.hooks.get(hookName).push(registration);

    // Track hook names on the plugin record
    if (!record.hookNames.includes(hookName)) {
      record.hookNames.push(hookName);
    }

    pluginLogger.debug({ hookName, priority: registration.priority }, "Hook registered");
  }

  /**
   * Resolve a path relative to the plugins directory.
   * @param {string} inputPath
   * @returns {string}
   */
  function resolvePath(inputPath) {
    if (path.isAbsolute(inputPath)) {
      return inputPath;
    }
    return path.resolve(pluginsDir, inputPath);
  }

  return {
    id: record.id,
    name: record.name,
    config,
    pluginConfig: pluginConfig ?? {},
    logger: pluginLogger,
    on,
    resolvePath,
  };
}

/**
 * Create a plugin record from a plugin definition.
 * @param {import('./types.js').ShadowPluginDefinition} definition
 * @param {string} source - Path to plugin source
 * @returns {import('./types.js').PluginRecord}
 */
export function createPluginRecord(definition, source) {
  return {
    id: definition.id,
    name: definition.name ?? definition.id,
    version: definition.version,
    source,
    enabled: true,
    status: "loaded",
    hookNames: [],
  };
}

/**
 * Get a summary of registered plugins and hooks.
 * @param {import('./types.js').PluginRegistry} registry
 * @returns {{ pluginCount: number, hookCount: number, plugins: Array<{ id: string, hooks: string[] }> }}
 */
export function getRegistrySummary(registry) {
  let hookCount = 0;
  for (const hooks of registry.hooks.values()) {
    hookCount += hooks.length;
  }

  return {
    pluginCount: registry.plugins.length,
    hookCount,
    plugins: registry.plugins.map((p) => ({
      id: p.id,
      hooks: p.hookNames,
    })),
  };
}
