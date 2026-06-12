import json
import os
from constants import HullSize

def _load_templates() -> dict:
    file_path = os.path.join(os.path.dirname(__file__), "data", "unit_templates.json")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, template in data.items():
        if "hull_size" in template:
            template["hull_size"] = HullSize[template["hull_size"]]
    return data

UNIT_TEMPLATES = _load_templates()
