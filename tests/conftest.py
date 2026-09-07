"""Keep tests and their child processes away from the real custom-design library."""
import atexit
import os
from pathlib import Path
import tempfile


_user_data = tempfile.TemporaryDirectory(prefix="wormhole-test-user-data-")
atexit.register(_user_data.cleanup)
os.environ["WORMHOLE_USER_DATA_DIR"] = _user_data.name
Path(_user_data.name, "custom_unit_templates.json").write_text("{}", encoding="utf-8")
