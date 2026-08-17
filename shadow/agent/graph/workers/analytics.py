"""Analytics Worker - Dashboards, reports, insights."""

from graph.workers.base import build_worker_subgraph

analytics_subgraph = build_worker_subgraph("analytics")
