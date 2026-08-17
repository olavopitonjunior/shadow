"""Collector Worker - Z-API data collection, contact import."""

from graph.workers.base import build_worker_subgraph

collector_subgraph = build_worker_subgraph("collector")
