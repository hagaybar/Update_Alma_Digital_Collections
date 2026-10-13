"""Tests for RedactingFormatter: secrets must never reach console or log file."""

import logging
import sys

import pytest

from collection_sync import RedactingFormatter

FAKE_SECRET = "PLACEHOLDER-SECRET-VALUE"


def render(msg, *args, exc_info=None):
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, msg, args, exc_info)
    return RedactingFormatter("%(message)s").format(record)


@pytest.mark.parametrize("text", [
    f"Authorization: apikey {FAKE_SECRET}",
    f"headers={{'Authorization': 'apikey {FAKE_SECRET}'}}",
    f"GET https://api-eu.hosted.exlibrisgroup.com/almaws/v1/bibs?apikey={FAKE_SECRET}&limit=1",
    f"api_key={FAKE_SECRET}",
    f"token: {FAKE_SECRET}",
])
def test_labelled_secrets_are_redacted(text):
    out = render(text)
    assert FAKE_SECRET not in out
    assert "REDACTED" in out


@pytest.mark.parametrize("var", ["ALMA_PROD_API_KEY", "ALMA_SB_API_KEY"])
def test_env_key_value_redacted_anywhere(monkeypatch, var):
    monkeypatch.setenv(var, FAKE_SECRET)
    out = render("unlabelled: %s", FAKE_SECRET)
    assert FAKE_SECRET not in out


def test_traceback_is_redacted():
    try:
        raise RuntimeError(f"failed url ?apikey={FAKE_SECRET}")
    except RuntimeError:
        out = render("Unexpected error", exc_info=sys.exc_info())
    assert "Traceback" in out
    assert FAKE_SECRET not in out


def test_ordinary_messages_unchanged():
    msg = "Found 192 MMS IDs in report /shared/Tel Aviv University/Reports/X for 9934084405904146"
    assert render(msg) == msg
