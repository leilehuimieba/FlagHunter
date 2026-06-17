"""Per-chain mixin modules for the CTF dispatcher (P4 modular split).

``CTFTaskDispatcher`` is composed from these mixins so each attack chain lives
in its own module instead of one ~10k-line class. The mixins share dispatcher
state via ``self`` at runtime (the composed class provides every attribute);
shed, dependency-free types live in :mod:`.base` to avoid an import cycle with
``ctf_dispatcher``.
"""
