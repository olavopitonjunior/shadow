/**
 * Shadow Gateway Plugin System - Type Definitions
 *
 * Uses JSDoc for type definitions to maintain JavaScript simplicity
 * while providing IDE support.
 */

/**
 * @typedef {'message_received' | 'message_sending' | 'message_sent' | 'gateway_start' | 'gateway_stop'} GatewayHookName
 */

/**
 * @typedef {Object} ShadowPluginDefinition
 * @property {string} id - Unique plugin identifier
 * @property {string} [name] - Display name
 * @property {string} [version] - Plugin version
 * @property {string} [description] - Plugin description
 * @property {(api: ShadowPluginApi) => void | Promise<void>} register - Registration function
 */

/**
 * @typedef {Object} ShadowPluginApi
 * @property {string} id - Plugin ID
 * @property {string} name - Plugin name
 * @property {Object} config - Gateway configuration
 * @property {Object} pluginConfig - Plugin-specific configuration
 * @property {import('pino').Logger} logger - Pino logger child
 * @property {(hookName: GatewayHookName, handler: Function, opts?: {priority?: number}) => void} on - Register a hook
 * @property {(path: string) => string} resolvePath - Resolve path relative to plugins directory
 */

/**
 * @typedef {Object} HookRegistration
 * @property {string} pluginId - Plugin that registered this hook
 * @property {GatewayHookName} hookName - Name of the hook
 * @property {Function} handler - Hook handler function
 * @property {number} [priority] - Priority (higher = runs first)
 */

/**
 * @typedef {Object} PluginRecord
 * @property {string} id - Plugin ID
 * @property {string} name - Plugin name
 * @property {string} [version] - Plugin version
 * @property {string} source - Path to plugin source
 * @property {boolean} enabled - Whether plugin is enabled
 * @property {'loaded' | 'disabled' | 'error'} status - Load status
 * @property {string[]} hookNames - Registered hook names
 */

/**
 * @typedef {Object} PluginRegistry
 * @property {PluginRecord[]} plugins - Loaded plugins
 * @property {Map<GatewayHookName, HookRegistration[]>} hooks - Registered hooks by name
 */

/**
 * Message received event - fired when a message is received
 * @typedef {Object} MessageReceivedEvent
 * @property {string} messageId - Message ID
 * @property {string} chatId - Chat JID
 * @property {string} chatType - 'direct' or 'group'
 * @property {string} senderE164 - Sender phone number (E.164)
 * @property {string} senderName - Sender push name
 * @property {string} content - Message text content
 * @property {number} timestamp - Message timestamp
 * @property {boolean} isOwner - Whether sender is owner
 */

/**
 * Message sending event - fired before sending a message
 * @typedef {Object} MessageSendingEvent
 * @property {string} to - Recipient JID
 * @property {string} content - Message content
 * @property {string} [replyTo] - Message ID being replied to
 */

/**
 * Message sending result - returned by message_sending hooks
 * @typedef {Object} MessageSendingResult
 * @property {string} [content] - Modified content
 * @property {boolean} [cancel] - Whether to cancel sending
 */

/**
 * Message sent event - fired after a message is sent
 * @typedef {Object} MessageSentEvent
 * @property {string} to - Recipient JID
 * @property {string} content - Message content
 * @property {string} [messageId] - Sent message ID
 * @property {boolean} success - Whether send succeeded
 */

/**
 * Gateway start event
 * @typedef {Object} GatewayStartEvent
 * @property {number} port - HTTP port
 * @property {string} [phoneNumber] - Connected phone number
 */

/**
 * Gateway stop event
 * @typedef {Object} GatewayStopEvent
 * @property {string} reason - Stop reason
 */

/**
 * Hook context - passed to all hooks
 * @typedef {Object} HookContext
 * @property {string} chatId - Chat JID (for message hooks)
 * @property {import('pino').Logger} logger - Logger instance
 */

export const HOOK_NAMES = /** @type {const} */ ([
  "message_received",
  "message_sending",
  "message_sent",
  "gateway_start",
  "gateway_stop",
]);

export const VOID_HOOKS = /** @type {const} */ ([
  "message_received",
  "message_sent",
  "gateway_start",
  "gateway_stop",
]);

export const MODIFYING_HOOKS = /** @type {const} */ (["message_sending"]);
