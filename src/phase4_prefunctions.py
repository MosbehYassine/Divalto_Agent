"""
phase4_prefunctions.py
======================
Reusable pre-processing helpers for Phase 4 reliability.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentScore:
    tool_name: str
    score: int
    matched_terms: tuple[str, ...]


def normalize_text(text: str) -> str:
    """
    Normalize user text for deterministic matching:
    - lowercase
    - remove accents
    - collapse repeated spaces
    """
    lowered = text.lower().strip()
    no_accents = "".join(
        ch for ch in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", no_accents)


def extract_customer(text: str) -> str:
    match = re.search(r"\bCLI-\d{3,6}\b", text.upper())
    return match.group(0) if match else ""


def extract_reference(text: str) -> str:
    match = re.search(r"\b[A-Z]{2,6}\d{3,6}\b", text.upper())
    return match.group(0) if match else ""


def extract_family(text: str) -> str:
    match = re.search(r"famille\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def detect_region(text: str) -> str:
    upper = text.upper()
    for region in ("NORD", "SUD", "EST", "OUEST", "CENTRE"):
        if region in upper:
            return region
    return ""


def compute_intent_scores(normalized_text: str) -> dict[str, IntentScore]:
    """
    Compute simple weighted intent scores by tool.
    """
    weighted_terms: dict[str, tuple[tuple[str, int], ...]] = {
        "facturation": (("facturation", 3), ("facture", 3), ("invoice", 2)),
        "consultation_ventes": (("vente", 3), ("ventes", 3), ("chiffre", 2), ("ca", 2)),
        "articles": (("article", 3), ("catalogue", 2), ("famille", 2), ("reference", 1)),
        "clients": (("client", 3), ("clients", 3), ("region", 1), ("segment", 1)),
        "stocks": (("stock", 4), ("disponible", 2), ("entrepot", 1), ("depot", 1)),
        "indicateurs_analytiques": (
            ("indicateur", 4),
            ("analytique", 3),
            ("kpi", 3),
            ("tendance", 2),
        ),
    }
    scores: dict[str, IntentScore] = {}
    for tool_name, terms in weighted_terms.items():
        score = 0
        matched: list[str] = []
        for term, weight in terms:
            if term in normalized_text:
                score += weight
                matched.append(term)
        scores[tool_name] = IntentScore(tool_name=tool_name, score=score, matched_terms=tuple(matched))
    return scores


def score_to_confidence(best_score: int) -> str:
    if best_score >= 5:
        return "high"
    if best_score >= 2:
        return "medium"
    return "low"


_LOOKUP_HINT_STOPWORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
        "d",
        "et",
        "ou",
        "en",
        "sur",
        "pour",
        "avec",
        "sans",
        "qui",
        "que",
        "quoi",
        "dont",
        "est",
        "son",
        "sa",
        "ses",
        "ce",
        "cette",
        "ces",
        "c",
        "il",
        "elle",
        "ils",
        "elles",
        "je",
        "tu",
        "nous",
        "vous",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "give",
        "tell",
        "about",
        "what",
        "how",
        "when",
        "where",
        "client",
        "clients",
        "article",
        "articles",
        "produit",
        "produits",
        "information",
        "informations",
        "infos",
        "detail",
        "details",
        "voir",
        "connaitre",
        "connaître",
    }
)


def _cleanup_lookup_hint(fragment: str) -> str:
    s = (fragment or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    lowered = s.lower()
    for prefix in ("le ", "la ", "les ", "l'", "d'", "de ", "du ", "des ", "un ", "une "):
        if lowered.startswith(prefix):
            s = s[len(prefix) :].strip()
            lowered = s.lower()
    return s.strip(" \t\r\n-*•")


def _lookup_hint_is_noisy(hint: str) -> bool:
    low = hint.lower()
    noise_markers = (
        "plus ",
        " moins ",
        " tous ",
        " toutes ",
        "liste ",
        "class",
        "ventes",
        "facturation",
        "combien",
        "total",
        "stock ",
        "dépôt",
        "depot",
    )
    return any(m in low for m in noise_markers)


def extract_lookup_hint(text: str) -> str:
    """
    Pull a short string usable as SQLite LIKE filter for client/article lookups.
    Prefer CLI-xxx codes, then quoted phrases, then patterns such as « client Dupont ».
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    cli = extract_customer(raw)
    if cli:
        return cli

    ref_code = extract_reference(raw)
    if ref_code:
        return ref_code

    for pattern in (r"«\s*([^»]+?)\s*»", r"[\"]([^\"]+)[\"]", r"'([^']+)'"):
        m = re.search(pattern, raw)
        if m:
            hint = _cleanup_lookup_hint(m.group(1))
            if len(hint) >= 2 and not _lookup_hint_is_noisy(hint):
                return hint

    patterns = [
        r"(?:infos?|informations?)\s+sur\s+(?:le\s+)?(?:client|clients)\s+(.+?)(?=\s*[?!.,;]|$)",
        r"(?:à\s+propos\s+(?:du|de\s+la)\s+cliente?\s+)(.+?)(?=\s*[?!.,;]|$)",
        r"\b(?:client|clients)\s+(?!ventes?\b)(.+?)(?=\s*[?!.,;]|$)",
        r"\b(?:article|produit|référence|réf)\s+(.+?)(?=\s*[?!.,;]|$)",
        r"(?:nommée?|nommé|appelée?|appelé)\s+(.+?)(?=\s*[?!.,;]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            hint = _cleanup_lookup_hint(m.group(1))
            if len(hint) >= 2 and not _lookup_hint_is_noisy(hint):
                return hint

    return ""


def focus_terms_for_answer(text: str) -> list[str]:
    """Tokens from the user question useful for matching catalog rows (clients, articles)."""
    normalized = normalize_text(text or "")
    return [
        t
        for t in re.findall(r"[a-zàâäéèêëïîôùûçñ0-9]{2,}", normalized)
        if t not in _LOOKUP_HINT_STOPWORDS
    ]
