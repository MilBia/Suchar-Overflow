"""Unit tests for the fill_translations management command's pure validation logic."""

from unittest.mock import MagicMock

import pytest

from suchar_overflow.suchary.management.commands.fill_translations import Command
from suchar_overflow.suchary.management.commands.fill_translations import (
    _has_format_specifier_corruption,
)
from suchar_overflow.suchary.management.commands.fill_translations import (
    _has_markdown_html_corruption,
)
from suchar_overflow.suchary.management.commands.fill_translations import (
    _has_multiple_alternatives,
)
from suchar_overflow.suchary.management.commands.fill_translations import (
    _is_translategemma,
)
from suchar_overflow.suchary.management.commands.fill_translations import (
    _looks_like_hallucination,
)

# ---------------------------------------------------------------------------
# _is_translategemma
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("translategemma", True),
        ("TranslateGemma-9B-GGUF", True),
        ("gpt-4o-mini", False),
        ("llama3", False),
    ],
)
def test_is_translategemma(model, expected):
    assert _is_translategemma(model) is expected


# ---------------------------------------------------------------------------
# _looks_like_hallucination
# ---------------------------------------------------------------------------


def test_looks_like_hallucination_short_response_is_fine():
    assert _looks_like_hallucination("Home", "Strona główna") is False


def test_looks_like_hallucination_absolute_length_cap():
    """A response over 500 chars is a hallucination regardless of msgid length."""
    assert _looks_like_hallucination("Home", "x" * 501) is True


def test_looks_like_hallucination_ratio_only_applies_above_min_msgid_length():
    """Short msgids (<20 chars) are exempt from the length-ratio check."""
    short_msgid = "Cancel"  # 6 chars, below _MIN_MSGID_FOR_RATIO (20)
    response = "x" * (len(short_msgid) * 4 + 1)
    assert _looks_like_hallucination(short_msgid, response) is False


def test_looks_like_hallucination_ratio_exceeded_on_long_msgid():
    long_msgid = "x" * 25  # >= _MIN_MSGID_FOR_RATIO
    response = "y" * (len(long_msgid) * 4 + 1)
    assert _looks_like_hallucination(long_msgid, response) is True


def test_looks_like_hallucination_ratio_within_bounds_on_long_msgid():
    long_msgid = "x" * 25
    response = "y" * (len(long_msgid) * 4)
    assert _looks_like_hallucination(long_msgid, response) is False


# ---------------------------------------------------------------------------
# _has_multiple_alternatives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        "Tak / Nie",
        "Tak | Nie",
        "Tak OR Nie",
        "Tak LUB Nie",
        "Tak lub Nie",
        "Ten/Ta/To",
    ],
)
def test_has_multiple_alternatives_detects_separators(response):
    assert _has_multiple_alternatives(response) is True


def test_has_multiple_alternatives_plain_text_is_fine():
    assert _has_multiple_alternatives("Zapisz zmiany") is False


def test_has_multiple_alternatives_detects_unspaced_slash_between_words():
    assert _has_multiple_alternatives("OK/Cancel workflow") is True


# ---------------------------------------------------------------------------
# _has_markdown_html_corruption
# ---------------------------------------------------------------------------


def test_has_markdown_html_corruption_true_when_strong_becomes_markdown():
    msgid = "Click <strong>here</strong> to continue"
    response = "Kliknij **tutaj**, aby kontynuować"
    assert _has_markdown_html_corruption(msgid, response) is True


def test_has_markdown_html_corruption_false_when_tag_preserved():
    msgid = "Click <strong>here</strong> to continue"
    response = "Kliknij <strong>tutaj</strong>, aby kontynuować"
    assert _has_markdown_html_corruption(msgid, response) is False


def test_has_markdown_html_corruption_false_when_msgid_has_no_relevant_tags():
    msgid = "Save changes"
    response = "**Zapisz zmiany**"
    assert _has_markdown_html_corruption(msgid, response) is False


def test_has_markdown_html_corruption_detects_em_tag_too():
    msgid = "This is <em>important</em>"
    response = "To jest **ważne**"
    assert _has_markdown_html_corruption(msgid, response) is True


# ---------------------------------------------------------------------------
# _has_format_specifier_corruption
# ---------------------------------------------------------------------------


def test_has_format_specifier_corruption_false_when_no_specifiers():
    assert _has_format_specifier_corruption("Home", "Strona główna") is False


def test_has_format_specifier_corruption_false_when_preserved():
    msgid = "Welcome, %(name)s!"
    response = "Witaj, %(name)s!"
    assert _has_format_specifier_corruption(msgid, response) is False


def test_has_format_specifier_corruption_true_when_space_injected():
    msgid = "Welcome, %(name)s!"
    response = "Witaj, % (name)s!"
    assert _has_format_specifier_corruption(msgid, response) is True


def test_has_format_specifier_corruption_true_when_specifier_dropped():
    msgid = "%(count)s items, %(total)s total"
    response = "%(count)s elementów"
    assert _has_format_specifier_corruption(msgid, response) is True


# ---------------------------------------------------------------------------
# Command._translate_via_httpx / Command._translate_via_openai
# ---------------------------------------------------------------------------


def test_translate_via_httpx_returns_stripped_text():
    cmd = Command()
    client = MagicMock()
    client.post.return_value.json.return_value = {
        "choices": [{"text": "  Strona główna  "}],
    }

    result = cmd._translate_via_httpx(  # noqa: SLF001
        client,
        "translategemma",
        "Home",
        "en",
        "pl",
        "Polish",
    )

    assert result == "Strona główna"
    client.post.assert_called_once()
    client.post.return_value.raise_for_status.assert_called_once()


def test_translate_via_openai_returns_stripped_content():
    cmd = Command()
    client = MagicMock()
    message = MagicMock()
    message.content = "  Strona główna  "
    client.chat.completions.create.return_value.choices = [MagicMock(message=message)]

    result = cmd._translate_via_openai(  # noqa: SLF001
        client,
        "gpt-4o-mini",
        "Home",
        "en",
        "Polish",
        "",
    )

    assert result == "Strona główna"
    client.chat.completions.create.assert_called_once()


def test_translate_via_openai_returns_none_when_content_missing():
    cmd = Command()
    client = MagicMock()
    message = MagicMock()
    message.content = None
    client.chat.completions.create.return_value.choices = [MagicMock(message=message)]

    result = cmd._translate_via_openai(  # noqa: SLF001
        client,
        "gpt-4o-mini",
        "Home",
        "en",
        "Polish",
        "",
    )

    assert result is None


# ---------------------------------------------------------------------------
# Command._validate_result
# ---------------------------------------------------------------------------


def test_validate_result_passes_through_clean_translation():
    cmd = Command()
    assert cmd._validate_result("Home", "Strona główna") == "Strona główna"  # noqa: SLF001


def test_validate_result_rejects_hallucination():
    cmd = Command()
    assert cmd._validate_result("Home", "x" * 501) is None  # noqa: SLF001


def test_validate_result_rejects_multiple_alternatives():
    cmd = Command()
    assert cmd._validate_result("Yes", "Tak / Nie") is None  # noqa: SLF001


def test_validate_result_returns_none_unchanged():
    cmd = Command()
    assert cmd._validate_result("Home", None) is None  # noqa: SLF001
