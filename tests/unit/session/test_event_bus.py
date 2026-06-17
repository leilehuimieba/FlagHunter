"""Unit tests for the neutral EventBus (architecture joint A, invariant I3)."""

from pentestagent.session.event_bus import Event, EventBus


def test_subscribe_receives_emitted_events():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(received.append)

    bus.emit("hello", {"x": 1}, source="test")

    assert len(received) == 1
    assert received[0].type == "hello"
    assert received[0].data == {"x": 1}
    assert received[0].source == "test"


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received: list[Event] = []
    unsub = bus.subscribe(received.append)

    bus.emit("a")
    unsub()
    bus.emit("b")

    assert [e.type for e in received] == ["a"]
    assert bus.subscriber_count == 0


def test_unsubscribe_is_idempotent():
    bus = EventBus()
    unsub = bus.subscribe(lambda e: None)
    unsub()
    unsub()  # must not raise
    assert bus.subscriber_count == 0


def test_faulty_subscriber_does_not_break_publisher():
    """I3: one bad consumer must never take down the agent loop."""
    bus = EventBus()
    good: list[Event] = []

    def boom(_event):
        raise RuntimeError("subscriber blew up")

    bus.subscribe(boom)
    bus.subscribe(good.append)

    # emit must not raise despite the faulty subscriber
    bus.emit("ping")

    assert len(good) == 1
    assert good[0].type == "ping"


def test_multiple_subscribers_all_receive():
    bus = EventBus()
    a: list[Event] = []
    b: list[Event] = []
    bus.subscribe(a.append)
    bus.subscribe(b.append)

    bus.emit("evt")

    assert len(a) == 1 and len(b) == 1


def test_emit_data_is_copied_not_shared():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(received.append)

    payload = {"k": "v"}
    bus.emit("evt", payload)
    payload["k"] = "mutated"

    assert received[0].data == {"k": "v"}
