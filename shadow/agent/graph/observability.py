"""
Observability - LangSmith tracing integration with sampling.

Enables tracing for a configurable percentage of graph invocations
to control costs while maintaining observability.

Environment variables:
- LANGCHAIN_TRACING_V2: "true" to enable tracing
- LANGCHAIN_PROJECT: Project name in LangSmith (default: "shadow-prod")
- LANGCHAIN_API_KEY: LangSmith API key
- LANGSMITH_SAMPLE_RATE: Fraction of invocations to trace (default: 0.1 = 10%)
"""

from __future__ import annotations

import os
import random


# Default: trace 10% of invocations
SAMPLE_RATE = float(os.getenv("LANGSMITH_SAMPLE_RATE", "0.1"))


def should_trace() -> bool:
    """Determine if this invocation should be traced.

    Returns True for SAMPLE_RATE fraction of calls.
    Always returns False if LANGCHAIN_TRACING_V2 is not "true".
    """
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() != "true":
        return False
    return random.random() < SAMPLE_RATE


def setup_tracing():
    """Configure LangSmith tracing environment.

    Call once at startup. Sets project name and validates API key.
    """
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() != "true":
        print("[observability] LangSmith tracing disabled")
        return

    project = os.getenv("LANGCHAIN_PROJECT", "shadow-prod")
    api_key = os.getenv("LANGCHAIN_API_KEY")

    if not api_key:
        print("[observability] LANGCHAIN_API_KEY not set, tracing disabled")
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return

    os.environ["LANGCHAIN_PROJECT"] = project
    print(f"[observability] LangSmith tracing enabled (project: {project}, sample: {SAMPLE_RATE*100:.0f}%)")


def enable_tracing_for_request():
    """Enable tracing for the current request based on sampling.

    Call before each graph invocation. Sets LANGCHAIN_TRACING_V2
    based on the sampling decision.
    """
    if should_trace():
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"


def get_langsmith_traces(limit: int = 50) -> list[dict]:
    """Pull recent traces from LangSmith REST API.

    Used by the admin dashboard to display execution traces.
    Returns empty list if LangSmith is not configured.
    """
    try:
        from langsmith import Client

        client = Client()
        project = os.getenv("LANGCHAIN_PROJECT", "shadow-prod")

        runs = client.list_runs(
            project_name=project,
            execution_order=1,
            limit=limit,
        )

        return [
            {
                "id": str(run.id),
                "name": run.name,
                "status": run.status,
                "start_time": run.start_time.isoformat() if run.start_time else None,
                "end_time": run.end_time.isoformat() if run.end_time else None,
                "latency_ms": int(run.latency.total_seconds() * 1000) if run.latency else None,
                "total_tokens": run.total_tokens,
                "total_cost": run.total_cost,
                "error": run.error,
            }
            for run in runs
        ]
    except ImportError:
        return []
    except Exception as e:
        print(f"[observability] Failed to fetch LangSmith traces: {e}")
        return []
