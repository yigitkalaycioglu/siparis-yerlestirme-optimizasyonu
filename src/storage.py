from __future__ import annotations

import json
from pathlib import Path

from src.engine import create_initial_state
from src.models import AlgorithmConfig, AppState, WarehouseConfig, from_dict, to_dict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> AppState:
    ensure_data_dir()
    if not STATE_FILE.exists():
        return create_initial_state(WarehouseConfig(), AlgorithmConfig())

    with STATE_FILE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    return from_dict(payload)


def save_state(state: AppState) -> None:
    ensure_data_dir()
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(to_dict(state), f, indent=2, ensure_ascii=False)
