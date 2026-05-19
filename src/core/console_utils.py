"""Safe console output on Windows (cp1252) when queries contain Unicode spaces or accents."""

from __future__ import annotations

import sys
import unicodedata


def normalize_user_text(text: str) -> str:
    """Normalize exotic Unicode spaces (e.g. U+202F in French numbers) for parsing."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text.strip())
    for ch in ("\u202f", "\u00a0", "\u2009", "\u2007", "\u2060"):
        t = t.replace(ch, " ")
    return t


def safe_print(*values: object, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
    """Print without raising UnicodeEncodeError on Windows consoles."""
    text = sep.join(str(v) for v in values) + end
    try:
        print(text, end="", flush=flush)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(text.encode(enc, errors="replace"))
        if flush:
            sys.stdout.flush()
