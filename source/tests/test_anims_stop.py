"""Animation stop-key validation tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import anims  # noqa: E402
from app.anims_stop import (  # noqa: E402
    VAL_BAD_STOP_KEY,
    VAL_EMPTY_STOP_KEY,
    VAL_UNKNOWN_STOP_KEY,
    stop_key_problem,
)


def test_valid_stop_keys():
    assert stop_key_problem("F") == ""
    assert stop_key_problem("space") == ""
    assert stop_key_problem("Ctrl+F12") == ""


def test_missing_or_ambiguous_stop_key():
    assert stop_key_problem("") == VAL_EMPTY_STOP_KEY
    assert stop_key_problem("ctrl+alt") == VAL_BAD_STOP_KEY
    assert stop_key_problem("ctrl+a+b") == VAL_BAD_STOP_KEY


def test_unsupported_stop_key():
    assert stop_key_problem("escape") == VAL_UNKNOWN_STOP_KEY
    assert stop_key_problem("f25") == VAL_UNKNOWN_STOP_KEY


def test_legacy_anims_exports_stay_available():
    assert anims.stop_key_problem is stop_key_problem
