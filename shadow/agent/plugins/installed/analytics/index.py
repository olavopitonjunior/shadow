"""
Analytics Plugin

Logs analytics about message processing.
This is an example plugin demonstrating the Shadow agent plugin system.
"""

from datetime import datetime
from plugins.types import PluginDefinition, AgentHookName


# Plugin statistics
stats = {
    "messages_processed": 0,
    "intents_detected": {},
    "start_time": None,
}


def register(api):
    """Register the analytics plugin."""
    logger = api.logger
    stats["start_time"] = datetime.utcnow().isoformat()

    # Hook: before_handle - count messages
    async def before_handle(payload):
        stats["messages_processed"] += 1
        logger.debug(
            f"Processing message #{stats['messages_processed']} "
            f"from {payload.get('sender_e164', 'unknown')}"
        )
        # Return None to continue normal processing
        return None

    # Hook: after_handle - track intents
    async def after_handle(payload, result):
        intent = result.get("intent", "unknown")
        stats["intents_detected"][intent] = stats["intents_detected"].get(intent, 0) + 1

        logger.info(
            f"Message processed: intent={intent}, "
            f"total={stats['messages_processed']}, "
            f"intent_count={stats['intents_detected'][intent]}"
        )

    # Register hooks
    api.on(AgentHookName.BEFORE_HANDLE, before_handle)
    api.on(AgentHookName.AFTER_HANDLE, after_handle)

    # Register a custom tool
    async def get_stats(params):
        """Get current analytics statistics."""
        return {
            "messages_processed": stats["messages_processed"],
            "intents_detected": stats["intents_detected"],
            "uptime_since": stats["start_time"],
        }

    api.register_tool(
        "analytics_stats",
        get_stats,
        schema={
            "type": "object",
            "properties": {},
            "description": "Get current analytics statistics",
        },
    )

    logger.info("Analytics plugin registered")


# Plugin definition
plugin = PluginDefinition(
    id="analytics",
    name="Analytics",
    version="1.0.0",
    description="Logs analytics about message processing",
    register=register,
)
