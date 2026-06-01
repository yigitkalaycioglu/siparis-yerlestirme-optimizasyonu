from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from src.engine import (
    apply_new_configs,
    clear_all_shelves,
    clear_shelf,
    mark_shelf_manual_full,
    orders_in_date_window,
    place_order_on_shelf,
    suggest_shelves_for_order,
)
from src.models import AlgorithmConfig, Order, PackagePreset, WarehouseConfig
from src.storage import load_state, save_state
from src.visualization import build_scene_payload, render_three_html

import csv
import io
import json


st.set_page_config(page_title="Sipariş Yerleştirme Optimizasyonu", layout="wide")
st.title("Sipariş Yerleştirme Optimizasyonu")
st.caption(
    "Kişiselleştirilebilir depo parametreleri, santimetre bazlı raf yerleşimi ve taşıyıcı için raf öneri motoru"
)

# ── Iframe → parent köprüsü ───────────────────────────────────────────────
# components.html iframe'i 'allow-top-navigation' sandbox bayrağı olmadan render
# edildiği için window.parent.location.href atama sessizce engelleniyor. iframe
# bunun yerine postMessage gönderiyor; aşağıdaki <script> parent context'te bir
# kerelik dinleyici kurarak URL'yi günceller ve sayfayı aynı sekmede yeniler.
#
# Not: Streamlit 1.56'da st.html DOMPurify ile event handler attribute'larını
# (onload, onerror, vb.) siler, ama <script> tag'lerini koruyup yeniden create
# eder (unsafe_allow_javascript=True ile). Bu yüzden script tag kullanıyoruz.
_BRIDGE_HTML = """
<script>
(function() {
  if (window.__apsBridgeInstalled) return;
  window.__apsBridgeInstalled = true;
  window.addEventListener('message', function(e) {
    var d = e && e.data;
    if (!d || d.type !== 'aps:select-shelf' || !d.shelf_id) return;
    try {
      var u = new URL(window.location.href);
      u.searchParams.set('shelf', d.shelf_id);
      window.location.href = u.toString();
    } catch (err) {
      window.location.search = '?shelf=' + encodeURIComponent(d.shelf_id);
    }
  });
})();
</script>
"""
if hasattr(st, "html"):
    try:
        st.html(_BRIDGE_HTML, unsafe_allow_javascript=True)
    except TypeError:
        st.html(_BRIDGE_HTML)
else:
    st.markdown(_BRIDGE_HTML, unsafe_allow_html=True)

# ── Session state defaults ─────────────────────────────────────────────────
if "state" not in st.session_state:
    st.session_state.state = load_state()

if "confirm_clear_all_shelves" not in st.session_state:
    st.session_state.confirm_clear_all_shelves = False

if "shelf_mgmt_override" not in st.session_state:
    st.session_state.shelf_mgmt_override = None

if "active_view" not in st.session_state:
    st.session_state.active_view = "Sipariş Yerleştir"

if "package_preset_choice" not in st.session_state:
    st.session_state.package_preset_choice = "Yeni Ekle +"
if "package_preset_last_applied" not in st.session_state:
    st.session_state.package_preset_last_applied = ""
if "package_preset_pending_choice" not in st.session_state:
    st.session_state.package_preset_pending_choice = ""
if "new_package_preset_label" not in st.session_state:
    st.session_state.new_package_preset_label = ""
if "new_package_preset_label_pending_reset" not in st.session_state:
    st.session_state.new_package_preset_label_pending_reset = False
if "order_order_id" not in st.session_state:
    st.session_state.order_order_id = f"ORD-{uuid4().hex[:8].upper()}"
if "order_product_width_cm" not in st.session_state:
    st.session_state.order_product_width_cm = 100
if "order_product_depth_cm" not in st.session_state:
    st.session_state.order_product_depth_cm = 100
if "order_pallet_width_cm" not in st.session_state:
    st.session_state.order_pallet_width_cm = 80
if "order_pallet_depth_cm" not in st.session_state:
    st.session_state.order_pallet_depth_cm = 120
if "order_company" not in st.session_state:
    st.session_state.order_company = "Örnek Firma"
if "order_ship_date" not in st.session_state:
    st.session_state.order_ship_date = date.today()

# 3B sekmesi durumu (filtre vs.)
if "view3d_aisles" not in st.session_state:
    st.session_state.view3d_aisles = None
if "view3d_levels" not in st.session_state:
    st.session_state.view3d_levels = None
if "view3d_only_occupied" not in st.session_state:
    st.session_state.view3d_only_occupied = False
if "view3d_show_placements" not in st.session_state:
    st.session_state.view3d_show_placements = True
if "view3d_color" not in st.session_state:
    st.session_state.view3d_color = "#27ae60"

# 3B sahnesinden gelen raf seçimi ?shelf=X ile geldiyse uygun sekmeye geç
_shelf_from_url = st.query_params.get("shelf", "")
if _shelf_from_url:
    st.session_state.shelf_mgmt_override = _shelf_from_url
    st.session_state.active_view = "3B Görünüm"
    st.query_params.clear()
    st.rerun()

state = st.session_state.state

# ── Sidebar: Sadece fabrika parametreleri ──────────────────────────────────
with st.sidebar:
    st.header("Fabrika Parametreleri")
    st.markdown(
        "Depo topolojisi ve algoritma parametreleri burada ayarlanır. "
        "Değişiklikleri kaydetmeyi unutmayın."
    )

    with st.form("warehouse_config_form"):
        st.subheader("Depo Topolojisi")
        st.caption("Koridor/sıra/raf sayıları, raf başına fiziksel ölçüler.")
        aisles = st.number_input("Koridor sayısı", min_value=1, value=state.warehouse_config.aisles)
        sides_per_aisle = st.number_input(
            "Koridor başına taraf sayısı", min_value=1, value=state.warehouse_config.sides_per_aisle
        )
        rows_per_side = st.number_input(
            "Taraf başına sıra sayısı", min_value=1, value=state.warehouse_config.rows_per_side
        )
        shelves_per_row = st.number_input(
            "Sıra başına Y düzlemi raf adedi", min_value=1, value=state.warehouse_config.shelves_per_row
        )

        st.subheader("Raf Ölçüleri (cm)")
        shelf_width_cm = st.number_input(
            "Raf genişliği", min_value=10, value=state.warehouse_config.shelf_width_cm
        )
        shelf_depth_cm = st.number_input(
            "Raf derinliği", min_value=10, value=state.warehouse_config.shelf_depth_cm
        )
        shelf_height_cm = st.number_input(
            "Raf yüksekliği", min_value=10, value=state.warehouse_config.shelf_height_cm
        )

        st.subheader("Güvenlik Payları (cm)")
        st.caption("Palet/ürün etrafındaki minimum boşluk.")
        clearance_width_cm = st.number_input(
            "Genişlik güvenlik payı", min_value=0, value=state.warehouse_config.clearance_width_cm
        )
        clearance_depth_cm = st.number_input(
            "Derinlik güvenlik payı", min_value=0, value=state.warehouse_config.clearance_depth_cm
        )

        st.subheader("Referans Min Palet")
        smallest_pallet_width_cm = st.number_input(
            "Min palet genişliği", min_value=1, value=state.warehouse_config.smallest_pallet_width_cm
        )
        smallest_pallet_depth_cm = st.number_input(
            "Min palet derinliği", min_value=1, value=state.warehouse_config.smallest_pallet_depth_cm
        )

        st.subheader("Algoritma Parametreleri")
        allow_rotation = st.checkbox("Palet döndürmeye izin ver", value=state.algorithm_config.allow_rotation)
        cluster_same_company = st.checkbox(
            "Aynı firmayı yakın raflarda kümelendir", value=state.algorithm_config.cluster_same_company
        )
        cluster_same_ship_date = st.checkbox(
            "Yakın sevk tarihlerini kümelendir", value=state.algorithm_config.cluster_same_ship_date
        )
        ship_date_cluster_days = st.number_input(
            "Sevk tarihi kümeleme günü", min_value=0, value=state.algorithm_config.ship_date_cluster_days
        )

        weight_fill_efficiency = st.slider(
            "Doluluk/verim ağırlığı", 0.0, 1.0,
            value=float(state.algorithm_config.weight_fill_efficiency), step=0.01,
        )
        weight_travel_distance = st.slider(
            "Mesafe ağırlığı", 0.0, 1.0,
            value=float(state.algorithm_config.weight_travel_distance), step=0.01,
        )
        weight_company_cluster = st.slider(
            "Firma kümeleme ağırlığı", 0.0, 1.0,
            value=float(state.algorithm_config.weight_company_cluster), step=0.01,
        )
        weight_date_cluster = st.slider(
            "Tarih kümelenme ağırlığı", 0.0, 1.0,
            value=float(state.algorithm_config.weight_date_cluster), step=0.01,
        )
        weight_balance = st.slider(
            "Dengeleme ağırlığı", 0.0, 1.0,
            value=float(state.algorithm_config.weight_balance), step=0.01,
        )
        top_k_suggestions = st.number_input(
            "Öneri adedi", min_value=1, max_value=25, value=state.algorithm_config.top_k_suggestions
        )
        min_fragment_cm2 = st.number_input(
            "Minimum kullanılabilir parça alanı (cm2)",
            min_value=1, value=state.algorithm_config.min_fragment_cm2,
        )

        rebuild_if_needed = st.checkbox(
            "Topoloji değiştiyse depoyu sıfırlayarak yeniden kur",
            value=False,
            help="Açık ise tüm raf dolulukları ve siparişler temizlenir.",
        )

        save_config = st.form_submit_button("Parametreleri Kaydet")

    if save_config:
        new_warehouse = WarehouseConfig(
            aisles=int(aisles),
            sides_per_aisle=int(sides_per_aisle),
            rows_per_side=int(rows_per_side),
            shelves_per_row=int(shelves_per_row),
            shelf_width_cm=int(shelf_width_cm),
            shelf_depth_cm=int(shelf_depth_cm),
            shelf_height_cm=int(shelf_height_cm),
            clearance_width_cm=int(clearance_width_cm),
            clearance_depth_cm=int(clearance_depth_cm),
            smallest_pallet_width_cm=int(smallest_pallet_width_cm),
            smallest_pallet_depth_cm=int(smallest_pallet_depth_cm),
        )
        new_algorithm = AlgorithmConfig(
            allow_rotation=allow_rotation,
            cluster_same_company=cluster_same_company,
            cluster_same_ship_date=cluster_same_ship_date,
            ship_date_cluster_days=int(ship_date_cluster_days),
            weight_fill_efficiency=float(weight_fill_efficiency),
            weight_travel_distance=float(weight_travel_distance),
            weight_company_cluster=float(weight_company_cluster),
            weight_date_cluster=float(weight_date_cluster),
            weight_balance=float(weight_balance),
            top_k_suggestions=int(top_k_suggestions),
            min_fragment_cm2=int(min_fragment_cm2),
        )
        state = apply_new_configs(state, new_warehouse, new_algorithm, rebuild_if_needed=rebuild_if_needed)
        st.session_state.state = state
        # Filtre defaultlarını yeni topolojiye göre sıfırla
        st.session_state.view3d_aisles = None
        st.session_state.view3d_levels = None
        save_state(state)
        st.success("Parametreler kaydedildi.")

# ── Üst özet metrikleri ───────────────────────────────────────────────────
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.metric("Toplam raf", len(state.shelves))
with col_b:
    used_count = sum(1 for shelf in state.shelves if shelf.placements)
    st.metric("Kullanılan raf", used_count)
with col_c:
    blocked_count = sum(1 for shelf in state.shelves if shelf.manual_full)
    st.metric("Manuel dolu raf", blocked_count)
with col_d:
    st.metric("Yerleşen sipariş", len(state.orders))

# ── Görünüm seçici: programatik geçiş için segmented_control (fallback: radio)
_view_options = ["Sipariş Yerleştir", "3B Görünüm", "Raf Yönetimi", "Durum Analizi"]
if hasattr(st, "segmented_control"):
    selected = st.segmented_control(
        "Görünüm",
        options=_view_options,
        label_visibility="collapsed",
        key="active_view",
    )
else:
    selected = st.radio(
        "Görünüm",
        options=_view_options,
        horizontal=True,
        label_visibility="collapsed",
        key="active_view",
    )

view = selected or "Sipariş Yerleştir"

st.markdown("---")

# =================================================================
# Sipariş Yerleştir
# =================================================================
if view == "Sipariş Yerleştir":
    st.subheader("Yeni Sipariş")
    st.info(
        "Hazır paket seçebilir, yeni ölçü girebilir veya mevcut ölçüleri preset olarak kaydedebilirsiniz. "
        "Yerleştirme başarılıysa durum kaydedilir."
    )

    preset_options = ["Yeni Ekle +"] + [preset.label for preset in state.package_presets]

    pending_preset_choice = st.session_state.package_preset_pending_choice
    if pending_preset_choice:
        st.session_state.package_preset_choice = pending_preset_choice if pending_preset_choice in preset_options else "Yeni Ekle +"
        st.session_state.package_preset_pending_choice = ""

    if st.session_state.new_package_preset_label_pending_reset:
        st.session_state.new_package_preset_label = ""
        st.session_state.new_package_preset_label_pending_reset = False

    selected_preset_label = st.selectbox("Hazır paket ölçüsü", options=preset_options, key="package_preset_choice")

    if selected_preset_label != "Yeni Ekle +":
        selected_preset = next((preset for preset in state.package_presets if preset.label == selected_preset_label), None)
        if selected_preset and st.session_state.package_preset_last_applied != selected_preset_label:
            st.session_state.order_product_width_cm = selected_preset.product_width_cm
            st.session_state.order_product_depth_cm = selected_preset.product_depth_cm
            st.session_state.order_pallet_width_cm = selected_preset.pallet_width_cm
            st.session_state.order_pallet_depth_cm = selected_preset.pallet_depth_cm
            st.session_state.package_preset_last_applied = selected_preset_label
            st.rerun()

    if selected_preset_label == "Yeni Ekle +":
        st.caption("Yeni bir hazır paket oluşturmak için aşağıdaki ölçüleri girin ve kaydedin.")

    order_id = st.text_input("Sipariş kodu", key="order_order_id")
    c1, c2 = st.columns(2)
    with c1:
        product_width_cm = st.number_input(
            "Ürün genişliği (cm)", min_value=1, key="order_product_width_cm"
        )
        pallet_width_cm = st.number_input("Palet genişliği (cm)", min_value=1, key="order_pallet_width_cm")
    with c2:
        product_depth_cm = st.number_input("Ürün derinliği (cm)", min_value=1, key="order_product_depth_cm")
        pallet_depth_cm = st.number_input("Palet derinliği (cm)", min_value=1, key="order_pallet_depth_cm")
    company = st.text_input("Firma", key="order_company")
    ship_date = st.date_input("Sevk tarihi", key="order_ship_date")

    if selected_preset_label == "Yeni Ekle +":
        with st.container(border=True):
            st.markdown("##### Hazır Paket Kaydet")
            st.caption("Bu alan, aşağıdaki mevcut ölçüleri bir şablon olarak saklar.")
            preset_label = st.text_input(
                "Hazır paket adı",
                key="new_package_preset_label",
                placeholder="Örn. Standart 80x120",
            )
            save_preset = st.button("Paketi Kaydet", key="save_package_preset")
            if save_preset:
                normalized_label = preset_label.strip()
                if not normalized_label:
                    st.error("Hazır paket adı boş olamaz.")
                elif any(preset.label == normalized_label for preset in state.package_presets):
                    st.error("Bu isimde bir hazır paket zaten kayıtlı.")
                else:
                    state.package_presets.append(
                        PackagePreset(
                            label=normalized_label,
                            product_width_cm=int(product_width_cm),
                            product_depth_cm=int(product_depth_cm),
                            pallet_width_cm=int(pallet_width_cm),
                            pallet_depth_cm=int(pallet_depth_cm),
                        )
                    )
                    save_state(state)
                    st.session_state.package_preset_pending_choice = normalized_label
                    st.session_state.package_preset_last_applied = ""
                    st.session_state.new_package_preset_label_pending_reset = True
                    st.success(f'"{normalized_label}" hazır paketi kaydedildi.')
                    st.rerun()

    submit_order = st.button("Uygun Raf Öner ve Yerleştir")

    if submit_order:
        order = Order(
            order_id=order_id.strip(),
            product_width_cm=int(product_width_cm),
            product_depth_cm=int(product_depth_cm),
            pallet_width_cm=int(pallet_width_cm),
            pallet_depth_cm=int(pallet_depth_cm),
            company=company.strip(),
            ship_date=ship_date.strftime("%Y-%m-%d"),
        )

        suggestions = suggest_shelves_for_order(state, order)
        if not suggestions:
            st.error(
                "Bu sipariş için uygun raf bulunamadı. "
                "Ürün ölçüsü raf ölçüsünden büyük olabilir veya tüm raflar dolu."
            )
        else:
            best = suggestions[0]
            ok, message = place_order_on_shelf(
                state, order,
                shelf_id=best["shelf_id"],
                free_rect_index=best["free_rect_index"],
            )
            if ok:
                save_state(state)
                st.success(f"Önerilen raf: **{best['shelf_id']}**. {message}")
                st.caption("3B Görünüm sekmesinde sonucu görebilirsiniz.")
            else:
                st.error(message)

            st.markdown("### En İyi Raf Adayları")
            st.dataframe(suggestions, width="stretch")

    st.markdown("---")
    st.subheader("Toplu Sipariş Yükle (CSV veya JSON)")
    st.info(
        "Alanlar: order_id, product_width_cm, product_depth_cm, pallet_width_cm, "
        "pallet_depth_cm, company, ship_date (YYYY-MM-DD)."
    )

    uploaded_file = st.file_uploader("Veri dosyası seçin", type=["csv", "json"], key="dataset_uploader")

    def _parse_orders_from_file(uploaded) -> tuple[list[Order], list[dict]]:
        """Parses orders and returns (parsed_orders, parse_errors)."""
        if not uploaded:
            return [], []
        content = uploaded.read()
        try:
            text = content.decode("utf-8-sig")
        except Exception:
            try:
                text = content.decode("utf-8")
            except Exception:
                text = content.decode("latin-1")

        orders_list: list[dict] = []
        errors: list[dict] = []

        try:
            if uploaded.name.lower().endswith(".json"):
                data = json.loads(text)
                if isinstance(data, dict):
                    for key in ("orders", "data", "items"):
                        if key in data and isinstance(data[key], list):
                            orders_list = data[key]
                            break
                    else:
                        orders_list = [data]
                elif isinstance(data, list):
                    orders_list = data
                else:
                    errors.append({"row": 0, "error": "Beklenmedik JSON yapısı."})
            else:
                f = io.StringIO(text)
                reader = csv.DictReader(f)
                for row in reader:
                    orders_list.append(row)
        except Exception as exc:
            errors.append({"row": 0, "error": f"Dosya çözümlenemedi: {exc}"})
            return [], errors

        parsed: list[Order] = []
        for i, item in enumerate(orders_list, start=1):
            try:
                parsed.append(
                    Order(
                        order_id=str(item.get("order_id", "")).strip() or f"ORD-{uuid4().hex[:8].upper()}",
                        product_width_cm=int(float(item.get("product_width_cm") or item.get("product_width") or 0)),
                        product_depth_cm=int(float(item.get("product_depth_cm") or item.get("product_depth") or 0)),
                        pallet_width_cm=int(float(item.get("pallet_width_cm") or item.get("pallet_width") or 0)),
                        pallet_depth_cm=int(float(item.get("pallet_depth_cm") or item.get("pallet_depth") or 0)),
                        company=str(item.get("company", "")).strip() or "-",
                        ship_date=str(item.get("ship_date", "")).strip() or date.today().strftime("%Y-%m-%d"),
                    )
                )
            except Exception as exc:
                errors.append({"row": i, "order_id": str(item.get("order_id", "?")), "error": str(exc)})
        return parsed, errors

    parsed_orders, parse_errors = _parse_orders_from_file(uploaded_file)

    if parse_errors:
        st.warning(f"{len(parse_errors)} satır okunamadı.")
        with st.expander("Hatalı satırları göster"):
            st.dataframe(parse_errors, width="stretch")

    if parsed_orders:
        st.success(f"Yüklenen geçerli sipariş sayısı: {len(parsed_orders)}")
        preview = [vars(o) for o in parsed_orders]
        st.dataframe(preview, width="stretch")

        place_mode = st.radio(
            "Yerleştirme modu",
            ["Otomatik (en iyi öneriye göre)", "Manuel (her sipariş için seçim)"],
        )

        if place_mode.startswith("Otomatik"):
            if st.button("Tümünü Otomatik Yerleştir"):
                results: list[dict] = []
                placed = 0
                for o in parsed_orders:
                    suggestions = suggest_shelves_for_order(state, o)
                    if not suggestions:
                        results.append({"order_id": o.order_id, "status": "Öneri yok"})
                        continue
                    best = suggestions[0]
                    ok, msg = place_order_on_shelf(
                        state, o, shelf_id=best["shelf_id"], free_rect_index=best["free_rect_index"]
                    )
                    if ok:
                        placed += 1
                        results.append({"order_id": o.order_id, "status": "Yerleştirildi", "shelf": best["shelf_id"]})
                    else:
                        results.append({"order_id": o.order_id, "status": f"Hata: {msg}"})
                save_state(state)
                st.success(f"{placed}/{len(parsed_orders)} sipariş yerleştirildi.")
                st.dataframe(results, width="stretch")
        else:
            st.write("Her sipariş için öneriler ve manuel yerleştirme düğmeleri")
            for o in parsed_orders:
                st.markdown(f"**Sipariş:** {o.order_id} — Firma: {o.company} — Sevk: {o.ship_date}")
                suggestions = suggest_shelves_for_order(state, o)
                if not suggestions:
                    st.warning("Bu sipariş için öneri bulunamadı.")
                    continue

                st.dataframe(suggestions, width="stretch")
                choices = [f"{s['shelf_id']} (free_rect={s['free_rect_index']})" for s in suggestions]
                sel = st.selectbox(f"Yerleştirilecek raf — {o.order_id}", options=choices, key=f"select_{o.order_id}")
                if st.button(f"Bu siparişi yerleştir — {o.order_id}", key=f"place_{o.order_id}"):
                    idx = choices.index(sel)
                    cand = suggestions[idx]
                    ok, msg = place_order_on_shelf(
                        state, o, shelf_id=cand["shelf_id"], free_rect_index=cand["free_rect_index"]
                    )
                    if ok:
                        save_state(state)
                        st.success(f"{o.order_id} yerleştirildi: {cand['shelf_id']}")
                    else:
                        st.error(msg)

# =================================================================
# 3B Görünüm
# =================================================================
elif view == "3B Görünüm":
    aisle_options = list(range(1, state.warehouse_config.aisles + 1))
    level_max = state.warehouse_config.shelves_per_row

    # Filtreler – sekme içinde
    with st.expander("Filtreler ve Görüntü Ayarları", expanded=False):
        fc1, fc2 = st.columns([2, 1])
        with fc1:
            default_aisles = st.session_state.view3d_aisles or aisle_options
            default_aisles = [a for a in default_aisles if a in aisle_options] or aisle_options
            selected_aisles = st.multiselect(
                "Gösterilecek koridorlar",
                options=aisle_options,
                default=default_aisles,
                key="multi_aisles",
            )
            st.session_state.view3d_aisles = selected_aisles
        with fc2:
            default_levels = st.session_state.view3d_levels or (1, level_max)
            level_range = st.slider(
                "Y raf aralığı",
                min_value=1,
                max_value=level_max,
                value=(min(default_levels[0], level_max), min(default_levels[1], level_max)),
                key="slider_levels",
            )
            st.session_state.view3d_levels = level_range

        fc3, fc4, fc5 = st.columns(3)
        with fc3:
            show_only_occupied = st.checkbox(
                "Sadece dolu/kilitli raflar",
                value=st.session_state.view3d_only_occupied,
                key="cb_only_occupied",
            )
            st.session_state.view3d_only_occupied = show_only_occupied
        with fc4:
            show_placements = st.checkbox(
                "Sipariş bloklarını göster",
                value=st.session_state.view3d_show_placements,
                key="cb_show_placements",
            )
            st.session_state.view3d_show_placements = show_placements
        with fc5:
            raw_color = st.color_picker(
                "Sipariş kutu rengi", value=st.session_state.view3d_color, key="cp_color"
            )
            st.session_state.view3d_color = raw_color

    filtered_aisles = selected_aisles or aisle_options
    placement_color = (raw_color or "#27ae60").lstrip("#")

    # 3B render
    payload = build_scene_payload(
        state,
        selected_aisles=list(filtered_aisles),
        level_range=level_range,
        show_only_occupied=show_only_occupied,
        show_placements=show_placements,
        highlight_shelf_id=st.session_state.shelf_mgmt_override or None,
    )

    components.html(render_three_html(payload, placement_color), height=720, scrolling=False)

    # Seçili raf işlem paneli (3B'den gelen tıklama veya manuel seçim)
    selected_id = st.session_state.shelf_mgmt_override
    if selected_id:
        selected_shelf = next((s for s in state.shelves if s.shelf_id == selected_id), None)
        if selected_shelf is None:
            st.warning(f"Seçili raf bulunamadı: {selected_id}")
            if st.button("Seçimi temizle", key="clear_sel_3d_missing"):
                st.session_state.shelf_mgmt_override = None
                st.rerun()
        else:
            st.markdown("---")
            util_pct = selected_shelf.utilization * 100
            if selected_shelf.manual_full:
                badge_color, badge_text = "#e74c3c", "Manuel Dolu"
            elif selected_shelf.placements:
                badge_color, badge_text = "#f39c12", "Kısmen Dolu"
            else:
                badge_color, badge_text = "#27ae60", "Boş"

            with st.container(border=True):
                tc, bc = st.columns([3, 1])
                with tc:
                    st.markdown(f"### Seçili Raf: {selected_shelf.shelf_id}")
                    st.caption(
                        f"Koridor {selected_shelf.aisle_index} │ Taraf {selected_shelf.side_index} │ "
                        f"Sıra {selected_shelf.row_index} │ Kat {selected_shelf.y_index}"
                    )
                with bc:
                    st.markdown(
                        f'<div style="text-align:right;margin-top:10px">'
                        f'<span style="background:{badge_color};color:white;padding:4px 14px;'
                        f'border-radius:20px;font-size:13px;font-weight:600">{badge_text}</span></div>',
                        unsafe_allow_html=True,
                    )

                st.progress(min(selected_shelf.utilization, 1.0), text=f"Alan kullanımı %{util_pct:.1f}")

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Yerleşen Sipariş", len(selected_shelf.placements))
                with m2:
                    st.metric("Boş Alan", f"{selected_shelf.free_area:,} cm²")
                with m3:
                    st.metric("Toplam Alan", f"{selected_shelf.area:,} cm²")

                if selected_shelf.placements:
                    with st.expander(f"Yerleşik Siparişler ({len(selected_shelf.placements)})"):
                        for p in selected_shelf.placements:
                            st.markdown(
                                f"**{p.order_id}** — {p.company} │ {p.ship_date} │ "
                                f"{p.width}×{p.depth} cm" + (" (döndürülmüş)" if p.rotated else "")
                            )

                a1, a2, a3, a4 = st.columns(4)
                with a1:
                    if st.button("Rafı DOLU İşaretle", type="primary", use_container_width=True, key="b3d_full"):
                        ok, message = mark_shelf_manual_full(state, selected_id, True)
                        if ok:
                            save_state(state)
                            st.success(message)
                        else:
                            st.error(message)
                with a2:
                    if st.button("Rafı Tekrar AÇ", use_container_width=True, key="b3d_open"):
                        ok, message = mark_shelf_manual_full(state, selected_id, False)
                        if ok:
                            save_state(state)
                            st.success(message)
                        else:
                            st.error(message)
                with a3:
                    if st.button("Rafı BOŞALT", use_container_width=True, key="b3d_clear"):
                        ok, message = clear_shelf(state, selected_id)
                        if ok:
                            save_state(state)
                            st.success(message)
                        else:
                            st.error(message)
                with a4:
                    if st.button("Seçimi Bırak", use_container_width=True, key="b3d_drop"):
                        st.session_state.shelf_mgmt_override = None
                        st.rerun()
    else:
        st.caption("Bir raf seçmek için 3B sahnesinden tıklayın; raf detay panelinde 'Bu rafı seç' düğmesini kullanın.")

# =================================================================
# Raf Yönetimi
# =================================================================
elif view == "Raf Yönetimi":
    st.subheader("Taşıyıcı Müdahalesi")
    st.info(
        "Hızlı raf arama, manuel dolu/aç ve raf temizleme bu görünümde yapılır. "
        "3B Görünüm sekmesinden tıklanan raflar burada da otomatik seçilir."
    )
    shelf_ids = [shelf.shelf_id for shelf in state.shelves]

    _shelf_override = st.session_state.shelf_mgmt_override

    if _shelf_override:
        if _shelf_override in shelf_ids:
            st.success(f"Seçili raf: **{_shelf_override}**")
            selected_shelf = _shelf_override
        else:
            st.warning(f"Bu raf kodu bulunamadı: `{_shelf_override}`")
            st.session_state.shelf_mgmt_override = None
            selected_shelf = shelf_ids[0] if shelf_ids else None
        if st.button("← Raf Aramasına Dön"):
            st.session_state.shelf_mgmt_override = None
            st.rerun()
    else:
        st.markdown("### Hızlı Raf Seçimi")
        quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
        with quick_col1:
            quick_aisle = st.number_input(
                "Koridor (A)", min_value=1, max_value=state.warehouse_config.aisles, value=1, step=1,
            )
        with quick_col2:
            quick_side = st.number_input(
                "Taraf (S)", min_value=1, max_value=state.warehouse_config.sides_per_aisle, value=1, step=1,
            )
        with quick_col3:
            quick_row = st.number_input(
                "Sıra (R)", min_value=1, max_value=state.warehouse_config.rows_per_side, value=1, step=1,
            )
        with quick_col4:
            quick_y = st.number_input(
                "Y Raf (Y)", min_value=1, max_value=state.warehouse_config.shelves_per_row, value=1, step=1,
            )

        quick_shelf_id = f"A{int(quick_aisle):02d}-S{int(quick_side):02d}-R{int(quick_row):03d}-Y{int(quick_y):02d}"
        st.caption(f"Hızlı seçim kodu: **{quick_shelf_id}**")

        search_text = st.text_input("Raf kodunda ara", value=quick_shelf_id)
        filtered_shelf_ids = [sid for sid in shelf_ids if search_text.strip().upper() in sid.upper()]
        if not filtered_shelf_ids:
            st.warning("Arama kriterine uyan raf yok. Tüm raf listesi gösterildi.")
            filtered_shelf_ids = shelf_ids

        selected_shelf = st.selectbox("Raf seç", options=filtered_shelf_ids)

    selected_state = next((s for s in state.shelves if s.shelf_id == selected_shelf), None) if selected_shelf else None

    if selected_state is not None:
        util_pct = selected_state.utilization * 100
        if selected_state.manual_full:
            badge_color, badge_text = "#e74c3c", "Manuel Dolu"
        elif selected_state.placements:
            badge_color, badge_text = "#f39c12", "Kısmen Dolu"
        else:
            badge_color, badge_text = "#27ae60", "Boş"

        with st.container(border=True):
            title_col, badge_col = st.columns([3, 1])
            with title_col:
                st.markdown(f"### {selected_state.shelf_id}")
            with badge_col:
                st.markdown(
                    f'<div style="text-align:right;margin-top:10px">'
                    f'<span style="background:{badge_color};color:white;padding:4px 14px;'
                    f'border-radius:20px;font-size:13px;font-weight:600">{badge_text}</span></div>',
                    unsafe_allow_html=True,
                )

            st.caption(
                f"Koridor {selected_state.aisle_index} │ Taraf {selected_state.side_index} │ "
                f"Sıra {selected_state.row_index} │ Kat {selected_state.y_index}"
            )

            st.progress(min(selected_state.utilization, 1.0), text=f"Alan kullanımı %{util_pct:.1f}")

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Sipariş", len(selected_state.placements))
            with m2:
                st.metric("Boş Alan", f"{selected_state.free_area:,} cm²")
            with m3:
                st.metric("Toplam Alan", f"{selected_state.area:,} cm²")
            with m4:
                st.metric("Manuel Dolu", "Evet" if selected_state.manual_full else "Hayır")

            if selected_state.placements:
                with st.expander(f"Yerleşik Siparişler ({len(selected_state.placements)})", expanded=True):
                    for p in selected_state.placements:
                        pc1, pc2 = st.columns([2, 3])
                        with pc1:
                            st.markdown(f"**{p.order_id}**")
                        with pc2:
                            st.caption(
                                f"{p.company} │ {p.ship_date} │ {p.width}×{p.depth} cm"
                                + (" (döndürülmüş)" if p.rotated else "")
                            )
            else:
                st.info("Bu rafta henüz sipariş yok.")

        st.markdown("**Raf İşlemleri:**")
        full_col, free_col, clear_col = st.columns(3)
        with full_col:
            if st.button("Rafı DOLU İşaretle", type="primary", use_container_width=True):
                ok, message = mark_shelf_manual_full(state, selected_shelf, True)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)
        with free_col:
            if st.button("Rafı Tekrar AÇ", use_container_width=True):
                ok, message = mark_shelf_manual_full(state, selected_shelf, False)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)
        with clear_col:
            if st.button("Rafı BOŞALT", use_container_width=True):
                ok, message = clear_shelf(state, selected_shelf)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)

        st.markdown("---")

    st.markdown("### Toplu İşlem")
    warn_col, action_col = st.columns([2, 1])
    with warn_col:
        st.warning("Bu işlem tüm raflardaki yerleşimleri siler ve geri alınamaz.")
    with action_col:
        if st.button("Tüm rafları BOŞALT (Onay Sor)"):
            st.session_state.confirm_clear_all_shelves = True

    if st.session_state.confirm_clear_all_shelves:
        st.error("Emin misiniz? Bu işlem bütün rafları ve tüm sipariş kayıtlarını sıfırlar.")
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button("Evet, tüm rafları boşalt"):
                ok, message = clear_all_shelves(state)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)
                st.session_state.confirm_clear_all_shelves = False
                st.rerun()
        with cancel_col:
            if st.button("Vazgeç"):
                st.session_state.confirm_clear_all_shelves = False
                st.info("Toplu boşaltma iptal edildi.")

# =================================================================
# Durum Analizi
# =================================================================
elif view == "Durum Analizi":
    st.subheader("Operasyon Özeti")
    st.info("Depo kullanım oranı, toplam sipariş sayısı ve tarih kümelenme özetleri.")
    total_area = sum(s.area for s in state.shelves)
    used_area = sum(s.used_area for s in state.shelves)
    utilization = (used_area / total_area) if total_area else 0.0

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Genel alan kullanımı", f"{utilization * 100:.2f}%")
    with m2:
        st.metric("Toplam yerleşen sipariş", len(state.orders))
    with m3:
        avg_per_shelf = (len(state.orders) / max(1, sum(1 for s in state.shelves if s.placements)))
        st.metric("Dolu raf başına ort. sipariş", f"{avg_per_shelf:.2f}")

    if state.orders:
        closest_date = state.orders[-1].ship_date
        near_count = orders_in_date_window(state, closest_date, state.algorithm_config.ship_date_cluster_days)
        st.info(
            f"Son sipariş tarihi çevresinde (±{state.algorithm_config.ship_date_cluster_days} gün) "
            f"toplam {near_count} sipariş var."
        )

    st.markdown("### En Dolu 20 Raf")
    top_shelves = sorted(state.shelves, key=lambda s: s.utilization, reverse=True)[:20]
    rows = [
        {
            "shelf_id": s.shelf_id,
            "utilization": round(s.utilization, 3),
            "order_count": len(s.placements),
            "manual_full": s.manual_full,
            "aisle": s.aisle_index,
            "row": s.row_index,
            "y": s.y_index,
        }
        for s in top_shelves
    ]
    st.dataframe(rows, width="stretch")

    # Firma dağılımı
    if state.orders:
        from collections import Counter
        company_counts = Counter(o.company for o in state.orders)
        st.markdown("### Firma Bazında Sipariş Dağılımı (ilk 15)")
        company_rows = [
            {"company": c, "order_count": n}
            for c, n in company_counts.most_common(15)
        ]
        st.dataframe(company_rows, width="stretch")
