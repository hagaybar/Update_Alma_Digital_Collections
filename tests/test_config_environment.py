"""A config must name its environment explicitly; a missing or unknown value
is refused instead of silently meaning PRODUCTION. No network."""

import pytest

from collection_sync import ConfigManager

TASKS = """
tasks:
  t1:
    collection_id: "1"
    report_paths: ["/a"]
"""


def _cfg(tmp_path, text):
    p = tmp_path / "config.yml"
    p.write_text(text)
    return str(p)


def test_missing_environment_is_refused(tmp_path):
    with pytest.raises(ValueError, match="environment"):
        ConfigManager(_cfg(tmp_path, TASKS))


def test_misspelled_environment_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="environment"):
        ConfigManager(_cfg(tmp_path, "enviroment: SANDBOX\n" + TASKS))


def test_unknown_environment_value_is_refused(tmp_path):
    with pytest.raises(ValueError, match="environment"):
        ConfigManager(_cfg(tmp_path, "environment: PROD\n" + TASKS))


def test_empty_environment_is_refused(tmp_path):
    with pytest.raises(ValueError, match="environment"):
        ConfigManager(_cfg(tmp_path, "environment:\n" + TASKS))


@pytest.mark.parametrize("value", ["SANDBOX", "PRODUCTION"])
def test_explicit_environment_is_accepted(tmp_path, value):
    cm = ConfigManager(_cfg(tmp_path, f"environment: {value}\n" + TASKS))
    assert cm.get_environment() == value
