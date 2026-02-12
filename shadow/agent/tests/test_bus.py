"""
Tests for the MessageBus system.
"""

import time
import threading
import pytest


class TestBusEvents:
    """Test event dataclasses."""

    def test_inbound_message_fields(self):
        from bus.events import InboundMessage

        msg = InboundMessage(
            channel="whatsapp",
            sender_id="+5511999990000",
            chat_id="chat_123",
            content="Hello",
            is_owner=True,
            sender_name="John",
            chat_type="direct",
        )
        assert msg.channel == "whatsapp"
        assert msg.sender_id == "+5511999990000"
        assert msg.content == "Hello"
        assert msg.is_owner is True
        assert msg.chat_type == "direct"
        assert msg.monitor_only is False
        assert msg.media_url is None

    def test_inbound_message_session_key(self):
        from bus.events import InboundMessage

        msg = InboundMessage(
            channel="whatsapp",
            sender_id="+5511999990000",
            chat_id="chat_123",
            content="Hi",
        )
        assert msg.session_key == "whatsapp:chat_123"

    def test_outbound_message_fields(self):
        from bus.events import OutboundMessage

        msg = OutboundMessage(
            channel="whatsapp",
            chat_id="owner",
            content="Task created!",
        )
        assert msg.channel == "whatsapp"
        assert msg.chat_id == "owner"
        assert msg.content == "Task created!"
        assert msg.reply_to is None
        assert msg.metadata == {}

    def test_outbound_message_with_metadata(self):
        from bus.events import OutboundMessage

        msg = OutboundMessage(
            channel="whatsapp",
            chat_id="owner",
            content="Alert",
            metadata={"source": "heartbeat"},
        )
        assert msg.metadata["source"] == "heartbeat"


class TestMessageBus:
    """Test sync MessageBus."""

    def test_publish_consume_inbound(self):
        from bus.queue import MessageBus
        from bus.events import InboundMessage

        bus = MessageBus()
        msg = InboundMessage(
            channel="whatsapp",
            sender_id="+5511999990000",
            chat_id="chat_1",
            content="Test message",
        )
        bus.publish_inbound(msg)
        assert bus.inbound_size == 1

        received = bus.consume_inbound(timeout=1.0)
        assert received is not None
        assert received.content == "Test message"
        assert bus.inbound_size == 0

    def test_publish_consume_outbound(self):
        from bus.queue import MessageBus
        from bus.events import OutboundMessage

        bus = MessageBus()
        msg = OutboundMessage(
            channel="whatsapp",
            chat_id="owner",
            content="Response",
        )
        bus.publish_outbound(msg)
        assert bus.outbound_size == 1

        received = bus.consume_outbound(timeout=1.0)
        assert received is not None
        assert received.content == "Response"

    def test_consume_inbound_timeout(self):
        from bus.queue import MessageBus

        bus = MessageBus()
        result = bus.consume_inbound(timeout=0.1)
        assert result is None

    def test_subscriber_dispatch(self):
        from bus.queue import MessageBus
        from bus.events import OutboundMessage

        bus = MessageBus()
        received_messages = []

        def callback(msg: OutboundMessage):
            received_messages.append(msg)

        bus.subscribe_outbound("whatsapp", callback)
        bus.start_dispatcher()

        try:
            bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id="owner",
                content="Dispatched!",
            ))
            # Wait for dispatcher to process
            time.sleep(0.5)

            assert len(received_messages) == 1
            assert received_messages[0].content == "Dispatched!"
        finally:
            bus.stop()

    def test_subscriber_multiple_channels(self):
        from bus.queue import MessageBus
        from bus.events import OutboundMessage

        bus = MessageBus()
        wa_messages = []
        system_messages = []

        bus.subscribe_outbound("whatsapp", lambda m: wa_messages.append(m))
        bus.subscribe_outbound("system", lambda m: system_messages.append(m))
        bus.start_dispatcher()

        try:
            bus.publish_outbound(OutboundMessage(
                channel="whatsapp", chat_id="owner", content="WA msg",
            ))
            bus.publish_outbound(OutboundMessage(
                channel="system", chat_id="internal", content="SYS msg",
            ))
            time.sleep(0.5)

            assert len(wa_messages) == 1
            assert len(system_messages) == 1
            assert wa_messages[0].content == "WA msg"
            assert system_messages[0].content == "SYS msg"
        finally:
            bus.stop()


class TestMessageBusSingleton:
    """Test singleton pattern."""

    def test_get_message_bus_returns_same_instance(self):
        from bus.queue import get_message_bus, reset_message_bus

        reset_message_bus()
        bus1 = get_message_bus()
        bus2 = get_message_bus()
        assert bus1 is bus2
        reset_message_bus()

    def test_reset_clears_singleton(self):
        from bus.queue import get_message_bus, reset_message_bus

        bus1 = get_message_bus()
        reset_message_bus()
        bus2 = get_message_bus()
        assert bus1 is not bus2
        reset_message_bus()
