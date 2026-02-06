/**
 * Shadow Gateway Plugin System - Hook Runner
 *
 * Provides utilities for executing plugin lifecycle hooks with proper
 * error handling, priority ordering, and async support.
 *
 * Inspired by Moltbot's hook system but simplified for Shadow MVP.
 */

import { VOID_HOOKS, MODIFYING_HOOKS } from "./types.js";

/**
 * Get hooks for a specific hook name, sorted by priority (higher first).
 * @param {import('./types.js').PluginRegistry} registry
 * @param {import('./types.js').GatewayHookName} hookName
 * @returns {import('./types.js').HookRegistration[]}
 */
function getHooksForName(registry, hookName) {
  const hooks = registry.hooks.get(hookName) || [];
  return [...hooks].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
}

/**
 * Create a hook runner for a specific registry.
 * @param {import('./types.js').PluginRegistry} registry
 * @param {{ logger?: import('pino').Logger, catchErrors?: boolean }} options
 */
export function createHookRunner(registry, options = {}) {
  const logger = options.logger;
  const catchErrors = options.catchErrors ?? true;

  /**
   * Run a hook that doesn't return a value (fire-and-forget style).
   * All handlers are executed in parallel for performance.
   * @param {import('./types.js').GatewayHookName} hookName
   * @param {Object} event
   * @param {import('./types.js').HookContext} ctx
   */
  async function runVoidHook(hookName, event, ctx) {
    const hooks = getHooksForName(registry, hookName);
    if (hooks.length === 0) return;

    logger?.debug({ hookName, count: hooks.length }, "running void hook");

    const promises = hooks.map(async (hook) => {
      try {
        await hook.handler(event, ctx);
      } catch (err) {
        const msg = `[hooks] ${hookName} handler from ${hook.pluginId} failed: ${String(err)}`;
        if (catchErrors) {
          logger?.error({ err, pluginId: hook.pluginId, hookName }, msg);
        } else {
          throw new Error(msg);
        }
      }
    });

    await Promise.all(promises);
  }

  /**
   * Run a hook that can return a modifying result.
   * Handlers are executed sequentially in priority order, and results are merged.
   * @param {import('./types.js').GatewayHookName} hookName
   * @param {Object} event
   * @param {import('./types.js').HookContext} ctx
   * @param {(accumulated: any, next: any) => any} [mergeResults]
   * @returns {Promise<any>}
   */
  async function runModifyingHook(hookName, event, ctx, mergeResults) {
    const hooks = getHooksForName(registry, hookName);
    if (hooks.length === 0) return undefined;

    logger?.debug({ hookName, count: hooks.length }, "running modifying hook");

    let result;

    for (const hook of hooks) {
      try {
        const handlerResult = await hook.handler(event, ctx);

        if (handlerResult !== undefined && handlerResult !== null) {
          if (mergeResults && result !== undefined) {
            result = mergeResults(result, handlerResult);
          } else {
            result = handlerResult;
          }
        }
      } catch (err) {
        const msg = `[hooks] ${hookName} handler from ${hook.pluginId} failed: ${String(err)}`;
        if (catchErrors) {
          logger?.error({ err, pluginId: hook.pluginId, hookName }, msg);
        } else {
          throw new Error(msg);
        }
      }
    }

    return result;
  }

  // =========================================================================
  // Message Hooks
  // =========================================================================

  /**
   * Run message_received hook.
   * Runs in parallel (fire-and-forget).
   * @param {import('./types.js').MessageReceivedEvent} event
   * @param {import('./types.js').HookContext} ctx
   */
  async function runMessageReceived(event, ctx) {
    return runVoidHook("message_received", event, ctx);
  }

  /**
   * Run message_sending hook.
   * Allows plugins to modify or cancel outgoing messages.
   * Runs sequentially.
   * @param {import('./types.js').MessageSendingEvent} event
   * @param {import('./types.js').HookContext} ctx
   * @returns {Promise<import('./types.js').MessageSendingResult | undefined>}
   */
  async function runMessageSending(event, ctx) {
    return runModifyingHook("message_sending", event, ctx, (acc, next) => ({
      content: next.content ?? acc?.content,
      cancel: next.cancel ?? acc?.cancel,
    }));
  }

  /**
   * Run message_sent hook.
   * Runs in parallel (fire-and-forget).
   * @param {import('./types.js').MessageSentEvent} event
   * @param {import('./types.js').HookContext} ctx
   */
  async function runMessageSent(event, ctx) {
    return runVoidHook("message_sent", event, ctx);
  }

  // =========================================================================
  // Gateway Hooks
  // =========================================================================

  /**
   * Run gateway_start hook.
   * Runs in parallel (fire-and-forget).
   * @param {import('./types.js').GatewayStartEvent} event
   * @param {import('./types.js').HookContext} ctx
   */
  async function runGatewayStart(event, ctx) {
    return runVoidHook("gateway_start", event, ctx);
  }

  /**
   * Run gateway_stop hook.
   * Runs in parallel (fire-and-forget).
   * @param {import('./types.js').GatewayStopEvent} event
   * @param {import('./types.js').HookContext} ctx
   */
  async function runGatewayStop(event, ctx) {
    return runVoidHook("gateway_stop", event, ctx);
  }

  // =========================================================================
  // Utility
  // =========================================================================

  /**
   * Check if any hooks are registered for a given hook name.
   * @param {import('./types.js').GatewayHookName} hookName
   * @returns {boolean}
   */
  function hasHooks(hookName) {
    const hooks = registry.hooks.get(hookName);
    return hooks ? hooks.length > 0 : false;
  }

  /**
   * Get count of registered hooks for a given hook name.
   * @param {import('./types.js').GatewayHookName} hookName
   * @returns {number}
   */
  function getHookCount(hookName) {
    const hooks = registry.hooks.get(hookName);
    return hooks ? hooks.length : 0;
  }

  return {
    // Message hooks
    runMessageReceived,
    runMessageSending,
    runMessageSent,
    // Gateway hooks
    runGatewayStart,
    runGatewayStop,
    // Utility
    hasHooks,
    getHookCount,
  };
}
