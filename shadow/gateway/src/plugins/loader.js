/**
 * Shadow Gateway Plugin System - Plugin Loader
 *
 * Discovers and loads plugins from the plugins directory.
 */

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createPluginRegistry, createPluginApi, createPluginRecord, getRegistrySummary } from "./registry.js";

/**
 * Discover plugin candidates in a directory.
 * @param {string} pluginsDir - Directory to search for plugins
 * @returns {Array<{ path: string, type: 'file' | 'directory' }>}
 */
function discoverPlugins(pluginsDir) {
  const candidates = [];

  if (!fs.existsSync(pluginsDir)) {
    return candidates;
  }

  const entries = fs.readdirSync(pluginsDir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(pluginsDir, entry.name);

    if (entry.isFile() && (entry.name.endsWith(".js") || entry.name.endsWith(".mjs"))) {
      // Direct .js file in plugins directory
      candidates.push({ path: fullPath, type: "file" });
    } else if (entry.isDirectory()) {
      // Directory - look for index.js or package.json
      const indexPath = path.join(fullPath, "index.js");
      const packagePath = path.join(fullPath, "package.json");

      if (fs.existsSync(indexPath)) {
        candidates.push({ path: indexPath, type: "directory" });
      } else if (fs.existsSync(packagePath)) {
        try {
          const pkg = JSON.parse(fs.readFileSync(packagePath, "utf-8"));
          const main = pkg.main || "index.js";
          const mainPath = path.join(fullPath, main);
          if (fs.existsSync(mainPath)) {
            candidates.push({ path: mainPath, type: "directory" });
          }
        } catch {
          // Ignore invalid package.json
        }
      }
    }
  }

  return candidates;
}

/**
 * Load a plugin module.
 * @param {string} pluginPath - Path to plugin entry file
 * @returns {Promise<import('./types.js').ShadowPluginDefinition | null>}
 */
async function loadPluginModule(pluginPath) {
  try {
    const moduleUrl = pathToFileURL(pluginPath).href;
    const module = await import(moduleUrl);

    // Support both default export and named export
    const definition = module.default ?? module;

    // Validate plugin definition
    if (!definition || typeof definition !== "object") {
      return null;
    }

    // Must have id and register function
    if (!definition.id || typeof definition.id !== "string") {
      return null;
    }

    if (typeof definition.register !== "function") {
      return null;
    }

    return definition;
  } catch {
    return null;
  }
}

/**
 * Load plugin configuration.
 * @param {string} configPath - Path to plugins config file
 * @returns {{ enabled?: string[], disabled?: string[], config?: Record<string, any> }}
 */
function loadPluginsConfig(configPath) {
  if (!fs.existsSync(configPath)) {
    return {};
  }

  try {
    const content = fs.readFileSync(configPath, "utf-8");
    const parsed = JSON.parse(content);
    return parsed.plugins ?? {};
  } catch {
    return {};
  }
}

/**
 * Check if a plugin is enabled based on configuration.
 * @param {string} pluginId
 * @param {{ enabled?: string[], disabled?: string[] }} pluginsConfig
 * @returns {boolean}
 */
function isPluginEnabled(pluginId, pluginsConfig) {
  // If there's an enabled list, only those plugins are enabled
  if (pluginsConfig.enabled && pluginsConfig.enabled.length > 0) {
    return pluginsConfig.enabled.includes(pluginId);
  }

  // If there's a disabled list, check if plugin is in it
  if (pluginsConfig.disabled && pluginsConfig.disabled.length > 0) {
    return !pluginsConfig.disabled.includes(pluginId);
  }

  // Default: enabled
  return true;
}

/**
 * Load all plugins from the plugins directory.
 * @param {Object} options
 * @param {Object} options.config - Gateway configuration
 * @param {import('pino').Logger} options.logger - Logger instance
 * @param {string} [options.pluginsDir] - Plugins directory path
 * @param {string} [options.configPath] - Path to plugins config file
 * @returns {Promise<import('./types.js').PluginRegistry>}
 */
export async function loadShadowPlugins(options) {
  const {
    config,
    logger,
    pluginsDir = path.join(process.cwd(), "plugins"),
    configPath = path.join(process.cwd(), "shadow.plugins.json"),
  } = options;

  const registry = createPluginRegistry();
  const pluginsConfig = loadPluginsConfig(configPath);

  logger.info({ pluginsDir }, "Loading plugins");

  const candidates = discoverPlugins(pluginsDir);

  if (candidates.length === 0) {
    logger.info("No plugins found");
    return registry;
  }

  logger.info({ count: candidates.length }, "Found plugin candidates");

  for (const candidate of candidates) {
    const definition = await loadPluginModule(candidate.path);

    if (!definition) {
      logger.warn({ path: candidate.path }, "Failed to load plugin - invalid definition");
      continue;
    }

    // Check if plugin is enabled
    if (!isPluginEnabled(definition.id, pluginsConfig)) {
      logger.info({ pluginId: definition.id }, "Plugin disabled by configuration");
      continue;
    }

    // Create plugin record
    const record = createPluginRecord(definition, candidate.path);

    // Get plugin-specific config
    const pluginConfig = pluginsConfig.config?.[definition.id] ?? {};

    // Create plugin API
    const api = createPluginApi({
      record,
      registry,
      config,
      pluginConfig,
      logger,
      pluginsDir,
    });

    // Call register function
    try {
      await definition.register(api);
      registry.plugins.push(record);
      logger.info(
        { pluginId: definition.id, hooks: record.hookNames },
        "Plugin loaded successfully"
      );
    } catch (err) {
      record.status = "error";
      logger.error(
        { pluginId: definition.id, err: String(err) },
        "Plugin registration failed"
      );
    }
  }

  const summary = getRegistrySummary(registry);
  logger.info(
    { pluginCount: summary.pluginCount, hookCount: summary.hookCount },
    "Plugins loaded"
  );

  return registry;
}

/**
 * Create an empty registry (for when plugins are disabled).
 * @returns {import('./types.js').PluginRegistry}
 */
export function createEmptyRegistry() {
  return createPluginRegistry();
}
