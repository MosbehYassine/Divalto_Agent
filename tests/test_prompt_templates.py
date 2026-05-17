import os
import sys

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from prompt_templates import load_prompt_template  # noqa: E402


def test_load_phase3_prompt_template():
    text = load_prompt_template("phase3_system")
    assert "{actions}" in text


def test_load_rag_suffix_template():
    text = load_prompt_template("rag_suffix")
    assert "{context}" in text
