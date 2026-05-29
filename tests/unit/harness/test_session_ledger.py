from __future__ import annotations

from pentestagent.harness.session_ledger import SessionLedger


def test_session_ledger_appends_and_reads_events(tmp_path) -> None:
    ledger = SessionLedger(tmp_path)

    first = ledger.append_event(
        "run-ledger-1",
        "dispatcher_started",
        {"target": "http://challenge.test", "type": "web"},
    )
    second = ledger.append_event(
        "run-ledger-1",
        "task_finished",
        {"success": True, "flag": "flag{ok}"},
    )

    events = ledger.read_events("run-ledger-1")

    assert ledger.path_for_run("run-ledger-1").exists()
    assert [item["event_type"] for item in events] == [
        "dispatcher_started",
        "task_finished",
    ]
    assert events[0]["run_id"] == "run-ledger-1"
    assert events[0]["payload"] == first["payload"]
    assert events[1]["payload"] == second["payload"]


def test_session_ledger_tail_events_returns_latest_slice(tmp_path) -> None:
    ledger = SessionLedger(tmp_path)

    for idx in range(4):
        ledger.append_event(
            "run-ledger-tail",
            f"event_{idx}",
            {"index": idx},
        )

    tail = ledger.tail_events("run-ledger-tail", limit=2)

    assert [item["event_type"] for item in tail] == ["event_2", "event_3"]
    assert [item["payload"]["index"] for item in tail] == [2, 3]
