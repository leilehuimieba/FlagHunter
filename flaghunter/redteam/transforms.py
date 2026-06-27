"""Deterministic obfuscation / encoding transforms for red-team payloads.

Each :class:`Transform` is a pure ``str -> str`` function that rewrites an
attack string into an equivalent-but-obfuscated form. They model the evasion
techniques a guardrail's keyword/regex layer must survive: alternate encodings,
Unicode confusables, zero-width insertion, bidi tricks, and multi-layer nesting
(via :func:`apply_chain`).

The ``evades_rescan`` flag captures a *specific* property of the target middleware
(Fulcrum): its ``keyword_rules`` detector base64/hex-decodes inputs and re-scans
them. So ``base64`` / ``hex`` are NOT evasive against it (the rescan recovers the
trigger and re-flags) — they are *controls* that prove the rescan works. Every
other encoding here is **not** covered by that rescan, so it tests whether the
deeper ml_classifier / llm_judge layers catch the semantic intent.

All transforms are deterministic: same input always yields the same output (no
randomness, gzip mtime pinned to 0), so generated corpora are reproducible and
diffable.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Dict, List

# --- Unicode confusable maps ------------------------------------------------
# Latin -> visually-identical Cyrillic/Greek code points (homoglyph attack).
_HOMOGLYPHS: Dict[str, str] = {
    "a": "а", "c": "с", "e": "е", "i": "і", "j": "ј", "o": "о", "p": "р",
    "s": "ѕ", "x": "х", "y": "у", "h": "һ", "k": "к", "n": "ո",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "I": "І", "K": "К",
    "M": "М", "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "Ү",
}

_LEET: Dict[str, str] = {
    "a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "l": "1",
    "g": "9", "b": "8",
    "A": "4", "E": "3", "I": "1", "O": "0", "S": "5", "T": "7", "L": "1",
    "G": "9", "B": "8",
}

# International Morse for A-Z / 0-9. Word separator = " / ".
_MORSE: Dict[str, str] = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..", "0": "-----", "1": ".----", "2": "..---",
    "3": "...--", "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
}

_ZWSP = "​"  # zero-width space
_RLO = "‮"   # right-to-left override
_PDF = "‬"   # pop directional formatting


def _b(text: str) -> bytes:
    return text.encode("utf-8")


# --- Transform implementations ----------------------------------------------
def _base64(text: str) -> str:
    return base64.b64encode(_b(text)).decode("ascii")


def _hex(text: str) -> str:
    return binascii.hexlify(_b(text)).decode("ascii")


def _base32(text: str) -> str:
    return base64.b32encode(_b(text)).decode("ascii")


def _base64_urlsafe(text: str) -> str:
    # URL-safe alphabet uses '-' and '_' instead of '+' and '/'. A defender that
    # only feeds the standard alphabet to its base64 rescan misses this variant.
    return base64.urlsafe_b64encode(_b(text)).decode("ascii")


def _base85(text: str) -> str:
    return base64.b85encode(_b(text)).decode("ascii")


def _ascii85(text: str) -> str:
    # Adobe/ASCII85 (distinct from b85): <~ ... ~> framing is common.
    return base64.a85encode(_b(text), adobe=True).decode("ascii")


def _octal_escape(text: str) -> str:
    return "".join(f"\\{b:03o}" for b in _b(text))


def _rot13(text: str) -> str:
    import codecs

    return codecs.encode(text, "rot_13")


def _url(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def _url_double(text: str) -> str:
    return urllib.parse.quote(urllib.parse.quote(text, safe=""), safe="")


def _html_decimal(text: str) -> str:
    return "".join(f"&#{ord(ch)};" for ch in text)


def _gzip_b64(text: str) -> str:
    # mtime=0 makes the gzip header deterministic.
    return base64.b64encode(gzip.compress(_b(text), mtime=0)).decode("ascii")


def _gzip_b32(text: str) -> str:
    # gzip then Base32: pairs a multi-stage decode with the non-standard alphabet.
    return base64.b32encode(gzip.compress(_b(text), mtime=0)).decode("ascii")


def _morse(text: str) -> str:
    out: List[str] = []
    for ch in text.upper():
        if ch == " ":
            out.append("/")
        elif ch in _MORSE:
            out.append(_MORSE[ch])
        else:
            out.append(ch)
    return " ".join(out)


def _homoglyph(text: str) -> str:
    return "".join(_HOMOGLYPHS.get(ch, ch) for ch in text)


def _zero_width(text: str) -> str:
    return _ZWSP.join(text)


def _fullwidth(text: str) -> str:
    out: List[str] = []
    for ch in text:
        code = ord(ch)
        if ch == " ":
            out.append("　")
        elif 0x21 <= code <= 0x7E:
            out.append(chr(code + 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _leetspeak(text: str) -> str:
    return "".join(_LEET.get(ch, ch) for ch in text)


def _bidi_rlo(text: str) -> str:
    return f"{_RLO}{text}{_PDF}"


def _whitespace_break(text: str) -> str:
    return " ".join(text)


@dataclass(frozen=True)
class Transform:
    """A named, deterministic obfuscation transform."""

    name: str
    category: str  # "encoding" | "unicode" | "structural"
    apply: Callable[[str], str]
    description: str
    # True  -> NOT recovered by Fulcrum's base64/hex keyword rescan (evasive).
    # False -> recovered by the rescan (a control proving the rescan fires).
    evades_rescan: bool


_TRANSFORMS: Dict[str, Transform] = {
    t.name: t
    for t in [
        Transform("base64", "encoding", _base64,
                  "Standard Base64. Control: Fulcrum's rescan decodes and re-flags it.", False),
        Transform("hex", "encoding", _hex,
                  "Lowercase hex. Control: Fulcrum's rescan decodes and re-flags it.", False),
        Transform("base32", "encoding", _base32,
                  "Base32 — not covered by the base64/hex rescan.", True),
        Transform("base64_urlsafe", "encoding", _base64_urlsafe,
                  "URL-safe Base64 (-_ alphabet) — standard-alphabet rescans miss it.", True),
        Transform("base85", "encoding", _base85,
                  "Base85 (b85/RFC1924) — not covered by the rescan.", True),
        Transform("ascii85", "encoding", _ascii85,
                  "Adobe ASCII85 (<~...~>) — not covered by the rescan.", True),
        Transform("octal_escape", "encoding", _octal_escape,
                  "Per-byte octal backslash escapes (\\NNN) — rescan does not un-escape.", True),
        Transform("rot13", "encoding", _rot13,
                  "ROT13 letter rotation — trivial but rescan-blind.", True),
        Transform("url_encode", "encoding", _url,
                  "Percent-encoding of every byte.", True),
        Transform("url_double_encode", "encoding", _url_double,
                  "Double percent-encoding (single-decode defenders miss it).", True),
        Transform("html_decimal_entities", "encoding", _html_decimal,
                  "HTML decimal numeric character references (&#NNN;).", True),
        Transform("morse", "encoding", _morse,
                  "International Morse code.", True),
        Transform("gzip_base64", "encoding", _gzip_b64,
                  "gzip-compressed then Base64 (multi-stage decode needed).", True),
        Transform("gzip_base32", "encoding", _gzip_b32,
                  "gzip-compressed then Base32 (multi-stage + non-standard alphabet).", True),
        Transform("homoglyph", "unicode", _homoglyph,
                  "Latin->Cyrillic/Greek visual confusables.", True),
        Transform("zero_width", "unicode", _zero_width,
                  "Zero-width spaces interspersed between characters.", True),
        Transform("fullwidth", "unicode", _fullwidth,
                  "Fullwidth (CJK-form) ASCII characters.", True),
        Transform("leetspeak", "unicode", _leetspeak,
                  "Leetspeak digit substitution (a->4, e->3, ...).", True),
        Transform("bidi_rlo", "structural", _bidi_rlo,
                  "Bidirectional RTL-override wrapping.", True),
        Transform("whitespace_break", "structural", _whitespace_break,
                  "Single space inserted between every character.", True),
    ]
}


def get_transform(name: str) -> Transform:
    """Return the :class:`Transform` registered under ``name``."""
    try:
        return _TRANSFORMS[name]
    except KeyError:
        raise KeyError(
            f"Unknown transform: {name!r}. Known: {sorted(_TRANSFORMS)}"
        ) from None


def list_transforms() -> List[Transform]:
    """All registered transforms, in declaration order."""
    return list(_TRANSFORMS.values())


def transform_names() -> List[str]:
    """All registered transform names."""
    return list(_TRANSFORMS.keys())


def apply_chain(text: str, names: List[str]) -> str:
    """Apply transforms left-to-right, enabling multi-layer nesting.

    ``apply_chain("x", ["base64", "base64"])`` double-encodes ``x``.
    An empty chain returns ``text`` unchanged.
    """
    out = text
    for name in names:
        out = get_transform(name).apply(out)
    return out
