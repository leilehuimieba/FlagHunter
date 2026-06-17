"""Environment-variable helpers.

Canonical FlagHunter env vars use the ``FLAGHUNTER_`` prefix. The historical
``PENTESTAGENT_`` prefix is still honoured as a backward-compatible fallback so
existing ``.env`` files and shell exports keep working after the rename.

The alias is applied process-wide right after ``.env`` is loaded: for every
``PENTESTAGENT_<X>`` present in the environment, ``FLAGHUNTER_<X>`` is set to the
same value unless it is already defined (new name always wins). This keeps every
read site free to use the canonical ``FLAGHUNTER_`` name without per-call logic.
"""

import os

_LEGACY_PREFIX = "PENTESTAGENT_"
_PREFIX = "FLAGHUNTER_"


def apply_legacy_env_aliases() -> None:
    """Mirror any legacy ``PENTESTAGENT_*`` vars onto ``FLAGHUNTER_*``.

    Idempotent and safe to call multiple times. The canonical ``FLAGHUNTER_``
    value always takes precedence when both are set.
    """
    for key, value in list(os.environ.items()):
        if key.startswith(_LEGACY_PREFIX):
            canonical = _PREFIX + key[len(_LEGACY_PREFIX):]
            os.environ.setdefault(canonical, value)
