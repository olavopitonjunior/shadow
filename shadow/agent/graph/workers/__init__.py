"""Worker subgraphs for Shadow agents.

Phase 1: Workers use passthrough to existing ReActAgent (see builder.py).
Phase 2: Each worker becomes a proper LangGraph subgraph with its own
         ReAct loop, tool set, and retry policies.

Workers:
- crm.py: Contact management, memories, relationships (14 tools)
- planner.py: Tasks, appointments, reminders (12 tools)
- analytics.py: Dashboards, reports, insights (8 tools)
- docgen.py: Proposals, contracts, PDFs (6 tools)
- collector.py: Z-API data collection, contact import (8 tools)
"""
