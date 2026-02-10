"""
Usage Tracker - Rastreamento de uso de API por provider.

Registra cada chamada de API (Claude, Gemini, OpenAI) com tokens,
latencia e custo calculado. Usado pelo admin dashboard para
monitoramento de custos e observabilidade.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generator

from logger import get_logger

logger = get_logger(__name__)

# Singleton global - inicializado em main.py
_tracker: UsageTracker | None = None


@dataclass
class UsageRecord:
    provider: str           # 'anthropic', 'google', 'openai'
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    operation: str = ""     # 'chat', 'entity_extraction', 'summarization', 'embedding', 'transcription'
    session_id: str = ""
    latency_ms: int = 0
    success: bool = True
    error_message: str = ""
    cost_usd: float = 0.0


class UsageTracker:
    """Rastreia uso de API e grava em storage."""

    def __init__(self, storage: Any = None) -> None:
        self._storage = storage
        self._pricing: dict[tuple[str, str], tuple[float, float]] = {}
        self._load_default_pricing()

    def _load_default_pricing(self) -> None:
        """Precos default por milhao de tokens (input, output) em USD."""
        self._pricing = {
            ("anthropic", "claude-sonnet-4-20250514"): (3.0, 15.0),
            ("anthropic", "claude-haiku-3-20240307"): (0.25, 1.25),
            ("google", "gemini-2.5-flash-lite"): (0.0, 0.0),
            ("google", "gemini-2.0-flash"): (0.10, 0.40),
            ("google", "gemini-1.5-flash"): (0.075, 0.30),
            ("openai", "text-embedding-3-small"): (0.02, 0.0),
        }

    def _calculate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calcula custo em USD baseado nos precos por milhao de tokens."""
        key = (provider, model)
        # Buscar preco exato ou por prefixo do modelo
        prices = self._pricing.get(key)
        if not prices:
            # Tentar match por prefixo
            for (p, m), pr in self._pricing.items():
                if p == provider and model.startswith(m.split("-")[0]):
                    prices = pr
                    break
        if not prices:
            return 0.0
        input_price, output_price = prices
        cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
        return round(cost, 6)

    def record(self, record: UsageRecord) -> None:
        """Registra uso de API no storage."""
        record.cost_usd = self._calculate_cost(
            record.provider, record.model, record.input_tokens, record.output_tokens,
        )

        if self._storage:
            try:
                self._storage.record_api_usage(
                    provider=record.provider,
                    model=record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    operation=record.operation,
                    session_id=record.session_id,
                    cost_usd=record.cost_usd,
                    latency_ms=record.latency_ms,
                    success=record.success,
                    error_message=record.error_message,
                )
            except Exception as e:
                logger.warning(f"Failed to record API usage: {e}")
        else:
            logger.debug(
                f"Usage: {record.provider}/{record.model} "
                f"in={record.input_tokens} out={record.output_tokens} "
                f"cost=${record.cost_usd:.4f} latency={record.latency_ms}ms"
            )

    @contextmanager
    def track(
        self,
        provider: str,
        model: str,
        operation: str = "",
        session_id: str = "",
    ) -> Generator[UsageRecord, None, None]:
        """Context manager que mede latencia e grava automaticamente."""
        record = UsageRecord(
            provider=provider,
            model=model,
            operation=operation,
            session_id=session_id,
        )
        start = time.monotonic()
        try:
            yield record
        except Exception as e:
            record.success = False
            record.error_message = str(e)[:500]
            raise
        finally:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            self.record(record)


def get_tracker() -> UsageTracker:
    """Retorna o tracker global."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker


def init_tracker(storage: Any) -> UsageTracker:
    """Inicializa o tracker global com storage."""
    global _tracker
    _tracker = UsageTracker(storage)
    return _tracker
