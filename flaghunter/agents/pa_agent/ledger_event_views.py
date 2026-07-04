"""Compatibility shim for compact session-ledger readback contracts."""

from __future__ import annotations

from flaghunter.domain.challenge.contracts.ledger_events import (
    LEDGER_EVENT_TYPES,
    build_ledger_event_readback,
)

P2_LEDGER_EVENT_TYPES = LEDGER_EVENT_TYPES
build_p2_ledger_event_readback = build_ledger_event_readback

__all__ = [
    "LEDGER_EVENT_TYPES",
    "P2_LEDGER_EVENT_TYPES",
    "build_ledger_event_readback",
    "build_p2_ledger_event_readback",
]
