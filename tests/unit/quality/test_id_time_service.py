"""Identity and time service tests (C-05 — §13.4 of the optimization guide).

C-05 acceptance: "时序关联一致" — IDs, UTC timestamps, and
monotonic durations all flow through one boundary. These tests
pin the port contracts and the smaller invariants each
implementation must satisfy.

The C-05 ADR is at docs/adr/0002-id-and-time-policy.md; the
tests below are the executable counterpart of the policy.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone

import pytest

from flaghunter.domain import (
    FixedTimeService,
    InMemoryIdentityService,
    SystemTimeService,
    UuidIdentityService,
)
from flaghunter.ports import IdentityServicePort, TimeServicePort

# --- UuidIdentityService ----------------------------------------------------


class TestUuidIdentityService:
    def test_new_id_unprefixed_is_32_hex(self) -> None:
        svc = UuidIdentityService()
        new_id = svc.new_id()
        assert len(new_id) == 32
        assert re.fullmatch(r"[0-9a-f]{32}", new_id), new_id

    def test_new_id_with_prefix_uses_underscore(self) -> None:
        svc = UuidIdentityService()
        new_id = svc.new_id("task")
        assert new_id.startswith("task_")
        suffix = new_id[len("task_") :]
        assert len(suffix) == 32
        assert re.fullmatch(r"[0-9a-f]{32}", suffix)

    def test_new_id_with_kind_is_alias_for_prefix(self) -> None:
        svc = UuidIdentityService()
        a = svc.new_id_with_kind("session")
        b = svc.new_id("session")
        # The shape is identical, even though the values differ.
        assert a.split("_", 1)[0] == "session"
        assert b.split("_", 1)[0] == "session"
        assert a != b  # different actual ids

    def test_satisfies_port_protocol(self) -> None:
        assert isinstance(UuidIdentityService(), IdentityServicePort)

    def test_unique_across_many_calls(self) -> None:
        svc = UuidIdentityService()
        seen = {svc.new_id("run") for _ in range(5000)}
        assert len(seen) == 5000

    def test_rejects_empty_prefix(self) -> None:
        svc = UuidIdentityService()
        with pytest.raises(ValueError, match="non-empty"):
            svc.new_id("   ")


# --- InMemoryIdentityService ------------------------------------------------


class TestInMemoryIdentityService:
    def test_emits_32_hex(self) -> None:
        svc = InMemoryIdentityService()
        new_id = svc.new_id()
        assert re.fullmatch(r"[0-9a-f]{32}", new_id)

    def test_counter_increments(self) -> None:
        svc = InMemoryIdentityService()
        a = svc.new_id()
        b = svc.new_id()
        assert a != b

    def test_reset_returns_to_initial(self) -> None:
        svc = InMemoryIdentityService()
        first = svc.new_id()
        svc.reset()
        again = svc.new_id()
        assert first == again

    def test_satisfies_port_protocol(self) -> None:
        assert isinstance(InMemoryIdentityService(), IdentityServicePort)

    def test_thread_safe(self) -> None:
        svc = InMemoryIdentityService()
        seen: set[str] = set()
        seen_lock = threading.Lock()

        def worker() -> None:
            for _ in range(500):
                value = svc.new_id("x")
                with seen_lock:
                    seen.add(value)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 4 * 500 = 2000 distinct ids, no collisions.
        assert len(seen) == 2000


# --- SystemTimeService ------------------------------------------------------


class TestSystemTimeService:
    def test_utc_now_is_aware(self) -> None:
        clock = SystemTimeService()
        now = clock.utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_utc_now_iso_uses_z_suffix(self) -> None:
        clock = SystemTimeService()
        iso = clock.utc_now_iso()
        assert iso.endswith("Z"), iso
        # No "+00:00" tail.
        assert "+00:00" not in iso

    def test_monotonic_now_is_monotonic(self) -> None:
        clock = SystemTimeService()
        samples = [clock.monotonic_now() for _ in range(20)]
        # Each subsequent sample is >= the previous one.
        for prev, cur in zip(samples, samples[1:], strict=False):
            assert cur >= prev

    def test_elapsed_since_is_non_negative(self) -> None:
        clock = SystemTimeService()
        start = clock.monotonic_now()
        # The clock advances naturally between samples; we cannot
        # assert "exactly" but we can assert the contract is
        # "monotonic_now() - start_monotonic".
        elapsed = clock.elapsed_since(start)
        assert elapsed >= 0

    def test_satisfies_port_protocol(self) -> None:
        assert isinstance(SystemTimeService(), TimeServicePort)


# --- FixedTimeService -------------------------------------------------------


class TestFixedTimeService:
    def test_default_utc_is_aware(self) -> None:
        clock = FixedTimeService()
        now = clock.utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_default_iso_uses_z_suffix(self) -> None:
        clock = FixedTimeService()
        iso = clock.utc_now_iso()
        assert iso.endswith("Z")

    def test_fixed_value_is_returned(self) -> None:
        anchor = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
        clock = FixedTimeService(utc_at=anchor)
        assert clock.utc_now() == anchor
        assert clock.utc_now_iso() == "2026-08-04T12:00:00Z"

    def test_factory_advances(self) -> None:
        anchor = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
        state = {"i": 0}

        def factory() -> datetime:
            state["i"] += 1
            return anchor + timedelta(seconds=state["i"])

        clock = FixedTimeService(utc_factory=factory)
        assert clock.utc_now() == anchor + timedelta(seconds=1)
        assert clock.utc_now() == anchor + timedelta(seconds=2)

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FixedTimeService(utc_at=datetime(2026, 8, 4, 12, 0, 0))

    def test_rejects_mutually_exclusive_utc_args(self) -> None:
        anchor = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="utc_at or utc_factory"):
            FixedTimeService(utc_at=anchor, utc_factory=lambda: anchor)

    def test_rejects_non_datetime_factory(self) -> None:
        clock = FixedTimeService(utc_factory=lambda: "not a datetime")
        with pytest.raises(RuntimeError, match="must return a datetime"):
            clock.utc_now()

    def test_mono_factory_advances(self) -> None:
        state = {"t": 1000.0}

        def factory() -> float:
            state["t"] += 1.0
            return state["t"]

        clock = FixedTimeService(mono_factory=factory)
        assert clock.monotonic_now() == 1001.0
        assert clock.monotonic_now() == 1002.0

    def test_elapsed_since_uses_injected_mono(self) -> None:
        state = {"t": 1000.0}

        def factory() -> float:
            state["t"] += 5.0
            return state["t"]

        clock = FixedTimeService(mono_factory=factory)
        assert clock.elapsed_since(1000.0) == 5.0

    def test_satisfies_port_protocol(self) -> None:
        assert isinstance(FixedTimeService(), TimeServicePort)


# --- Migration sanity -------------------------------------------------------


class TestMigrationSanity:
    """Spot-check that the migrated call sites land on the port."""

    def test_task_dag_plan_new_id_is_32_hex_with_prefix(self) -> None:
        from flaghunter.domain.challenge.contracts.task_dag_plan import _new_id

        new_id = _new_id("task")
        assert new_id.startswith("task_")
        assert re.fullmatch(r"task_[0-9a-f]{32}", new_id), new_id

    def test_task_dag_plan_now_ts_is_a_recent_epoch_float(self) -> None:
        from flaghunter.domain.challenge.contracts.task_dag_plan import _now_ts

        # The function returns a float unix epoch. The numeric
        # value is system-clock-dependent but should be a sane
        # 2026-era timestamp.
        value = _now_ts()
        assert isinstance(value, float)
        # 2026-01-01 .. 2027-01-01 in unix epoch seconds.
        assert 1767225600.0 <= value <= 1798761600.0, value

    def test_ctf_state_new_id_is_32_hex_with_prefix(self) -> None:
        from flaghunter.agents.pa_agent.ctf_state import _new_id

        new_id = _new_id("trace")
        assert re.fullmatch(r"trace_[0-9a-f]{32}", new_id), new_id

    def test_solve_node_new_id_is_32_hex_with_prefix(self) -> None:
        from flaghunter.agents.pa_agent.solve_node import _new_id

        new_id = _new_id("node")
        assert re.fullmatch(r"node_[0-9a-f]{32}", new_id), new_id

    def test_state_transition_timestamp_is_aware_utc(self) -> None:
        from flaghunter.agents.state import StateTransition

        t = StateTransition(from_state=None, to_state=None)  # type: ignore[arg-type]
        assert t.timestamp.tzinfo is not None
        assert t.timestamp.tzinfo == timezone.utc

    def test_worker_pool_id_is_32_hex_with_prefix(self) -> None:
        from flaghunter.agents.crew.worker_pool import WorkerPool

        wp = WorkerPool.__new__(WorkerPool)
        new_id = wp._generate_id()
        assert re.fullmatch(r"agent_[0-9a-f]{32}", new_id), new_id
