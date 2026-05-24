"""Generate the 3D scene payload (without filters) to data/debug_sim_payload.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage import load_state
from src.visualization import build_scene_payload

OUT = Path(__file__).resolve().parent.parent / "data" / "debug_sim_payload.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

state = load_state()
payload = build_scene_payload(state)

with OUT.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print("Wrote:", OUT)
print("stats:", payload["stats"])
print("first_shelves:", [s["shelf_id"] for s in payload["shelves"][:5]])
