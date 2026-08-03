"""Domain-layer contracts and value objects."""

from .active_schemas import (
    known_active_schema_count,
    register_all_active_schemas,
)
from .atomic_file import (
    AtomicWriteError,
    FilesystemAtomicFile,
    InMemoryAtomicFile,
    request_from_mapping,
)
from .schema_catalog import (
    SCHEMA_REGISTRY_DOMAIN_VERSION,
    InMemorySchemaRegistry,
    SchemaRecord,
    SchemaStatus,
    is_reader_compatible,
    record_from_mapping,
)

__all__ = [
    "AtomicWriteError",
    "FilesystemAtomicFile",
    "InMemoryAtomicFile",
    "InMemorySchemaRegistry",
    "SCHEMA_REGISTRY_DOMAIN_VERSION",
    "SchemaRecord",
    "SchemaStatus",
    "is_reader_compatible",
    "known_active_schema_count",
    "record_from_mapping",
    "register_all_active_schemas",
    "request_from_mapping",
]
