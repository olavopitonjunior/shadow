"""
Integration tests for LangGraph multi-agent orchestration.

Tests:
1. All imports resolve
2. Graph compiles without error
3. Three-tier routing works correctly
4. State schema is valid
5. Worker tool loadouts are correct
6. SSE event bus works
7. DocGen and Collector tools import
"""

import os
import sys

# Ensure shadow/agent is on the path
agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

import pytest


# ── 1. Import Tests ──

class TestImports:
    """Verify all graph modules import without error."""

    def test_import_state(self):
        from graph.state import ShadowState, WorkerState, WorkerResult, default_shadow_state
        assert ShadowState is not None
        assert WorkerState is not None
        assert WorkerResult is not None
        state = default_shadow_state()
        assert "messages" in state
        assert "fan_out_workers" in state

    def test_import_supervisor(self):
        from graph.supervisor import supervisor_think_node, supervisor_route, SUPERVISOR_SYSTEM
        assert callable(supervisor_think_node)
        assert callable(supervisor_route)
        assert "crm" in SUPERVISOR_SYSTEM

    def test_import_nodes(self):
        from graph.nodes.intake import intake_node
        from graph.nodes.router import route_message
        from graph.nodes.fast_path import fast_path_node
        from graph.nodes.rag import rag_retrieve_node
        from graph.nodes.synthesize import synthesize_node, check_quality
        from graph.nodes.respond import respond_node
        assert all(callable(f) for f in [
            intake_node, route_message, fast_path_node,
            rag_retrieve_node, synthesize_node, check_quality, respond_node,
        ])

    def test_import_streaming(self):
        from graph.streaming import AgentEventBus, AgentEvent
        assert AgentEventBus is not None
        assert AgentEvent is not None

    def test_import_observability(self):
        from graph.observability import should_trace, setup_tracing
        assert callable(should_trace)
        assert callable(setup_tracing)

    def test_import_zapi_client(self):
        from graph.adapters.zapi_client import ZAPIClient, ZAPIRateLimiter
        assert ZAPIClient is not None
        assert ZAPIRateLimiter is not None

    def test_import_docgen_tools(self):
        from graph.adapters.docgen_tools import get_docgen_tools
        tools = get_docgen_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "list_templates" in names
        assert "generate_document" in names

    def test_import_collector_tools(self):
        from graph.adapters.collector_tools import get_collector_tools
        tools = get_collector_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "sync_contacts_to_crm" in names
        assert "get_whatsapp_chats" in names
        assert "summarize_conversation" in names


# ── 2. Graph Compile Test ──

class TestGraphCompile:
    """Verify the graph compiles and has correct topology."""

    def test_graph_compiles(self):
        from graph.builder import build_shadow_graph
        graph = build_shadow_graph(checkpointer=None)
        assert graph is not None

    def test_graph_has_nodes(self):
        from graph.builder import build_shadow_graph
        graph = build_shadow_graph(checkpointer=None)
        # get_graph() returns a DrawableGraph — nodes may be strings or objects
        graph_data = graph.get_graph()
        # Handle both node formats
        if hasattr(graph_data, "nodes"):
            nodes = graph_data.nodes
            if isinstance(nodes, dict):
                node_ids = set(nodes.keys())
            else:
                node_ids = {n.id if hasattr(n, "id") else str(n) for n in nodes}
        else:
            node_ids = set()
        expected = {"intake", "fast_path", "rag_retrieve", "supervisor_think",
                    "crm", "planner", "analytics", "docgen", "collector",
                    "synthesize", "respond"}
        for expected_node in expected:
            assert expected_node in node_ids, f"Missing node: {expected_node}"


# ── 3. Routing Tests ──

class TestRouting:
    """Test three-tier routing logic."""

    def test_fast_path_greetings(self):
        from graph.nodes.router import route_message
        for greeting in ["oi", "ping", "help"]:
            result = route_message({"body": greeting})
            assert result == "fast_path", f"'{greeting}' should be fast_path, got {result}"

    def test_fast_path_commands(self):
        from graph.nodes.router import route_message
        for cmd in ["tarefas", "agenda", "resumo"]:
            result = route_message({"body": cmd})
            assert result == "fast_path", f"'{cmd}' should be fast_path, got {result}"

    def test_keyword_planner(self):
        from graph.nodes.router import route_message
        result = route_message({"body": "cria tarefa para amanhã"})
        assert result == "planner"

    def test_keyword_crm(self):
        from graph.nodes.router import route_message
        result = route_message({"body": "quem é o João?"})
        assert result == "crm"

    def test_keyword_docgen(self):
        from graph.nodes.router import route_message
        result = route_message({"body": "gera uma proposta"})
        assert result == "docgen"

    def test_keyword_collector(self):
        from graph.nodes.router import route_message
        result = route_message({"body": "importa contatos do whatsapp"})
        assert result == "collector"

    def test_ambiguous_goes_to_supervisor(self):
        from graph.nodes.router import route_message
        result = route_message({"body": "o que você acha disso?"})
        assert result == "supervisor_think"

    def test_empty_body(self):
        from graph.nodes.router import route_message
        result = route_message({"body": ""})
        assert result == "supervisor_think"


# ── 4. State Schema Tests ──

class TestStateSchema:
    """Verify state schema integrity."""

    def test_default_state_has_all_fields(self):
        from graph.state import default_shadow_state, ShadowState
        state = default_shadow_state()
        annotations = ShadowState.__annotations__
        for field_name in annotations:
            assert field_name in state, f"Missing field in default state: {field_name}"

    def test_worker_result_dataclass(self):
        from graph.state import WorkerResult
        r = WorkerResult(
            worker_name="crm",
            status="ok",
            display_text="test",
        )
        d = r.to_dict()
        assert d["worker_name"] == "crm"
        assert d["status"] == "ok"
        assert d["display_text"] == "test"


# ── 5. Supervisor Routing Tests ──

class TestSupervisorRouting:
    """Test supervisor_route function."""

    def test_direct_reply(self):
        from graph.supervisor import supervisor_route
        result = supervisor_route({"route": "direct_reply"})
        assert result == "respond"

    def test_worker_routes(self):
        from graph.supervisor import supervisor_route
        for worker in ["crm", "planner", "analytics", "docgen", "collector"]:
            result = supervisor_route({"route": worker})
            assert result == worker

    def test_unknown_route_fallback(self):
        from graph.supervisor import supervisor_route
        result = supervisor_route({"route": "unknown"})
        assert result == "respond"

    def test_fan_out_route(self):
        from graph.supervisor import supervisor_route
        result = supervisor_route({
            "route": "fan_out",
            "fan_out_workers": [
                {"agent": "crm", "task": "get João"},
                {"agent": "planner", "task": "list tasks"},
            ],
        })
        # Should return a list of Send objects
        assert isinstance(result, list)
        assert len(result) == 2


# ── 6. Intake Tests ──

class TestIntake:
    """Test intake node processing."""

    def test_basic_text_message(self):
        from graph.nodes.intake import intake_node
        result = intake_node({
            "raw_payload": {
                "body": "Hello world",
                "sender_phone": "+5511999887766",
                "sender_name": "Test User",
            },
        })
        assert result["body"] == "Hello world"
        assert result["sender_phone"] == "+5511999887766"
        assert result["sender_name"] == "Test User"
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "Hello world"

    def test_empty_payload(self):
        from graph.nodes.intake import intake_node
        result = intake_node({"raw_payload": {}})
        assert result["body"] == ""
        assert result["messages"][0].content == "[empty message]"

    def test_url_extraction(self):
        from graph.nodes.intake import _URL_PATTERN
        urls = _URL_PATTERN.findall("Check this out: https://example.com/page and more text")
        assert len(urls) == 1
        assert urls[0] == "https://example.com/page"


# ── 7. SSE Event Bus Tests ──

class TestEventBus:
    """Test SSE streaming event bus."""

    def test_event_bus_init(self):
        from graph.streaming import AgentEventBus
        bus = AgentEventBus()
        assert bus is not None
        assert hasattr(bus, "emit")
        assert hasattr(bus, "subscribe")

    def test_event_creation(self):
        from graph.streaming import AgentEvent
        from uuid import uuid4
        from datetime import datetime, timezone
        event = AgentEvent(
            event_id=str(uuid4()),
            event_type="node_start",
            node_name="crm",
            thread_id="owner:chat123",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        d = event.to_dict() if hasattr(event, "to_dict") else {"event_type": event.event_type, "node_name": event.node_name, "thread_id": event.thread_id}
        assert d["event_type"] == "node_start"
        assert d["node_name"] == "crm"
        assert d["thread_id"] == "owner:chat123"


# ── 8. Tool Adapter Tests ──

class TestToolAdapter:
    """Test tool loadout configuration."""

    def test_worker_tool_loadouts(self):
        from graph.adapters.tool_adapter import WORKER_TOOLS
        assert len(WORKER_TOOLS["crm"]) == 14
        assert len(WORKER_TOOLS["planner"]) == 12
        assert len(WORKER_TOOLS["analytics"]) == 8
        assert len(WORKER_TOOLS["docgen"]) == 6
        assert len(WORKER_TOOLS["collector"]) == 5

    def test_no_duplicate_tools_in_loadout(self):
        from graph.adapters.tool_adapter import WORKER_TOOLS
        for worker, tools in WORKER_TOOLS.items():
            assert len(tools) == len(set(tools)), f"Duplicate tools in {worker}"


# ── 9. Z-API Client Tests ──

class TestZAPIClient:
    """Test Z-API client initialization and rate limiter."""

    def test_rate_limiter(self):
        from graph.adapters.zapi_client import ZAPIRateLimiter
        limiter = ZAPIRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.acquire() == 0  # First request OK
        assert limiter.acquire() == 0  # Second request OK
        wait = limiter.acquire()       # Third should wait
        assert wait > 0

    def test_client_url_construction(self):
        from graph.adapters.zapi_client import ZAPIClient
        client = ZAPIClient(instance_id="test123", token="tok456")
        assert "test123" in client.base_url
        assert "tok456" in client.base_url


# ── 10. DocGen Template Tests ──

class TestDocGenTemplates:
    """Test document template listing."""

    def test_list_templates(self):
        from graph.adapters.docgen_tools import _list_templates
        result = _list_templates()
        assert "proposals" in result.lower() or "Template" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
