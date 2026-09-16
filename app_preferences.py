"""Application preferences, stored independently of campaigns."""
from dataclasses import dataclass
from enum import Enum
import json
import logging
import os
from pathlib import Path
import tempfile

from utils import user_data_path

logger = logging.getLogger(__name__)


class TurnSummaryMode(str, Enum):
    ALWAYS = "always"
    AUTOMATIC = "automatic"
    NEVER = "never"


@dataclass(frozen=True)
class AppPreferences:
    turn_summary_mode: TurnSummaryMode = TurnSummaryMode.AUTOMATIC


def load_preferences() -> AppPreferences:
    try:
        payload = json.loads((user_data_path() / "preferences.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Preferences must be an object")
        return AppPreferences(TurnSummaryMode(payload.get("turn_summary_mode", "automatic")))
    except FileNotFoundError:
        return AppPreferences()
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Could not load application preferences: %s", exc)
        return AppPreferences()


def save_preferences(preferences: AppPreferences) -> None:
    """Publish atomically; propagate failures so the UI can retain its old choice."""
    payload = json.dumps({"turn_summary_mode": TurnSummaryMode(preferences.turn_summary_mode).value}, indent=2)
    target = user_data_path() / "preferences.json"
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary preferences file: %s", temporary)
