from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class WarehouseConfig:
    aisles: int = 6
    sides_per_aisle: int = 2
    rows_per_side: int = 180
    shelves_per_row: int = 9
    shelf_width_cm: int = 360
    shelf_depth_cm: int = 250
    shelf_height_cm: int = 220
    clearance_width_cm: int = 1
    clearance_depth_cm: int = 1
    smallest_pallet_width_cm: int = 80
    smallest_pallet_depth_cm: int = 120


@dataclass
class ShelfTypeConfig:
    label: str
    shelf_width_cm: int = 360
    shelf_depth_cm: int = 250
    shelf_height_cm: int = 220
    clearance_width_cm: int = 1
    clearance_depth_cm: int = 1
    smallest_pallet_width_cm: int = 80
    smallest_pallet_depth_cm: int = 120


@dataclass
class ShelfTypeLayout:
    label: str
    sequence: int = 1
    block_size: int = 1


@dataclass
class AlgorithmConfig:
    allow_rotation: bool = True
    cluster_same_company: bool = True
    cluster_same_ship_date: bool = True
    cluster_same_destination: bool = True
    ship_date_cluster_days: int = 2
    due_date_priority_days: int = 7
    weight_fill_efficiency: float = 0.45
    weight_travel_distance: float = 0.25
    weight_company_cluster: float = 0.15
    weight_date_cluster: float = 0.1
    weight_destination_cluster: float = 0.12
    weight_due_date_priority: float = 0.08
    weight_storage_duration: float = 0.08
    weight_balance: float = 0.05
    top_k_suggestions: int = 5
    min_fragment_cm2: int = 400


@dataclass
class PackagePreset:
    label: str
    product_width_cm: int
    product_depth_cm: int
    pallet_width_cm: int
    pallet_depth_cm: int


@dataclass
class Order:
    order_id: str
    product_width_cm: int
    product_depth_cm: int
    pallet_width_cm: int
    pallet_depth_cm: int
    company: str
    ship_date: str
    due_date: str = ""
    entry_date: str = field(default_factory=lambda: date.today().isoformat())
    destination: str = ""
    max_storage_days: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def requested_width_cm(self) -> int:
        return max(self.product_width_cm, self.pallet_width_cm)

    @property
    def requested_depth_cm(self) -> int:
        return max(self.product_depth_cm, self.pallet_depth_cm)

    @property
    def effective_due_date(self) -> str:
        return self.due_date or self.ship_date

    @property
    def destination_key(self) -> str:
        return (self.destination or self.company or "-").strip()

    @property
    def planned_storage_days(self) -> int:
        try:
            return max(0, (parse_ship_date(self.effective_due_date) - parse_ship_date(self.entry_date)).days)
        except ValueError:
            return 0

    @property
    def storage_pressure(self) -> float:
        if self.max_storage_days <= 0:
            return 0.0
        return min(1.0, self.planned_storage_days / self.max_storage_days)


@dataclass
class Rect:
    x: int
    y: int
    width: int
    depth: int

    @property
    def area(self) -> int:
        return self.width * self.depth


@dataclass
class Placement:
    order_id: str
    company: str
    ship_date: str
    x: int
    y: int
    width: int
    depth: int
    rotated: bool
    due_date: str = ""
    entry_date: str = ""
    destination: str = ""
    max_storage_days: int = 0

    @property
    def area(self) -> int:
        return self.width * self.depth


@dataclass
class ShelfState:
    shelf_id: str
    aisle_index: int
    side_index: int
    row_index: int
    y_index: int
    width_cm: int
    depth_cm: int
    free_rectangles: list[Rect]
    shelf_type: str = "Standart"
    height_cm: int = 220
    placements: list[Placement] = field(default_factory=list)
    manual_full: bool = False

    @property
    def area(self) -> int:
        return self.width_cm * self.depth_cm

    @property
    def used_area(self) -> int:
        return sum(p.area for p in self.placements)

    @property
    def free_area(self) -> int:
        return self.area - self.used_area

    @property
    def utilization(self) -> float:
        if self.area == 0:
            return 1.0
        return self.used_area / self.area


@dataclass
class AppState:
    warehouse_config: WarehouseConfig
    algorithm_config: AlgorithmConfig
    shelves: list[ShelfState]
    shelf_types: list[str] = field(default_factory=list)
    shelf_type_configs: dict[str, ShelfTypeConfig] = field(default_factory=dict)
    shelf_type_layouts: list[ShelfTypeLayout] = field(default_factory=list)
    package_presets: list[PackagePreset] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)


def make_shelf_type_config(label: str, warehouse_config: WarehouseConfig, data: dict[str, Any] | None = None) -> ShelfTypeConfig:
    payload = data or {}
    return ShelfTypeConfig(
        label=label,
        shelf_width_cm=int(payload.get("shelf_width_cm", warehouse_config.shelf_width_cm)),
        shelf_depth_cm=int(payload.get("shelf_depth_cm", warehouse_config.shelf_depth_cm)),
        shelf_height_cm=int(payload.get("shelf_height_cm", warehouse_config.shelf_height_cm)),
        clearance_width_cm=int(payload.get("clearance_width_cm", warehouse_config.clearance_width_cm)),
        clearance_depth_cm=int(payload.get("clearance_depth_cm", warehouse_config.clearance_depth_cm)),
        smallest_pallet_width_cm=int(payload.get("smallest_pallet_width_cm", warehouse_config.smallest_pallet_width_cm)),
        smallest_pallet_depth_cm=int(payload.get("smallest_pallet_depth_cm", warehouse_config.smallest_pallet_depth_cm)),
    )


def make_shelf_type_layout(label: str, data: dict[str, Any] | None = None) -> ShelfTypeLayout:
    payload = data or {}
    return ShelfTypeLayout(
        label=label,
        sequence=int(payload.get("sequence", 1)),
        block_size=max(1, int(payload.get("block_size", 1))),
    )


def _normalize_shelf_type_layouts(raw_layouts: Any) -> dict[str, dict[str, Any]]:
    if isinstance(raw_layouts, dict):
        return {str(label): dict(payload or {}) for label, payload in raw_layouts.items()}

    normalized: dict[str, dict[str, Any]] = {}
    if isinstance(raw_layouts, list):
        for index, item in enumerate(raw_layouts):
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("shelf_type") or f"Layout-{index + 1}")
                normalized[label] = dict(item)
    return normalized


def _dataclass_payload(model: type, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {item.name for item in fields(model)}
    return {key: value for key, value in dict(payload or {}).items() if key in allowed}


def parse_ship_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def to_dict(state: AppState) -> dict[str, Any]:
    return asdict(state)


def from_dict(data: dict[str, Any]) -> AppState:
    warehouse_config = WarehouseConfig(**_dataclass_payload(WarehouseConfig, data.get("warehouse_config", {})))
    algorithm_config = AlgorithmConfig(**_dataclass_payload(AlgorithmConfig, data.get("algorithm_config", {})))
    package_presets = [
        PackagePreset(**_dataclass_payload(PackagePreset, preset_data))
        for preset_data in data.get("package_presets", [])
    ]
    shelf_types = list(data.get("shelf_types", [])) or ["Standart"]
    raw_shelf_type_configs = data.get("shelf_type_configs", {}) or {}
    raw_shelf_type_layouts = _normalize_shelf_type_layouts(data.get("shelf_type_layouts", {}))

    shelf_type_configs = {
        shelf_type: make_shelf_type_config(shelf_type, warehouse_config, raw_shelf_type_configs.get(shelf_type, {}))
        for shelf_type in shelf_types
    }

    for shelf_type, config_data in raw_shelf_type_configs.items():
        if shelf_type not in shelf_type_configs:
            shelf_type_configs[shelf_type] = make_shelf_type_config(shelf_type, warehouse_config, config_data)

    shelf_type_layouts = [
        make_shelf_type_layout(shelf_type, raw_shelf_type_layouts.get(shelf_type, {}))
        for shelf_type in shelf_types
    ]
    layout_known = {layout.label for layout in shelf_type_layouts}
    for shelf_type, layout_data in raw_shelf_type_layouts.items():
        if shelf_type not in layout_known:
            shelf_type_layouts.append(make_shelf_type_layout(shelf_type, layout_data))
    shelf_type_layouts.sort(key=lambda layout: (layout.sequence, layout.label.lower()))

    shelves: list[ShelfState] = []
    for index, item in enumerate(data.get("shelves", [])):
        free_rectangles = [Rect(**r) for r in item.get("free_rectangles", [])]
        placements = [Placement(**_dataclass_payload(Placement, p)) for p in item.get("placements", [])]
        shelf_type = str(item.get("shelf_type") or shelf_types[index % len(shelf_types)]).strip() or shelf_types[0]
        shelf_config = shelf_type_configs.get(shelf_type, make_shelf_type_config(shelf_type, warehouse_config))
        width_cm = int(item.get("width_cm", shelf_config.shelf_width_cm))
        depth_cm = int(item.get("depth_cm", shelf_config.shelf_depth_cm))
        if not free_rectangles:
            free_rectangles = [Rect(x=0, y=0, width=width_cm, depth=depth_cm)]
        shelves.append(
            ShelfState(
                shelf_id=item["shelf_id"],
                aisle_index=item["aisle_index"],
                side_index=item["side_index"],
                row_index=item["row_index"],
                y_index=item["y_index"],
                width_cm=width_cm,
                depth_cm=depth_cm,
                shelf_type=shelf_type,
                height_cm=int(item.get("height_cm", shelf_config.shelf_height_cm)),
                free_rectangles=free_rectangles,
                placements=placements,
                manual_full=item.get("manual_full", False),
            )
        )

    orders = [Order(**_dataclass_payload(Order, order_data)) for order_data in data.get("orders", [])]

    return AppState(
        warehouse_config=warehouse_config,
        algorithm_config=algorithm_config,
        shelves=shelves,
        shelf_types=shelf_types,
        shelf_type_configs=shelf_type_configs,
        shelf_type_layouts=shelf_type_layouts,
        package_presets=package_presets,
        orders=orders,
    )
