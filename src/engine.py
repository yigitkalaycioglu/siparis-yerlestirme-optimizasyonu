from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from src.models import (
    AlgorithmConfig,
    AppState,
    Order,
    Placement,
    Rect,
    ShelfState,
    ShelfTypeConfig,
    ShelfTypeLayout,
    WarehouseConfig,
    make_shelf_type_config,
    make_shelf_type_layout,
    parse_ship_date,
)


def generate_shelf_id(aisle: int, side: int, row: int, y_index: int) -> str:
    return f"A{aisle:02d}-S{side:02d}-R{row:03d}-Y{y_index:02d}"


def get_shelf_type_config(state: AppState, shelf_type: str) -> ShelfTypeConfig:
    return state.shelf_type_configs.get(
        shelf_type,
        make_shelf_type_config(shelf_type, state.warehouse_config),
    )


def _build_shelf_type_pattern(
    shelf_types: list[str],
    shelf_type_layouts: list[ShelfTypeLayout] | None = None,
) -> list[str]:
    shelf_type_list = [s for s in shelf_types if s.strip()] or ["Standart"]
    resolved_layouts = {layout.label: layout for layout in (shelf_type_layouts or [])}
    ordered_shelf_types = sorted(
        shelf_type_list,
        key=lambda shelf_type: (
            resolved_layouts.get(shelf_type, make_shelf_type_layout(shelf_type)).sequence,
            shelf_type.lower(),
        ),
    )

    pattern: list[str] = []
    for shelf_type in ordered_shelf_types:
        block_size = resolved_layouts.get(shelf_type, make_shelf_type_layout(shelf_type)).block_size
        pattern.extend([shelf_type] * block_size)
    return pattern or ordered_shelf_types or ["Standart"]


def _apply_type_config_to_empty_shelf(shelf: ShelfState, shelf_type: str, config: ShelfTypeConfig) -> None:
    shelf.shelf_type = shelf_type
    shelf.width_cm = config.shelf_width_cm
    shelf.depth_cm = config.shelf_depth_cm
    shelf.height_cm = config.shelf_height_cm
    shelf.free_rectangles = [Rect(x=0, y=0, width=config.shelf_width_cm, depth=config.shelf_depth_cm)]


def apply_shelf_type_layouts_to_available_shelves(state: AppState) -> int:
    pattern = _build_shelf_type_pattern(state.shelf_types, state.shelf_type_layouts)
    updated = 0
    if not pattern:
        return updated

    bays: dict[tuple[int, int, int], list[ShelfState]] = {}
    for shelf in state.shelves:
        bays.setdefault((shelf.aisle_index, shelf.side_index, shelf.row_index), []).append(shelf)

    for bay_index, bay_key in enumerate(sorted(bays)):
        bay_shelves = bays[bay_key]
        if any(shelf.placements or shelf.manual_full for shelf in bay_shelves):
            continue
        shelf_type = pattern[bay_index % len(pattern)]
        config = get_shelf_type_config(state, shelf_type)
        for shelf in bay_shelves:
            _apply_type_config_to_empty_shelf(shelf, shelf_type, config)
            updated += 1
    return updated


def assign_shelf_type(state: AppState, shelf_id: str, shelf_type: str) -> tuple[bool, str]:
    shelf = next((s for s in state.shelves if s.shelf_id == shelf_id), None)
    if shelf is None:
        return False, "Raf bulunamadı."
    if shelf.placements or shelf.manual_full:
        return False, "Dolu ya da kilitli rafın tipi değiştirilemez. Önce rafı boşaltın."
    if shelf_type not in state.shelf_types:
        return False, "Seçilen raf tipi kayıtlı değil."

    _apply_type_config_to_empty_shelf(shelf, shelf_type, get_shelf_type_config(state, shelf_type))
    return True, f"{shelf.shelf_id} raf tipi {shelf_type} olarak güncellendi."


def build_empty_shelves(
    config: WarehouseConfig,
    shelf_types: list[str] | None = None,
    shelf_type_configs: dict[str, ShelfTypeConfig] | None = None,
    shelf_type_layouts: list[ShelfTypeLayout] | None = None,
) -> list[ShelfState]:
    shelves: list[ShelfState] = []
    shelf_type_list = [s for s in (shelf_types or ["Standart"]) if s.strip()] or ["Standart"]
    resolved_shelf_type_configs = {
        shelf_type: shelf_type_configs.get(shelf_type)
        if shelf_type_configs and shelf_type in shelf_type_configs
        else make_shelf_type_config(shelf_type, config)
        for shelf_type in shelf_type_list
    }
    shelf_pattern = _build_shelf_type_pattern(shelf_type_list, shelf_type_layouts)
    bay_index = 0
    for aisle in range(1, config.aisles + 1):
        for side in range(1, config.sides_per_aisle + 1):
            for row in range(1, config.rows_per_side + 1):
                shelf_type = shelf_pattern[bay_index % len(shelf_pattern)]
                shelf_config = resolved_shelf_type_configs[shelf_type]
                for y_index in range(1, config.shelves_per_row + 1):
                    shelves.append(
                        ShelfState(
                            shelf_id=generate_shelf_id(aisle, side, row, y_index),
                            aisle_index=aisle,
                            side_index=side,
                            row_index=row,
                            y_index=y_index,
                            width_cm=shelf_config.shelf_width_cm,
                            depth_cm=shelf_config.shelf_depth_cm,
                            height_cm=shelf_config.shelf_height_cm,
                            shelf_type=shelf_type,
                            free_rectangles=[
                                Rect(
                                    x=0,
                                    y=0,
                                    width=shelf_config.shelf_width_cm,
                                    depth=shelf_config.shelf_depth_cm,
                                )
                            ],
                        )
                    )
                bay_index += 1
    return shelves


def create_initial_state(
    warehouse_config: WarehouseConfig, algorithm_config: AlgorithmConfig, shelf_types: list[str] | None = None
) -> AppState:
    resolved_shelf_types = [s for s in (shelf_types or ["Standart"]) if s.strip()] or ["Standart"]
    return AppState(
        warehouse_config=warehouse_config,
        algorithm_config=algorithm_config,
        shelves=build_empty_shelves(warehouse_config, resolved_shelf_types),
        shelf_types=resolved_shelf_types,
        shelf_type_configs={shelf_type: make_shelf_type_config(shelf_type, warehouse_config) for shelf_type in resolved_shelf_types},
        shelf_type_layouts=[make_shelf_type_layout(shelf_type) for shelf_type in resolved_shelf_types],
    )


def apply_shelf_type_config(state: AppState, shelf_type: str, new_config: ShelfTypeConfig) -> tuple[bool, str]:
    affected_shelves = [shelf for shelf in state.shelves if shelf.shelf_type == shelf_type]
    if any(shelf.placements or shelf.manual_full for shelf in affected_shelves):
        return False, "Bu raf tipinde dolu ya da manuel işaretli raflar var. Önce onları boşaltın."

    state.shelf_type_configs[shelf_type] = make_shelf_type_config(shelf_type, state.warehouse_config, {
        "shelf_width_cm": new_config.shelf_width_cm,
        "shelf_depth_cm": new_config.shelf_depth_cm,
        "shelf_height_cm": new_config.shelf_height_cm,
        "clearance_width_cm": new_config.clearance_width_cm,
        "clearance_depth_cm": new_config.clearance_depth_cm,
        "smallest_pallet_width_cm": new_config.smallest_pallet_width_cm,
        "smallest_pallet_depth_cm": new_config.smallest_pallet_depth_cm,
    })

    for shelf in affected_shelves:
        shelf.width_cm = new_config.shelf_width_cm
        shelf.depth_cm = new_config.shelf_depth_cm
        shelf.height_cm = new_config.shelf_height_cm
        shelf.free_rectangles = [Rect(x=0, y=0, width=new_config.shelf_width_cm, depth=new_config.shelf_depth_cm)]

    return True, f'"{shelf_type}" raf tipi parametreleri güncellendi.'


def _is_contained(inner: Rect, outer: Rect) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.depth <= outer.y + outer.depth
    )


def _normalize_free_rectangles(rects: list[Rect], min_fragment_cm2: int) -> list[Rect]:
    filtered = [r for r in rects if r.width > 0 and r.depth > 0 and r.area >= min_fragment_cm2]
    result: list[Rect] = []
    for i, rect in enumerate(filtered):
        contained = False
        for j, other in enumerate(filtered):
            if i != j and _is_contained(rect, other):
                contained = True
                break
        if not contained:
            result.append(rect)
    return result


def _candidate_orientations(order: Order, algo: AlgorithmConfig) -> list[tuple[int, int, bool]]:
    orientations = [(order.requested_width_cm, order.requested_depth_cm, False)]
    if algo.allow_rotation and order.requested_width_cm != order.requested_depth_cm:
        orientations.append((order.requested_depth_cm, order.requested_width_cm, True))
    return orientations


def _place_in_rect(free_rect: Rect, width: int, depth: int) -> tuple[Rect, list[Rect]]:
    placement_rect = Rect(x=free_rect.x, y=free_rect.y, width=width, depth=depth)

    right_rect = Rect(
        x=free_rect.x + width,
        y=free_rect.y,
        width=free_rect.width - width,
        depth=depth,
    )
    top_rect = Rect(
        x=free_rect.x,
        y=free_rect.y + depth,
        width=free_rect.width,
        depth=free_rect.depth - depth,
    )

    return placement_rect, [right_rect, top_rect]


def _days_delta(order_date: str, other_date: str) -> int:
    try:
        return abs((parse_ship_date(order_date) - parse_ship_date(other_date)).days)
    except ValueError:
        return 9999


def _days_until_due(order: Order, today: date | None = None) -> int:
    base_day = today or date.today()
    try:
        return (parse_ship_date(order.effective_due_date) - base_day).days
    except ValueError:
        return 9999


def _due_date_urgency(order: Order, algo: AlgorithmConfig, today: date | None = None) -> float:
    window = max(1, algo.due_date_priority_days)
    days_left = _days_until_due(order, today)
    if days_left <= 0:
        return 1.0
    if days_left >= window:
        return 0.0
    return (window - days_left) / window


def _storage_pressure(order: Order) -> float:
    if order.max_storage_days <= 0:
        return 0.0
    return min(1.0, order.planned_storage_days / max(1, order.max_storage_days))


def _storage_violation(order: Order) -> float:
    if order.max_storage_days <= 0:
        return 0.0
    excess_days = order.planned_storage_days - order.max_storage_days
    if excess_days <= 0:
        return 0.0
    return min(2.0, excess_days / max(1, order.max_storage_days))


def placement_priority_score(order: Order, algo: AlgorithmConfig | None = None, today: date | None = None) -> float:
    config = algo or AlgorithmConfig()
    due_urgency = _due_date_urgency(order, config, today)
    storage_pressure = _storage_pressure(order)
    storage_violation = _storage_violation(order)
    return (due_urgency * 2.0) + storage_pressure + storage_violation


def sort_orders_for_automatic_placement(orders: list[Order], algo: AlgorithmConfig | None = None) -> list[Order]:
    today = date.today()
    return sorted(
        orders,
        key=lambda order: (
            -placement_priority_score(order, algo, today),
            order.effective_due_date or "9999-12-31",
            order.entry_date or "9999-12-31",
            order.order_id,
        ),
    )


def _shelf_distance(shelf: ShelfState) -> int:
    # Start the path preference from low aisle/row indexes as a deterministic route heuristic.
    return shelf.aisle_index * 1000 + shelf.row_index * 10 + shelf.y_index


def _smallest_pallet_capacity_hint(config: WarehouseConfig | ShelfTypeConfig) -> int:
    smallest_area = config.smallest_pallet_width_cm * config.smallest_pallet_depth_cm
    if smallest_area <= 0:
        return 0
    return (config.shelf_width_cm * config.shelf_depth_cm) // smallest_area


def suggest_shelves_for_order(
    state: AppState,
    order: Order,
    allowed_shelf_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    algo = state.algorithm_config

    candidates: list[dict[str, Any]] = []
    today = date.today()
    due_urgency = _due_date_urgency(order, algo, today)
    storage_pressure = _storage_pressure(order)
    storage_violation = _storage_violation(order)

    all_distances = [_shelf_distance(s) for s in state.shelves]
    max_distance = max(all_distances) if all_distances else 1

    for shelf in state.shelves:
        if shelf.manual_full:
            continue
        if allowed_shelf_types is not None and shelf.shelf_type not in allowed_shelf_types:
            continue

        config = get_shelf_type_config(state, shelf.shelf_type)
        best_local_candidate: dict[str, Any] | None = None

        for free_rect_index, free_rect in enumerate(shelf.free_rectangles):
            for place_w, place_d, rotated in _candidate_orientations(order, algo):
                if place_w + config.clearance_width_cm > free_rect.width:
                    continue
                if place_d + config.clearance_depth_cm > free_rect.depth:
                    continue

                effective_w = place_w + config.clearance_width_cm
                effective_d = place_d + config.clearance_depth_cm

                waste_area = free_rect.area - (effective_w * effective_d)
                fill_efficiency_penalty = waste_area / shelf.area

                distance_score = _shelf_distance(shelf) / max_distance

                company_bonus = 0.0
                date_bonus = 0.0
                destination_bonus = 0.0
                if shelf.placements:
                    if algo.cluster_same_company:
                        same_company_count = sum(
                            1 for p in shelf.placements if p.company.strip().lower() == order.company.strip().lower()
                        )
                        company_bonus = same_company_count / len(shelf.placements)

                    if algo.cluster_same_ship_date:
                        near_date_count = sum(
                            1
                            for p in shelf.placements
                            if _days_delta(order.effective_due_date, p.due_date or p.ship_date)
                            <= algo.ship_date_cluster_days
                        )
                        date_bonus = near_date_count / len(shelf.placements)

                    if algo.cluster_same_destination:
                        destination_key = order.destination_key.strip().lower()
                        same_destination_count = sum(
                            1
                            for p in shelf.placements
                            if (p.destination or p.company or "-").strip().lower() == destination_key
                        )
                        destination_bonus = same_destination_count / len(shelf.placements)

                balance_penalty = shelf.utilization
                access_pressure = max(due_urgency, storage_pressure)
                distance_component = distance_score * (1.0 + access_pressure)

                total_score = (
                    algo.weight_fill_efficiency * fill_efficiency_penalty
                    + algo.weight_travel_distance * distance_component
                    - algo.weight_company_cluster * company_bonus
                    - algo.weight_date_cluster * date_bonus
                    - algo.weight_destination_cluster * destination_bonus
                    + algo.weight_due_date_priority * due_urgency * distance_score
                    + algo.weight_storage_duration * ((storage_pressure * distance_score) + storage_violation)
                    + algo.weight_balance * balance_penalty
                )

                candidate = {
                    "shelf_id": shelf.shelf_id,
                    "shelf_type": shelf.shelf_type,
                    "score": total_score,
                    "free_rect_index": free_rect_index,
                    "effective_width": effective_w,
                    "effective_depth": effective_d,
                    "placed_width": place_w,
                    "placed_depth": place_d,
                    "rotated": rotated,
                    "capacity_hint": _smallest_pallet_capacity_hint(config),
                    "current_order_count": len(shelf.placements),
                    "utilization": shelf.utilization,
                    "aisle": shelf.aisle_index,
                    "side": shelf.side_index,
                    "row": shelf.row_index,
                    "y": shelf.y_index,
                    "due_date": order.effective_due_date,
                    "entry_date": order.entry_date,
                    "destination": order.destination_key,
                    "max_storage_days": order.max_storage_days,
                    "planned_storage_days": order.planned_storage_days,
                    "due_urgency": round(due_urgency, 3),
                    "storage_pressure": round(storage_pressure, 3),
                    "storage_violation": round(storage_violation, 3),
                    "company_bonus": round(company_bonus, 3),
                    "date_bonus": round(date_bonus, 3),
                    "destination_bonus": round(destination_bonus, 3),
                }

                if best_local_candidate is None or candidate["score"] < best_local_candidate["score"]:
                    best_local_candidate = candidate

        if best_local_candidate:
            candidates.append(best_local_candidate)

    candidates.sort(key=lambda x: x["score"])
    return candidates[: max(1, algo.top_k_suggestions)]


def place_order_on_shelf(
    state: AppState, order: Order, shelf_id: str, free_rect_index: int | None = None
) -> tuple[bool, str]:
    algo = state.algorithm_config

    shelf = next((s for s in state.shelves if s.shelf_id == shelf_id), None)
    if shelf is None:
        return False, "Seçilen raf bulunamadı."
    if shelf.manual_full:
        return False, "Raf manuel olarak dolu işaretlenmiş."

    if free_rect_index is not None and (free_rect_index < 0 or free_rect_index >= len(shelf.free_rectangles)):
        return False, "Geçersiz boş alan seçimi."

    if any(p.order_id == order.order_id for p in shelf.placements) or any(
        existing.order_id == order.order_id for existing in state.orders
    ):
        return False, f"Bu sipariş kodu zaten kayıtlı: {order.order_id}"

    if free_rect_index is not None:
        candidate_indices = [free_rect_index]
    else:
        candidate_indices = list(range(len(shelf.free_rectangles)))

    config = get_shelf_type_config(state, shelf.shelf_type)
    for selected_idx in candidate_indices:
        selected_rect = shelf.free_rectangles[selected_idx]
        for place_w, place_d, rotated in _candidate_orientations(order, algo):
            effective_w = place_w + config.clearance_width_cm
            effective_d = place_d + config.clearance_depth_cm

            if effective_w > selected_rect.width or effective_d > selected_rect.depth:
                continue

            placement_rect, new_rects = _place_in_rect(selected_rect, effective_w, effective_d)

            shelf.placements.append(
                Placement(
                    order_id=order.order_id,
                    company=order.company,
                    ship_date=order.ship_date,
                    x=placement_rect.x,
                    y=placement_rect.y,
                    width=place_w,
                    depth=place_d,
                    rotated=rotated,
                    due_date=order.effective_due_date,
                    entry_date=order.entry_date,
                    destination=order.destination_key,
                    max_storage_days=order.max_storage_days,
                )
            )

            updated = [r for i, r in enumerate(shelf.free_rectangles) if i != selected_idx]
            updated.extend(new_rects)
            shelf.free_rectangles = _normalize_free_rectangles(updated, algo.min_fragment_cm2)

            state.orders.append(order)
            return True, "Sipariş başarıyla rafa yerleştirildi."

    return False, "Sipariş seçili raftaki boş alanlara sığmadı."


def mark_shelf_manual_full(state: AppState, shelf_id: str, is_full: bool) -> tuple[bool, str]:
    shelf = next((s for s in state.shelves if s.shelf_id == shelf_id), None)
    if shelf is None:
        return False, "Raf bulunamadı."
    shelf.manual_full = is_full
    if is_full:
        return True, "Raf manuel olarak dolu işaretlendi."
    return True, "Raf tekrar kullanılabilir duruma alındı."


def clear_shelf(state: AppState, shelf_id: str) -> tuple[bool, str]:
    shelf = next((s for s in state.shelves if s.shelf_id == shelf_id), None)
    if shelf is None:
        return False, "Raf bulunamadı."

    removed_order_ids = {placement.order_id for placement in shelf.placements}
    removed_count = len(removed_order_ids)

    shelf.placements = []
    shelf.manual_full = False
    shelf.free_rectangles = [Rect(x=0, y=0, width=shelf.width_cm, depth=shelf.depth_cm)]

    if removed_order_ids:
        state.orders = [order for order in state.orders if order.order_id not in removed_order_ids]

    return True, f"Raf tamamen boşaltıldı. Silinen sipariş adedi: {removed_count}"


def clear_all_shelves(state: AppState) -> tuple[bool, str]:
    cleared_shelf_count = 0
    removed_order_count = len(state.orders)

    for shelf in state.shelves:
        had_data = bool(shelf.placements) or shelf.manual_full or len(shelf.free_rectangles) != 1
        shelf.placements = []
        shelf.manual_full = False
        shelf.free_rectangles = [Rect(x=0, y=0, width=shelf.width_cm, depth=shelf.depth_cm)]
        if had_data:
            cleared_shelf_count += 1

    state.orders = []
    return (
        True,
        f"Tüm raflar boşaltıldı. Sıfırlanan raf: {cleared_shelf_count}, silinen sipariş: {removed_order_count}",
    )


def apply_new_configs(
    state: AppState,
    new_warehouse: WarehouseConfig,
    new_algorithm: AlgorithmConfig,
    rebuild_if_needed: bool,
) -> AppState:
    same_topology = (
        state.warehouse_config.aisles == new_warehouse.aisles
        and state.warehouse_config.sides_per_aisle == new_warehouse.sides_per_aisle
        and state.warehouse_config.rows_per_side == new_warehouse.rows_per_side
        and state.warehouse_config.shelves_per_row == new_warehouse.shelves_per_row
        and state.warehouse_config.shelf_width_cm == new_warehouse.shelf_width_cm
        and state.warehouse_config.shelf_depth_cm == new_warehouse.shelf_depth_cm
        and state.warehouse_config.shelf_height_cm == new_warehouse.shelf_height_cm
    )

    state.warehouse_config = replace(new_warehouse)
    state.algorithm_config = replace(new_algorithm)

    if rebuild_if_needed or not same_topology:
        state.shelves = build_empty_shelves(
            new_warehouse,
            state.shelf_types,
            state.shelf_type_configs,
            state.shelf_type_layouts,
        )
        state.orders = []

    return state


def orders_in_date_window(state: AppState, center_date: str, day_radius: int) -> int:
    low = parse_ship_date(center_date) - timedelta(days=day_radius)
    high = parse_ship_date(center_date) + timedelta(days=day_radius)
    count = 0
    for order in state.orders:
        target = parse_ship_date(order.effective_due_date)
        if low <= target <= high:
            count += 1
    return count
