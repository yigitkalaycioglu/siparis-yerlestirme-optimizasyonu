"""Print a few shelves with their computed 3D positions using the live layout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage import load_state
from src.visualization import DEFAULT_LAYOUT

state = load_state()
layout = DEFAULT_LAYOUT


def shelf_pos(s):
    x = (s.aisle_index - 1) * layout["aisle_pitch"]
    z = (s.row_index - 1) * layout["row_pitch"] + (-layout["side_gap"] if s.side_index == 1 else layout["side_gap"])
    y = (s.y_index - 1) * layout["level_pitch"]
    return (x, y, z)


print("total_shelves=", len(state.shelves))
indices = [0, 1, 10, 100, 1000, 5000, 10000, len(state.shelves) - 1]
for i in indices:
    if i >= len(state.shelves):
        continue
    s = state.shelves[i]
    print(i, s.shelf_id, "pos", shelf_pos(s), "util", round(s.utilization, 3), "placements", len(s.placements))
