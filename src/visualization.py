from __future__ import annotations

import json
from collections import Counter
from typing import Iterable

from src.models import AppState


DEFAULT_LAYOUT: dict[str, float] = {
    "aisle_pitch": 4.8,
    "row_pitch": 1.15,
    "side_gap": 0.95,
    "level_pitch": 0.78,
    "shelf_width": 1.65,
    "shelf_depth": 0.62,
    "shelf_height": 0.06,
    "placement_height": 0.48,
}

SHELF_TYPE_PALETTE = [
  "#2d7dd2",
  "#f45d48",
  "#17a398",
  "#f7b32b",
  "#7b61ff",
  "#2fbf71",
  "#b56576",
  "#4d908e",
  "#f9844a",
  "#577590",
]


def shelf_type_color(shelf_type: str, type_order: Iterable[str] | None = None) -> str:
  ordered_types = [item for item in (type_order or []) if str(item).strip()]
  if shelf_type in ordered_types:
    index = ordered_types.index(shelf_type)
  else:
    index = sum(ord(char) for char in shelf_type)
  return SHELF_TYPE_PALETTE[index % len(SHELF_TYPE_PALETTE)]


def build_scene_payload(
  state: AppState,
  *,
  selected_aisles: Iterable[int] | None = None,
  level_range: tuple[int, int] | None = None,
  show_only_occupied: bool = False,
  show_placements: bool = True,
  highlight_shelf_id: str | None = None,
  visible_shelf_types: Iterable[str] | None = None,
) -> dict:
  aisle_filter = set(selected_aisles) if selected_aisles else None
  shelf_type_filter = set(visible_shelf_types) if visible_shelf_types is not None else None
  if level_range is None:
    min_level, max_level = 1, state.warehouse_config.shelves_per_row
  else:
    min_level, max_level = level_range

  shelves: list[dict] = []
  rendered_placements = 0
  occupied_shelves = 0
  blocked_shelves = 0
  type_counts = Counter(shelf.shelf_type for shelf in state.shelves)
  resolved_types = state.shelf_types or sorted(type_counts.keys()) or ["Standart"]
  type_configs = state.shelf_type_configs
  type_colors = {shelf_type: shelf_type_color(shelf_type, resolved_types) for shelf_type in resolved_types}

  for shelf in state.shelves:
    if aisle_filter is not None and shelf.aisle_index not in aisle_filter:
      continue
    if shelf.y_index < min_level or shelf.y_index > max_level:
      continue
    if (
      shelf_type_filter is not None
      and shelf.shelf_type not in shelf_type_filter
      and shelf.shelf_id != highlight_shelf_id
    ):
      continue
    if show_only_occupied and not shelf.placements and not shelf.manual_full:
      continue

    is_occupied = bool(shelf.placements)
    occupied_shelves += int(is_occupied)
    blocked_shelves += int(shelf.manual_full)

    placements: list[dict] = []
    if show_placements:
      for placement in shelf.placements:
        placements.append(
          {
            "order_id": placement.order_id,
            "company": placement.company,
            "ship_date": placement.ship_date,
            "due_date": placement.due_date or placement.ship_date,
            "entry_date": placement.entry_date,
            "destination": placement.destination or placement.company,
            "max_storage_days": placement.max_storage_days,
            "x": placement.x,
            "y": placement.y,
            "width": placement.width,
            "depth": placement.depth,
            "rotated": placement.rotated,
          }
        )
      rendered_placements += len(placements)

    shelves.append(
      {
        "shelf_id": shelf.shelf_id,
        "aisle_index": shelf.aisle_index,
        "side_index": shelf.side_index,
        "row_index": shelf.row_index,
        "y_index": shelf.y_index,
        "width_cm": shelf.width_cm,
        "depth_cm": shelf.depth_cm,
        "height_cm": shelf.height_cm,
        "shelf_type": shelf.shelf_type,
        "type_color": type_colors.get(shelf.shelf_type, shelf_type_color(shelf.shelf_type, resolved_types)),
        "utilization": shelf.utilization,
        "manual_full": shelf.manual_full,
        "placement_count": len(shelf.placements),
        "placements": placements,
      }
    )

  return {
    "warehouse": {
      "aisles": state.warehouse_config.aisles,
      "sides_per_aisle": state.warehouse_config.sides_per_aisle,
      "rows_per_side": state.warehouse_config.rows_per_side,
      "shelves_per_row": state.warehouse_config.shelves_per_row,
      "clearance_width_cm": state.warehouse_config.clearance_width_cm,
      "clearance_depth_cm": state.warehouse_config.clearance_depth_cm,
    },
    "layout": dict(DEFAULT_LAYOUT),
    "stats": {
      "total_shelves": len(state.shelves),
      "rendered_shelves": len(shelves),
      "occupied_shelves": occupied_shelves,
      "blocked_shelves": blocked_shelves,
      "rendered_placements": rendered_placements,
      "orders": len(state.orders),
    },
    "shelf_type_summary": [
      {
        "type": shelf_type,
        "count": int(type_counts.get(shelf_type, 0)),
        "visible": shelf_type_filter is None or shelf_type in shelf_type_filter,
        "color": type_colors.get(shelf_type, shelf_type_color(shelf_type, resolved_types)),
        "width_cm": getattr(type_configs.get(shelf_type), "shelf_width_cm", 0),
        "depth_cm": getattr(type_configs.get(shelf_type), "shelf_depth_cm", 0),
        "height_cm": getattr(type_configs.get(shelf_type), "shelf_height_cm", 0),
      }
      for shelf_type in resolved_types
    ],
    "highlight_shelf_id": highlight_shelf_id,
    "shelf_type_colors": type_colors,
    "shelves": shelves,
  }


def render_three_html(payload: dict, placement_color: str = "27ae60") -> str:
    safe_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    safe_color = "".join(c for c in placement_color if c in "0123456789abcdefABCDEF")[:6] or "27ae60"

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background:
        radial-gradient(circle at top left, rgba(90, 140, 255, 0.18), transparent 34%),
        radial-gradient(circle at bottom right, rgba(255, 164, 77, 0.12), transparent 28%),
        linear-gradient(180deg, #0c1220 0%, #10182b 48%, #070b13 100%);
      color: #eff4ff;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    #stage {{ position: absolute; inset: 0; }}

    #hud {{
      position: absolute;
      left: 16px;
      top: 16px;
      z-index: 10;
      max-width: 380px;
      padding: 12px 14px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 16px;
      backdrop-filter: blur(14px);
      background: rgba(8, 12, 21, 0.68);
      box-shadow: 0 16px 50px rgba(0, 0, 0, 0.32);
    }}

    #hud h3 {{
      margin: 0 0 6px 0;
      font-size: 13px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #cfe1ff;
    }}

    #hud p {{
      margin: 3px 0;
      font-size: 12px;
      line-height: 1.45;
      color: rgba(239, 244, 255, 0.78);
    }}

    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px 8px;
      margin-top: 8px;
      font-size: 11px;
    }}

    .stat-item {{
      padding: 6px 8px;
      border-radius: 9px;
      background: rgba(255, 255, 255, 0.06);
    }}

    .stat-item strong {{
      display: block;
      font-size: 15px;
      margin-top: 2px;
      color: #ffffff;
    }}

    #type-legend {{
      margin-top: 10px;
      display: grid;
      gap: 6px;
      font-size: 11px;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.05);
    }}

    .legend-swatch {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}

    #tooltip {{
      position: absolute;
      right: 16px;
      top: 16px;
      z-index: 10;
      width: min(340px, calc(100vw - 32px));
      padding: 12px 14px;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 16px;
      background: rgba(10, 15, 24, 0.78);
      backdrop-filter: blur(14px);
      box-shadow: 0 16px 50px rgba(0, 0, 0, 0.32);
      color: #eef4ff;
      font-size: 12px;
      min-height: 60px;
    }}

    #shelf-panel {{
      position: absolute;
      right: 16px;
      top: 16px;
      z-index: 20;
      width: min(360px, calc(100vw - 32px));
      max-height: calc(100% - 32px);
      overflow-y: auto;
      padding: 14px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 16px;
      background: rgba(8, 12, 24, 0.94);
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 70px rgba(0, 0, 0, 0.5);
      color: #eef4ff;
      font-size: 13px;
      display: none;
    }}

    .panel-stat {{ padding: 9px 11px; background: rgba(255,255,255,0.07); border-radius: 9px; }}
    .panel-stat-label {{ font-size: 10px; color: rgba(239,244,255,0.55); margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .panel-stat-value {{ font-size: 18px; font-weight: 700; color: #fff; }}
    .panel-placement {{ padding: 7px 10px; background: rgba(255,255,255,0.06); border-radius: 8px; margin-bottom: 4px; }}

    #manage-btn {{
      width: 100%;
      padding: 10px;
      margin-top: 12px;
      background: rgba(74, 144, 226, 0.22);
      border: 1px solid rgba(74, 144, 226, 0.55);
      border-radius: 10px;
      color: #7fc8f8;
      font-size: 13px;
      cursor: pointer;
      font-family: inherit;
      transition: background 0.15s;
    }}

    #manage-btn:hover {{ background: rgba(74, 144, 226, 0.38); }}

    .progress-track {{
      height: 6px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.1);
      overflow: hidden;
      margin: 6px 0 12px;
    }}

    .progress-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s ease; }}

    .panel-close-btn {{
      background: none;
      border: none;
      color: rgba(239, 244, 255, 0.5);
      font-size: 18px;
      cursor: pointer;
      line-height: 1;
      padding: 2px 4px;
    }}
    .panel-close-btn:hover {{ color: rgba(239, 244, 255, 0.9); }}
  </style>
</head>
<body>
  <div id="hud">
    <h3>Sahne</h3>
    <p>Fare ile sürükle: döndür · Tekerlek: yakınlaştır · Sağ tuş: kaydır</p>
    <p style="color: rgba(239,244,255,0.6)">Rafa tıklayın → ayrıntı paneli açılır, sayfada işlem yapılabilir.</p>
    <div class="stat-grid" id="stats"></div>
    <div id="type-legend"></div>
  </div>
  <div id="tooltip">Bir rafın üzerine gelerek detayları görün.</div>
  <div id="shelf-panel">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 style="margin:0;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#cfe1ff">Raf Detayı</h3>
      <button class="panel-close-btn" onclick="closePanel()" title="Kapat">✕</button>
    </div>
    <div id="shelf-panel-content"></div>
    <button id="manage-btn" onclick="manageSelf()">Bu rafı seç ve işlem yap →</button>
  </div>
  <div id="stage"></div>

  <script type="importmap">
  {{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}}}
  </script>
  <script type="module">
  import * as THREE from 'three';
  import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
  const payload = {safe_json};
  const stage = document.getElementById('stage');
  const tooltip = document.getElementById('tooltip');
  const stats = document.getElementById('stats');
  const typeLegend = document.getElementById('type-legend');

  function hashString(value) {{
    let hash = 0;
    for (let i = 0; i < value.length; i++) {{
      hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
    }}
    return Math.abs(hash);
  }}

  function typeColor(typeName) {{
    if (payload.shelf_type_colors && payload.shelf_type_colors[typeName]) {{
      return new THREE.Color(payload.shelf_type_colors[typeName]);
    }}
    const hue = hashString(typeName || 'Standart') % 360;
    const color = new THREE.Color();
    color.setHSL(hue / 360, 0.42, 0.58);
    return color;
  }}

  stats.innerHTML = [
    ['Toplam raf', payload.stats.total_shelves],
    ['Çizilen raf', payload.stats.rendered_shelves],
    ['Dolu raf', payload.stats.occupied_shelves],
    ['Yerleşen sipariş', payload.stats.rendered_placements],
    ['Manuel dolu', payload.stats.blocked_shelves],
    ['Sipariş kaydı', payload.stats.orders],
  ].map(([label, value]) => `
    <div class="stat-item">
      <span>${{label}}</span>
      <strong>${{value}}</strong>
    </div>
  `).join('');

  typeLegend.innerHTML = (payload.shelf_type_summary || []).map((entry) => {{
    const swatch = typeColor(entry.type).getStyle();
    const dims = entry.width_cm && entry.depth_cm && entry.height_cm
      ? `${{entry.width_cm}}×${{entry.depth_cm}}×${{entry.height_cm}}`
      : '';
    return `
      <div class="legend-item" style="opacity:${{entry.visible ? 1 : 0.45}}">
        <span class="legend-swatch" style="background:${{swatch}}"></span>
        <span>${{entry.type}}${{dims ? ` · ${{dims}} cm` : ''}}</span>
        <strong style="margin-left:auto;color:#fff">${{entry.count}}</strong>
      </div>
    `;
  }}).join('');

  const L = payload.layout;
  const W = payload.warehouse;
  const maxShelfWidthCm = Math.max(1, ...payload.shelves.map(s => s.width_cm || 1));
  const maxShelfDepthCm = Math.max(1, ...payload.shelves.map(s => s.depth_cm || 1));
  const maxShelfHeightCm = Math.max(1, ...payload.shelves.map(s => s.height_cm || 1));
  const P = {{
    aisle_pitch: Math.max(L.aisle_pitch, L.shelf_width + 2.4),
    row_pitch: Math.max(L.row_pitch, L.shelf_depth + 0.5),
    side_gap: Math.max(L.side_gap, L.shelf_depth * 0.8 + 0.55),
    level_pitch: Math.max(L.level_pitch, L.shelf_height + L.placement_height + 0.28),
  }};

  function shelfRenderSize(shelf) {{
    return {{
      width: Math.max(0.35, ((shelf.width_cm || maxShelfWidthCm) / maxShelfWidthCm) * L.shelf_width),
      depth: Math.max(0.22, ((shelf.depth_cm || maxShelfDepthCm) / maxShelfDepthCm) * L.shelf_depth),
      height: Math.max(0.045, ((shelf.height_cm || maxShelfHeightCm) / maxShelfHeightCm) * L.shelf_height),
    }};
  }}

  const extentX = (W.aisles - 1) * P.aisle_pitch;
  const extentZ = (W.rows_per_side - 1) * P.row_pitch;
  const extentY = (W.shelves_per_row - 1) * P.level_pitch;

  const centerX = extentX / 2;
  const centerZ = extentZ / 2;
  const centerY = extentY * 0.4;

  const footprintX = extentX + L.shelf_width + 4;
  const footprintZ = extentZ + 2 * P.side_gap + L.shelf_depth + 4;
  const gridSize = Math.max(20, footprintX, footprintZ);
  const cameraDistance = Math.max(20, Math.max(footprintX, footprintZ) * 0.85);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0d1424, cameraDistance * 0.3, cameraDistance * 3.5);

  const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.appendChild(renderer.domElement);

  const camera = new THREE.PerspectiveCamera(45, stage.clientWidth / stage.clientHeight, 0.1, cameraDistance * 6);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.maxPolarAngle = Math.PI * 0.49;

  const hemiLight = new THREE.HemisphereLight(0xd4e8ff, 0x1a1206, 1.2);
  scene.add(hemiLight);
  const dirLight = new THREE.DirectionalLight(0xfff4d6, 3.5);
  dirLight.position.set(centerX + 40, 80, centerZ + 50);
  dirLight.castShadow = true;
  dirLight.shadow.mapSize.set(1024, 1024);
  dirLight.shadow.camera.near = 1;
  dirLight.shadow.camera.far = cameraDistance * 4;
  dirLight.shadow.camera.left = -cameraDistance * 1.2;
  dirLight.shadow.camera.right = cameraDistance * 1.2;
  dirLight.shadow.camera.top = cameraDistance * 1.2;
  dirLight.shadow.camera.bottom = -cameraDistance * 1.2;
  dirLight.shadow.bias = -0.0005;
  scene.add(dirLight);
  scene.add(new THREE.AmbientLight(0x8ab0d8, 0.4));

  const gridDivisions = Math.min(80, Math.max(20, Math.round(gridSize / 3)));
  const grid = new THREE.GridHelper(gridSize, gridDivisions, 0x31435f, 0x182233);
  grid.material.opacity = 0.5;
  grid.material.transparent = true;
  grid.position.set(centerX, 0, centerZ);
  scene.add(grid);

  const shelfGeometry = new THREE.BoxGeometry(1, 1, 1);
  const shelfMaterial = new THREE.MeshStandardMaterial({{ color: 0xffffff, roughness: 0.45, metalness: 0.55 }});
  const shelfMesh = payload.shelves.length > 0
    ? new THREE.InstancedMesh(shelfGeometry, shelfMaterial, payload.shelves.length)
    : null;
  if (shelfMesh) {{
    shelfMesh.castShadow = false;
    shelfMesh.receiveShadow = true;
  }}

  const placementGeometry = new THREE.BoxGeometry(1, 1, 1);
  const placementMaterial = new THREE.MeshStandardMaterial({{ color: 0xffffff, roughness: 0.80, metalness: 0.05 }});
  const placementEntries = [];
  const placementMesh = payload.stats.rendered_placements > 0
    ? new THREE.InstancedMesh(placementGeometry, placementMaterial, payload.stats.rendered_placements)
    : null;
  if (placementMesh) {{
    placementMesh.castShadow = true;
    placementMesh.receiveShadow = true;
  }}

  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  const highlightId = payload.highlight_shelf_id;
  let highlightWorldPos = null;

  function shelfPosition(shelf) {{
    const x = (shelf.aisle_index - 1) * P.aisle_pitch;
    const z = (shelf.row_index - 1) * P.row_pitch + (shelf.side_index === 1 ? -P.side_gap : P.side_gap);
    const y = (shelf.y_index - 1) * P.level_pitch;
    return [x, y, z];
  }}

  function updateTooltip(text) {{ tooltip.innerHTML = text; }}

  payload.shelves.forEach((shelf, index) => {{
    const [x, y, z] = shelfPosition(shelf);
    const shelfSize = shelfRenderSize(shelf);
    dummy.position.set(x, y, z);
    dummy.scale.set(shelfSize.width, shelfSize.height, shelfSize.depth);
    dummy.updateMatrix();
    if (shelfMesh) shelfMesh.setMatrixAt(index, dummy.matrix);

    if (highlightId && shelf.shelf_id === highlightId) {{
      color.setHex(0x6ad1ff);
      highlightWorldPos = [x, y, z];
    }} else if (shelf.manual_full) {{
      color.setHex(0xdd3333);
    }} else if (shelf.placement_count > 0) {{
      color.copy(typeColor(shelf.shelf_type)).offsetHSL(0, 0.16, -0.05 + Math.min(shelf.utilization, 1) * 0.06);
    }} else {{
      color.copy(typeColor(shelf.shelf_type)).offsetHSL(0, -0.05, 0.12);
    }}
    if (shelfMesh) shelfMesh.setColorAt(index, color);

    if (placementMesh && shelf.placements.length) {{
      const baseY = y + (shelfSize.height * 0.5) + (payload.layout.placement_height * 0.5) + 0.02;
      shelf.placements.forEach((placement) => {{
        const widthScale = Math.max(0.08, (placement.width / shelf.width_cm) * shelfSize.width);
        const depthScale = Math.max(0.08, (placement.depth / shelf.depth_cm) * shelfSize.depth);
        const localX = ((placement.x + placement.width / 2) / shelf.width_cm - 0.5) * shelfSize.width;
        const localZ = ((placement.y + placement.depth / 2) / shelf.depth_cm - 0.5) * shelfSize.depth;

        dummy.position.set(x + localX, baseY, z + localZ);
        dummy.scale.set(widthScale, payload.layout.placement_height, depthScale);
        dummy.updateMatrix();
        placementMesh.setMatrixAt(placementEntries.length, dummy.matrix);
        placementEntries.push({{
          shelf_id: shelf.shelf_id,
          shelf_type: shelf.shelf_type,
          order_id: placement.order_id,
          company: placement.company,
          ship_date: placement.ship_date,
          due_date: placement.due_date,
          entry_date: placement.entry_date,
          destination: placement.destination,
          max_storage_days: placement.max_storage_days,
          rotated: placement.rotated,
          utilization: shelf.utilization,
        }});
        color.setHex(0x{safe_color});
        placementMesh.setColorAt(placementEntries.length - 1, color);
      }});
    }}
  }});

  if (shelfMesh) {{
    if (shelfMesh.instanceMatrix) shelfMesh.instanceMatrix.needsUpdate = true;
    if (shelfMesh.instanceColor) shelfMesh.instanceColor.needsUpdate = true;
    scene.add(shelfMesh);
  }}
  if (placementMesh) {{
    if (placementMesh.instanceMatrix) placementMesh.instanceMatrix.needsUpdate = true;
    if (placementMesh.instanceColor) placementMesh.instanceColor.needsUpdate = true;
    scene.add(placementMesh);
  }}

  // Uprights (raf direkleri)
  const uniqueRows = new Map();
  payload.shelves.forEach(shelf => {{
    const key = shelf.aisle_index + '-' + shelf.side_index + '-' + shelf.row_index;
    if (!uniqueRows.has(key)) uniqueRows.set(key, shelf);
  }});
  if (uniqueRows.size > 0) {{
    const uprightH = (W.shelves_per_row) * L.level_pitch + 0.15;
    const uprightW = 0.045;
    const uprightCount = uniqueRows.size * 2;
    const uprightGeo = new THREE.BoxGeometry(1, 1, 1);
    const uprightMat = new THREE.MeshStandardMaterial({{ color: 0x8fa8b8, roughness: 0.3, metalness: 0.75 }});
    const uprightMesh = new THREE.InstancedMesh(uprightGeo, uprightMat, uprightCount);
    uprightMesh.castShadow = false;
    uprightMesh.receiveShadow = true;
    let ui = 0;
    const uprightColor = new THREE.Color(0x8fa8b8);
    uniqueRows.forEach(shelf => {{
      const x = (shelf.aisle_index - 1) * P.aisle_pitch;
      const z = (shelf.row_index - 1) * P.row_pitch + (shelf.side_index === 1 ? -P.side_gap : P.side_gap);
      const shelfSize = shelfRenderSize(shelf);
      const baseY = uprightH / 2 - 0.45;
      [-1, 1].forEach(side => {{
        dummy.position.set(x + side * (shelfSize.width * 0.5 - uprightW * 0.5), baseY, z);
        dummy.scale.set(uprightW, uprightH, uprightW);
        dummy.updateMatrix();
        uprightMesh.setMatrixAt(ui, dummy.matrix);
        uprightMesh.setColorAt(ui, uprightColor);
        ui++;
      }});
    }});
    if (uprightMesh.instanceMatrix) uprightMesh.instanceMatrix.needsUpdate = true;
    if (uprightMesh.instanceColor) uprightMesh.instanceColor.needsUpdate = true;
    scene.add(uprightMesh);
  }}

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(gridSize + 20, gridSize + 20),
    new THREE.MeshStandardMaterial({{ color: 0x2c3240, roughness: 0.92, metalness: 0.05 }})
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(centerX, -0.45, centerZ);
  floor.receiveShadow = false;
  scene.add(floor);

  // If a shelf is highlighted, frame it; otherwise overview
  if (highlightWorldPos) {{
    const [hx, hy, hz] = highlightWorldPos;
    const focusDist = Math.max(8, cameraDistance * 0.35);
    camera.position.set(hx + focusDist, hy + focusDist * 0.7, hz + focusDist);
    controls.target.set(hx, hy, hz);
  }} else {{
    camera.position.set(centerX + cameraDistance, cameraDistance * 0.82, centerZ + cameraDistance * 0.95);
    controls.target.set(centerX, centerY, centerZ);
  }}
  controls.update();

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  function describeShelf(shelf) {{
    return `
      <strong>Raf:</strong> ${{shelf.shelf_id}}<br />
      <strong>Raf tipi:</strong> ${{shelf.shelf_type}}<br />
      <strong>Koridor / Taraf / Sıra / Y:</strong> ${{shelf.aisle_index}} / ${{shelf.side_index}} / ${{shelf.row_index}} / ${{shelf.y_index}}<br />
      <strong>Boyut:</strong> ${{shelf.width_cm}}×${{shelf.depth_cm}}×${{shelf.height_cm}} cm<br />
      <strong>Doluluk:</strong> ${{(shelf.utilization * 100).toFixed(1)}}%<br />
      <strong>Sipariş:</strong> ${{shelf.placement_count}}<br />
      <strong>Manuel dolu:</strong> ${{shelf.manual_full ? 'Evet' : 'Hayır'}}
    `;
  }}

  function describePlacement(entry) {{
    return `
      <strong>Sipariş:</strong> ${{entry.order_id}}<br />
      <strong>Firma:</strong> ${{entry.company}}<br />
      <strong>Hedef:</strong> ${{entry.destination || '-'}}<br />
      <strong>Termin:</strong> ${{entry.due_date || entry.ship_date}}<br />
      <strong>Sevk tarihi:</strong> ${{entry.ship_date}}<br />
      <strong>Giriş tarihi:</strong> ${{entry.entry_date || '-'}}<br />
      <strong>Raf:</strong> ${{entry.shelf_id}}<br />
      <strong>Döndürülmüş:</strong> ${{entry.rotated ? 'Evet' : 'Hayır'}}
    `;
  }}

  function onPointerMove(event) {{
    if (document.getElementById('shelf-panel').style.display !== 'none') return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);

    raycaster.setFromCamera(pointer, camera);

    const shelfHits = shelfMesh ? raycaster.intersectObject(shelfMesh, false) : [];
    const placementHits = placementMesh ? raycaster.intersectObject(placementMesh, false) : [];

    if (placementHits.length) {{
      const entry = placementEntries[placementHits[0].instanceId];
      updateTooltip(describePlacement(entry));
      return;
    }}
    if (shelfHits.length) {{
      const shelf = payload.shelves[shelfHits[0].instanceId];
      updateTooltip(describeShelf(shelf));
      return;
    }}
    updateTooltip('Bir rafın üzerine gelerek detayları görün.');
  }}

  renderer.domElement.addEventListener('pointermove', onPointerMove);
  renderer.domElement.addEventListener('pointerleave', () => updateTooltip('Bir rafın üzerine gelerek detayları görün.'));

  let _panelShelfId = null;
  let _ptrDownX = 0, _ptrDownY = 0;

  function showShelfPanel(shelf) {{
    _panelShelfId = shelf.shelf_id;
    const util = shelf.utilization;
    const utilPct = (util * 100).toFixed(1);
    const statusColor = shelf.manual_full
      ? '#e74c3c'
      : (shelf.placement_count > 0 ? '#f39c12' : '#27ae60');
    const statusText = shelf.manual_full
      ? 'Manuel Dolu'
      : (shelf.placement_count > 0 ? 'Kısmen Dolu' : 'Boş');
    const barColor = shelf.manual_full
      ? '#e74c3c'
      : (util > 0.75 ? '#f39c12' : '#4a90e2');

    let placementsHtml = '';
    if (shelf.placements && shelf.placements.length > 0) {{
      placementsHtml = `
        <div style="margin-top:12px">
          <div style="font-size:10px;color:rgba(239,244,255,0.55);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">
            Yerleşik Siparişler (${{shelf.placements.length}})
          </div>
          ${{shelf.placements.map(p => `
            <div class="panel-placement">
              <div style="font-weight:600;margin-bottom:2px">${{p.order_id}}</div>
              <div style="color:rgba(239,244,255,0.7);font-size:12px">${{p.company}} — ${{p.destination || '-'}}</div>
              <div style="color:rgba(239,244,255,0.55);font-size:11px;margin-top:2px">
                Termin ${{p.due_date || p.ship_date}} · Giriş ${{p.entry_date || '-'}} · Sevk ${{p.ship_date}}
              </div>
              <div style="color:rgba(239,244,255,0.45);font-size:11px;margin-top:2px">
                ${{p.width}}×${{p.depth}} cm${{p.rotated ? ' · döndürülmüş' : ''}}
              </div>
            </div>
          `).join('')}}
        </div>`;
    }}

    document.getElementById('shelf-panel-content').innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <div style="font-size:16px;font-weight:700;color:#fff">${{shelf.shelf_id}}</div>
        <span style="background:${{statusColor}};color:#fff;padding:3px 10px;border-radius:18px;font-size:11px;font-weight:600">
          ${{statusText}}
        </span>
      </div>
      <div style="font-size:11px;color:rgba(239,244,255,0.5);margin-bottom:8px">
        Koridor ${{shelf.aisle_index}} / Taraf ${{shelf.side_index}} / Sıra ${{shelf.row_index}} / Kat ${{shelf.y_index}}
      </div>
      <div style="font-size:12px;color:rgba(239,244,255,0.7);margin-bottom:2px">Raf Tipi — ${{shelf.shelf_type}}</div>
      <div style="font-size:12px;color:rgba(239,244,255,0.7);margin-bottom:2px">Alan Kullanımı — ${{utilPct}}%</div>
      <div class="progress-track">
        <div class="progress-fill" style="width:${{Math.min(util*100,100)}}%;background:${{barColor}}"></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div class="panel-stat">
          <div class="panel-stat-label">Sipariş Sayısı</div>
          <div class="panel-stat-value">${{shelf.placement_count}}</div>
        </div>
        <div class="panel-stat">
          <div class="panel-stat-label">Boyut (cm)</div>
          <div class="panel-stat-value" style="font-size:13px">${{shelf.width_cm}}×${{shelf.depth_cm}}×${{shelf.height_cm}}</div>
        </div>
      </div>
      ${{placementsHtml}}
    `;

    document.getElementById('tooltip').style.display = 'none';
    document.getElementById('shelf-panel').style.display = 'block';
  }}

  window.closePanel = function() {{
    document.getElementById('shelf-panel').style.display = 'none';
    document.getElementById('tooltip').style.display = 'block';
    _panelShelfId = null;
  }};

  window.manageSelf = function() {{
    if (!_panelShelfId) return;
    const id = _panelShelfId;
    const url = '/?shelf=' + encodeURIComponent(id);

    const btn = document.getElementById('manage-btn');
    if (btn) {{
      btn.textContent = 'Yönlendiriliyor...';
      btn.disabled = true;
    }}

    // 1) Asıl mekanizma: parent'taki köprüye postMessage gönder (sandbox-safe).
    try {{
      window.parent.postMessage({{ type: 'aps:select-shelf', shelf_id: id }}, '*');
    }} catch (e) {{
      console.error('postMessage failed:', e);
    }}

    // 2) Sandbox izin veriyorsa direkt navigasyonu da dene (sessiz başarısız olabilir).
    try {{ window.top.location.href = url; }} catch (e) {{}}
    try {{ window.parent.location.href = url; }} catch (e) {{}}

    // 3) 900ms içinde sayfa yenilenmediyse iframe hâlâ canlı demek →
    //    köprü yok veya çalışmıyor. Yeni sekmede aç (allow-popups her zaman vardır).
    setTimeout(function () {{
      try {{
        const w = window.open(url, '_blank');
        if (!w) {{
          // Popup engelliyse butonu manuel tıklanabilir link'e çevir.
          if (btn) {{
            btn.innerHTML = '<a href="' + url + '" target="_blank" rel="noopener" style="color:#7fc8f8;text-decoration:underline">Yeni sekmede açmak için tıkla →</a>';
            btn.disabled = false;
          }}
          return;
        }}
      }} catch (e) {{
        console.error('window.open failed:', e);
      }}
      if (btn) {{
        btn.textContent = 'Bu rafı seç ve işlem yap →';
        btn.disabled = false;
      }}
    }}, 900);
  }};

  renderer.domElement.addEventListener('pointerdown', function(event) {{
    _ptrDownX = event.clientX;
    _ptrDownY = event.clientY;
  }});

  renderer.domElement.addEventListener('pointerup', function(event) {{
    const dx = event.clientX - _ptrDownX;
    const dy = event.clientY - _ptrDownY;
    if (Math.sqrt(dx * dx + dy * dy) > 5) return;

    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
    raycaster.setFromCamera(pointer, camera);

    const placementHits = placementMesh ? raycaster.intersectObject(placementMesh, false) : [];
    const shelfHits = shelfMesh ? raycaster.intersectObject(shelfMesh, false) : [];

    if (placementHits.length) {{
      const entry = placementEntries[placementHits[0].instanceId];
      const shelf = payload.shelves.find(s => s.shelf_id === entry.shelf_id);
      if (shelf) showShelfPanel(shelf);
      return;
    }}
    if (shelfHits.length) {{
      showShelfPanel(payload.shelves[shelfHits[0].instanceId]);
    }}
  }});

  function resize() {{
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }}

  window.addEventListener('resize', resize);
  // Streamlit iframe sometimes resizes after first paint; force a few resizes
  setTimeout(resize, 100);
  setTimeout(resize, 400);

  function animate() {{
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }}

  animate();
  </script>
</body>
</html>"""
