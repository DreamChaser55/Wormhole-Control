import json

import pytest

from app_preferences import AppPreferences, TurnSummaryMode, load_preferences, save_preferences
from utils import user_data_path


def test_missing_preferences_do_not_create_file():
    assert load_preferences() == AppPreferences()
    assert not (user_data_path() / "preferences.json").exists()


@pytest.mark.parametrize("mode", list(TurnSummaryMode))
def test_round_trip(mode):
    save_preferences(AppPreferences(mode))
    assert load_preferences() == AppPreferences(mode)


@pytest.mark.parametrize("payload", ['broken', '[]', '{"turn_summary_mode": "bad"}', '{"turn_summary_mode": null}'])
def test_invalid_preferences_use_default(payload, caplog):
    (user_data_path() / "preferences.json").write_text(payload)
    assert load_preferences() == AppPreferences()
    assert "Could not load" in caplog.text


def test_unreadable_preferences_use_default(caplog):
    (user_data_path() / "preferences.json").mkdir()
    assert load_preferences() == AppPreferences()
    assert "Could not load" in caplog.text


def test_failed_atomic_write_preserves_file(monkeypatch):
    save_preferences(AppPreferences(TurnSummaryMode.ALWAYS))
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("app_preferences.os.replace", fail)
    with pytest.raises(OSError):
        save_preferences(AppPreferences(TurnSummaryMode.NEVER))
    assert json.loads((user_data_path() / "preferences.json").read_text())["turn_summary_mode"] == "always"
    assert not list(user_data_path().glob("*.tmp"))
