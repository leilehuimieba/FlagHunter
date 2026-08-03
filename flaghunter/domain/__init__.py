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
from .identity_service import (
    InMemoryIdentityService,
    UuidIdentityService,
)
from .process_lock import (
    FilesystemProcessLock,
    InMemoryProcessLock,
    LockHandle,
    path_from_mapping,
)
from .schema_catalog import (
    SCHEMA_REGISTRY_DOMAIN_VERSION,
    InMemorySchemaRegistry,
    SchemaRecord,
    SchemaStatus,
    is_reader_compatible,
    record_from_mapping,
)
from .time_service import (
    FixedTimeService,
    SystemTimeService,
)

__all__ = [
    "AtomicWriteError",
    "FilesystemProcessLock",
    "FilesystemAtomicFile",
    "FixedTimeService",
    "InMemoryAtomicFile",
    "InMemoryIdentityService",
    "InMemoryProcessLock",
    "LockHandle",
    "InMemorySchemaRegistry",
    "SCHEMA_REGISTRY_DOMAIN_VERSION",
    "SchemaRecord",
    "SchemaStatus",
    "FixedTimeService",
    "SystemTimeService",
    "UuidIdentityService",
    "is_reader_compatible",
    "known_active_schema_count",
    "path_from_mapping",
    "record_from_mapping",
    "register_all_active_schemas",
    "request_from_mapping",
]
