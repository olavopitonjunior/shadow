/**
 * Message Logger Plugin
 *
 * Logs all messages received and sent through the gateway.
 * This is an example plugin demonstrating the Shadow plugin system.
 */

export default {
  id: "message-logger",
  name: "Message Logger",
  version: "1.0.0",
  description: "Logs all messages received and sent through the gateway",

  /**
   * @param {import('../../src/plugins/types.js').ShadowPluginApi} api
   */
  register(api) {
    const logger = api.logger;

    // Log when gateway starts
    api.on("gateway_start", async (event, ctx) => {
      logger.info({ port: event.port }, "Gateway started - Message Logger active");
    });

    // Log incoming messages
    api.on("message_received", async (event, ctx) => {
      logger.info(
        {
          messageId: event.messageId,
          chatId: event.chatId,
          chatType: event.chatType,
          sender: event.senderE164,
          senderName: event.senderName,
          contentPreview: event.content.slice(0, 100),
          isOwner: event.isOwner,
        },
        "Message received"
      );
    });

    // Log outgoing messages (can modify if needed)
    api.on("message_sending", async (event, ctx) => {
      logger.info(
        {
          to: event.to,
          contentPreview: event.content.slice(0, 100),
        },
        "Sending message"
      );

      // Return undefined to not modify the message
      // To modify: return { content: "modified content" }
      // To cancel: return { cancel: true }
      return undefined;
    });

    // Log sent messages
    api.on("message_sent", async (event, ctx) => {
      logger.info(
        {
          to: event.to,
          messageId: event.messageId,
          success: event.success,
        },
        "Message sent"
      );
    });

    // Log when gateway stops
    api.on("gateway_stop", async (event, ctx) => {
      logger.info({ reason: event.reason }, "Gateway stopping - Message Logger cleanup");
    });

    logger.info("Message Logger plugin registered");
  },
};
