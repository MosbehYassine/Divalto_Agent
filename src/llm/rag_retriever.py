"""
rag_retriever.py
================
Lightweight local RAG retriever (no external dependencies).
Builds lexical chunks from project docs and returns top-k context snippets.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.settings import RAG_CHUNK_SIZE, RAG_DOCS_DIR, RAG_ENABLED, RAG_FILE_EXTENSIONS, RAG_TOP_K


@dataclass(frozen=True)
class Chunk:
    source: str
    text: str
    tokens: tuple[str, ...]


_INDEX_CACHE: dict[str, Any] = {"root": None, "signature": None, "chunks": []}


def _tokenize(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()) if tok]


def _split_chunks(text: str, chunk_size: int) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    if len(clean) <= chunk_size:
        return [clean]
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _docs_root() -> Path:
    if RAG_DOCS_DIR.strip():
        return Path(RAG_DOCS_DIR).resolve()
    # default to project docs folder
    return (Path(__file__).resolve().parents[2] / "docs").resolve()


def _scan_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    allowed = {
        ext.strip().lower()
        for ext in RAG_FILE_EXTENSIONS.split(",")
        if ext.strip()
    }
    return sorted(
        [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed],
        key=lambda p: str(p).lower(),
    )


def _signature(paths: list[Path]) -> str:
    items = []
    for p in paths:
        stat = p.stat()
        items.append(f"{p}:{int(stat.st_mtime)}:{stat.st_size}")
    return "|".join(items)


def build_index() -> list[Chunk]:
    root = _docs_root()
    files = _scan_files(root)
    sig = _signature(files)
    if (
        _INDEX_CACHE["root"] == str(root)
        and _INDEX_CACHE["signature"] == sig
        and _INDEX_CACHE["chunks"]
    ):
        return _INDEX_CACHE["chunks"]

    chunks: list[Chunk] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for chunk_text in _split_chunks(content, RAG_CHUNK_SIZE):
            tokens = tuple(_tokenize(chunk_text))
            if tokens:
                chunks.append(Chunk(source=str(path), text=chunk_text, tokens=tokens))

    _INDEX_CACHE["root"] = str(root)
    _INDEX_CACHE["signature"] = sig
    _INDEX_CACHE["chunks"] = chunks
    return chunks


def _idf_map(chunks: list[Chunk]) -> dict[str, float]:
    df: dict[str, int] = {}
    for c in chunks:
        seen = set(c.tokens)
        for tok in seen:
            df[tok] = df.get(tok, 0) + 1
    n_docs = max(len(chunks), 1)
    return {tok: math.log((1 + n_docs) / (1 + freq)) + 1.0 for tok, freq in df.items()}


def retrieve_context(query: str, top_k: int | None = None) -> dict[str, Any]:
    if not RAG_ENABLED:
        return {"enabled": False, "snippets": [], "context": ""}

    chunks = build_index()
    if not chunks:
        return {"enabled": True, "snippets": [], "context": ""}

    q_tokens = _tokenize(query)
    if not q_tokens:
        return {"enabled": True, "snippets": [], "context": ""}

    idf = _idf_map(chunks)
    scored: list[tuple[float, Chunk]] = []
    q_set = set(q_tokens)
    for c in chunks:
        tf: dict[str, int] = {}
        for t in c.tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for tok in q_set:
            if tok in tf:
                score += (1.0 + math.log(tf[tok])) * idf.get(tok, 1.0)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    k = top_k if top_k is not None else RAG_TOP_K
    top = scored[: max(k, 1)]

    snippets = [
        {
            "source": item.source,
            "score": round(score, 4),
            "text": item.text,
        }
        for score, item in top
    ]
    context = "\n\n".join(
        [f"[source: {s['source']}]\n{s['text']}" for s in snippets]
    )
    return {"enabled": True, "snippets": snippets, "context": context}

