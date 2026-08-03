"""Schema registry port contract.

The schema registry is the canonical catalog of every active schema the
system produces or consumes. It exists so that the codebase can answer
four questions programmatically instead of by code archaeology:

* "What is the current version of schema X?"
* "Who owns this schema?"
* "Can reader R safely consume writer W's output?"
* "Is this schema active, deprecated, or retired?"

Scope (§13.4 C-01, §10.3 of the optimization guide): the registry is a
**port** — a Protocol that any backing store (in-memory, file-backed,
remote) can satisfy. The domain ships a default in-memory implementation
(``flaghunter.domain.schema_catalog.InMemorySchemaRegistry``); future
slices may add a JSON-file adapter or a remote-registry adapter without
changing any caller.

The port deliberately stays thin: it never imports runtime / LLM / MCP /
storage / IO, so a domain unit test or a CLI tool can use it without
pulling in the rest of the application.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable

# Re-exported for caller convenience; concrete type lives in the domain.
SchemaRecord = Mapping[str, object]


@runtime_checkable
class SchemaRegistryPort(Protocol):
    """Catalog of every active (and historical) schema in the system.

    Implementations must be safe to call from multiple threads; the
    default in-memory implementation uses a plain dict under a Lock.
    """

    def register(self, record: Mapping[str, object]) -> None:
        """Insert or replace a schema record.

        Raises ``ValueError`` on duplicate ``(schema_id, version)`` pairs
        with different payloads, or on records missing the
        ``schema_id`` / ``version`` / ``owner`` / ``status`` fields.
        """
        ...

    def get(self, schema_id: str, version: str) -> Mapping[str, object] | None:
        """Return the record for ``(schema_id, version)`` or ``None``."""
        ...

    def latest(self, schema_id: str) -> Mapping[str, object] | None:
        """Return the most recent ACTIVE record for ``schema_id`` or ``None``."""
        ...

    def find_by_owner(self, owner: str) -> Sequence[Mapping[str, object]]:
        """Return every record whose ``owner`` field matches exactly."""
        ...

    def active_schemas(self) -> Sequence[Mapping[str, object]]:
        """Return every record whose ``status`` is ``active``."""
        ...

    def is_compatible(
        self,
        reader: Mapping[str, object],
        writer: Mapping[str, object],
    ) -> bool:
        """Return True iff a reader declared by ``reader`` can safely
        consume a payload emitted by ``writer``.

        The compatibility rules are owned by the registry implementation;
        see ``InMemorySchemaRegistry.is_compatible`` for the default
        semantics. Both arguments must be records previously returned by
        ``register``; passing an ad-hoc dict is undefined.
        """
        ...

    def __iter__(self) -> Iterable[Mapping[str, object]]:
        """Iterate over every registered record (any status)."""
        ...
