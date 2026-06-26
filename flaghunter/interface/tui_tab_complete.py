"""Slash-command tab-completion helpers (debt ledger 第五波·TUI 刀2).

Extracted from tui.py. Four pure string helpers used by the CommandSuggestions
widget to match a partial input against a command signature, render the
suggestion row, and produce the Tab-completed value. They call only each other
(``_sig_matches`` -> ``_is_placeholder``) plus str builtins — zero dependency on
any tui widget/screen, FlagHunterTUI, or module globals (the signature is passed
in as an argument) — so the cluster is down-closed. tui.py re-imports them so the
stay-behind CommandSuggestions caller resolves unchanged.
"""

from __future__ import annotations


def _is_placeholder(token: str) -> bool:
    return (token.startswith("<") and token.endswith(">")) or (
        token.startswith("[") and token.endswith("]")
    )


def _sig_matches(sig: str, value: str) -> bool:
    """Return True if the current input is a valid prefix path of the signature."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    completed = val_tokens if has_trailing else val_tokens[:-1]
    partial = "" if has_trailing else (val_tokens[-1] if val_tokens else "")

    if len(completed) > len(sig_tokens):
        return False

    for i, tok in enumerate(completed):
        sig_tok = sig_tokens[i]
        if _is_placeholder(sig_tok):
            continue
        if sig_tok != tok:
            return False

    if partial:
        next_idx = len(completed)
        if next_idx >= len(sig_tokens):
            return False
        sig_tok = sig_tokens[next_idx]
        if _is_placeholder(sig_tok):
            return True
        return sig_tok.startswith(partial)

    return True


def _get_display_parts(sig: str, value: str) -> tuple:
    """Return (next_token, remaining_tokens_str) for rendering the suggestion row."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    next_idx = len(val_tokens) if has_trailing else max(0, len(val_tokens) - 1)
    next_tok = sig_tokens[next_idx] if next_idx < len(sig_tokens) else ""
    remaining = (
        " ".join(sig_tokens[next_idx + 1 :]) if next_idx + 1 < len(sig_tokens) else ""
    )
    return next_tok, remaining


def _tab_complete(sig: str, value: str) -> str:
    """Return new input value produced by Tab-completing the given signature."""
    sig_tokens = sig.split()
    stripped = value.rstrip()
    has_trailing = bool(value) and value[-1] == " "
    val_tokens = stripped.split() if stripped else []

    next_idx = len(val_tokens) if has_trailing else max(0, len(val_tokens) - 1)
    if next_idx >= len(sig_tokens):
        return value

    kept = val_tokens[:next_idx]
    return " ".join(kept + [sig_tokens[next_idx]]) + " "
