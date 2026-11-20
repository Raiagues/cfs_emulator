"""Read the operator's last explicit target selection."""
import json
from pathlib import Path

from journey import TARGETS


def selected_target(root):
    try:
        selected = json.loads((Path(root) / "hardware/.runtime/target.json").read_text())["target"]
    except FileNotFoundError:
        return None
    if selected not in TARGETS:
        raise ValueError("Invalid saved execution target")
    return selected
