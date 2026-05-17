"""
phase5_dates.py — Relative windows for analytic queries → yyyymmdd strings.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta


def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def infer_date_bounds_from_question(user_question: str) -> tuple[str, str]:
    """
    Return (startDate, endDate) as yyyymmdd from French business phrasing.

    Fallback is the broad ERP default window covering all history.
    """
    q_raw = user_question.strip()
    q = q_raw.lower()
    today = date.today()

    m_days = re.search(r"(\d+)\s*(derniers?|dernières?)\s*jours?", q)
    if m_days:
        n = max(1, int(m_days.group(1)))
        start = today - timedelta(days=n)
        return _yyyymmdd(start), _yyyymmdd(today)

    if "aujourd'hui" in q or "today" in q:
        return _yyyymmdd(today), _yyyymmdd(today)

    if "mois dernier" in q or "mois précédent" in q or " dernier mois" in q:
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start_prev = last_prev.replace(day=1)
        return _yyyymmdd(start_prev), _yyyymmdd(last_prev)

    if "ce mois" in q or "mois en cours" in q:
        start = today.replace(day=1)
        return _yyyymmdd(start), _yyyymmdd(today)

    if " cette semaine" in q or "cette semaine" == q.strip() or re.search(r"\bcette\s+semaine\b", q):
        start = today - timedelta(days=today.weekday())
        return _yyyymmdd(start), _yyyymmdd(today)

    if ("semaine dernière" in q or "semaine passée" in q) or re.search(r"\bben\s*dernière\s*semaine\b", q):
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return _yyyymmdd(start), _yyyymmdd(end)

    m_year_month = re.search(
        r"\b(en|pour|durant)?\s*([a-zûéèàâôîï]+)\s+(\d{4})\b",
        q,
    )
    if m_year_month:
        month_tokens = {
            "janvier": 1,
            "février": 2,
            "fevrier": 2,
            "mars": 3,
            "avril": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7,
            "août": 8,
            "aout": 8,
            "septembre": 9,
            "octobre": 10,
            "novembre": 11,
            "décembre": 12,
            "decembre": 12,
        }
        month_name = m_year_month.group(2).lower()
        year = int(m_year_month.group(3))
        month = month_tokens.get(month_name)
        if month:
            last_day = calendar.monthrange(year, month)[1]
            start = date(year, month, 1)
            end = date(year, month, last_day)
            return _yyyymmdd(start), _yyyymmdd(end)

    return "19000101", "99991231"


def paired_prior_window(start_date: str, end_date: str) -> tuple[str, str]:
    """
    Given a current window [start,end] inclusive, returns the immediately
    preceding window of identical length as (yyyymmdd, yyyymmdd).
    """
    start_norm = normalize_yyyymmdd(start_date)
    end_norm = normalize_yyyymmdd(end_date)
    if not start_norm or not end_norm:
        return "", ""
    s = parse_yyyymmdd(start_norm)
    e = parse_yyyymmdd(end_norm)
    if s is None or e is None or e < s:
        return "", ""
    length_days = (e - s).days + 1
    prev_end = s - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length_days - 1)
    return _yyyymmdd(prev_start), _yyyymmdd(prev_end)


def normalize_yyyymmdd(value: str) -> str:
    raw = (value or "").strip()
    return raw if len(raw) == 8 and raw.isdigit() else ""


def parse_yyyymmdd(raw: str) -> date | None:
    normalized = normalize_yyyymmdd(raw)
    if not normalized:
        return None
    y, mo, da = int(normalized[0:4]), int(normalized[4:6]), int(normalized[6:8])
    return date(y, mo, da)


def describe_window_fr(start_date: str, end_date: str) -> str:
    if start_date == "19000101" and end_date == "99991231":
        return "toute la période disponible"
    if len(start_date) == 8 and len(end_date) == 8:
        ys, ms, ds = int(start_date[0:4]), int(start_date[4:6]), int(start_date[6:8])
        ye, me, de = int(end_date[0:4]), int(end_date[4:6]), int(end_date[6:8])
        return f"du {ds:02d}/{ms:02d}/{ys} au {de:02d}/{me:02d}/{ye}"
    return f"du {start_date} au {end_date}"
