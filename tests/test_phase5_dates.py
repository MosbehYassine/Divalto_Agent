import os
import sys
from datetime import date, timedelta

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import phase5_dates  # noqa: E402
import pytest  # noqa: E402

from phase5_dates import (  # noqa: E402
    describe_window_fr,
    infer_date_bounds_from_question,
    paired_prior_window,
)


def test_infer_last_n_days(monkeypatch):
    frozen = date(2026, 5, 15)

    class _FixedDate:
        @staticmethod
        def today():
            return frozen

    monkeypatch.setattr(phase5_dates, "date", _FixedDate)

    start, end = infer_date_bounds_from_question("Ventes sur les 30 derniers jours")
    assert end == frozen.strftime("%Y%m%d")
    expected_start = (frozen - timedelta(days=30)).strftime("%Y%m%d")
    assert start == expected_start


def test_paired_prior_window_equal_length():
    cur_s, cur_e = "20260110", "20260119"
    prev_s, prev_e = paired_prior_window(cur_s, cur_e)
    assert prev_e == "20260109"
    assert prev_s == "20251231"


def test_describe_window_fr_full_range():
    txt = describe_window_fr("19000101", "99991231")
    assert "période" in txt.lower()


def test_infer_ce_mois_contains_first_of_month(monkeypatch):
    frozen = date(2026, 3, 14)

    class _FixedDate:
        @staticmethod
        def today():
            return frozen

    monkeypatch.setattr(phase5_dates, "date", _FixedDate)
    start, end = infer_date_bounds_from_question("Ventes ce mois")
    assert start == "20260301"
    assert end == "20260314"
