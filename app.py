from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st

from src.engine import (
    apply_new_configs,
    clear_all_shelves,
    clear_shelf,
    mark_shelf_manual_full,
    orders_in_date_window,
    place_order_on_shelf,
    suggest_shelves_for_order,
)
from src.models import AlgorithmConfig, Order, WarehouseConfig
from src.storage import load_state, save_state


st.set_page_config(page_title="Sipariş Yerleştirme Optimizasyonu", layout="wide")
st.title("Sipariş Yerleştirme Optimizasyonu")
st.caption(
    "Kişiselleştirilebilir depo parametreleri, santimetre bazlı raf yerleşimi ve taşıyıcı için raf öneri motoru"
)

if "state" not in st.session_state:
    st.session_state.state = load_state()

if "confirm_clear_all_shelves" not in st.session_state:
    st.session_state.confirm_clear_all_shelves = False

state = st.session_state.state

with st.sidebar:
    st.header("Fabrika Parametreleri")

    with st.form("warehouse_config_form"):
        st.subheader("Depo Topolojisi")
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
            "Doluluk/verim ağırlığı",
            0.0,
            1.0,
            value=float(state.algorithm_config.weight_fill_efficiency),
            step=0.01,
        )
        weight_travel_distance = st.slider(
            "Mesafe ağırlığı",
            0.0,
            1.0,
            value=float(state.algorithm_config.weight_travel_distance),
            step=0.01,
        )
        weight_company_cluster = st.slider(
            "Firma kümeleme ağırlığı",
            0.0,
            1.0,
            value=float(state.algorithm_config.weight_company_cluster),
            step=0.01,
        )
        weight_date_cluster = st.slider(
            "Tarih kümeleme ağırlığı",
            0.0,
            1.0,
            value=float(state.algorithm_config.weight_date_cluster),
            step=0.01,
        )
        weight_balance = st.slider(
            "Dengeleme ağırlığı",
            0.0,
            1.0,
            value=float(state.algorithm_config.weight_balance),
            step=0.01,
        )
        top_k_suggestions = st.number_input(
            "Öneri adedi", min_value=1, max_value=25, value=state.algorithm_config.top_k_suggestions
        )
        min_fragment_cm2 = st.number_input(
            "Minimum kullanılabilir parça alanı (cm2)",
            min_value=1,
            value=state.algorithm_config.min_fragment_cm2,
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
        save_state(state)
        st.success("Parametreler kaydedildi.")

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("Toplam raf", len(state.shelves))
with col_b:
    used_count = sum(1 for shelf in state.shelves if shelf.placements)
    st.metric("Kullanılan raf", used_count)
with col_c:
    blocked_count = sum(1 for shelf in state.shelves if shelf.manual_full)
    st.metric("Manuel dolu raf", blocked_count)

tab1, tab2, tab3 = st.tabs(["Sipariş Yerleştir", "Raf Yönetimi", "Durum Analizi"])

with tab1:
    st.subheader("Yeni Sipariş")
    with st.form("order_form"):
        order_id = st.text_input("Sipariş kodu", value=f"ORD-{uuid4().hex[:8].upper()}")
        product_width_cm = st.number_input("Siparişin palet üstü genişliği (cm)", min_value=1, value=100)
        product_depth_cm = st.number_input("Siparişin palet üstü derinliği (cm)", min_value=1, value=100)
        pallet_width_cm = st.number_input("Palet genişliği (cm)", min_value=1, value=80)
        pallet_depth_cm = st.number_input("Palet derinliği (cm)", min_value=1, value=120)
        company = st.text_input("Firma", value="Örnek Firma")
        ship_date = st.date_input("Sevk tarihi", value=date.today())

        submit_order = st.form_submit_button("Uygun Raf Öner ve Yerleştir")

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
            st.error("Bu sipariş için uygun raf bulunamadı. Parametreleri veya boş alanları kontrol edin.")
        else:
            best = suggestions[0]
            ok, message = place_order_on_shelf(
                state,
                order,
                shelf_id=best["shelf_id"],
                free_rect_index=best["free_rect_index"],
            )
            if ok:
                save_state(state)
                st.success(f"Önerilen raf: {best['shelf_id']}. {message}")
            else:
                st.error(message)

            st.markdown("### En İyi Raf Adayları")
            st.dataframe(suggestions, use_container_width=True)

with tab2:
    st.subheader("Taşıyıcı Müdahalesi")
    shelf_ids = [shelf.shelf_id for shelf in state.shelves]

    st.markdown("### Hızlı Raf Seçimi")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    with quick_col1:
        quick_aisle = st.number_input(
            "Koridor (A)",
            min_value=1,
            max_value=state.warehouse_config.aisles,
            value=1,
            step=1,
        )
    with quick_col2:
        quick_side = st.number_input(
            "Taraf (S)",
            min_value=1,
            max_value=state.warehouse_config.sides_per_aisle,
            value=1,
            step=1,
        )
    with quick_col3:
        quick_row = st.number_input(
            "Sıra (R)",
            min_value=1,
            max_value=state.warehouse_config.rows_per_side,
            value=1,
            step=1,
        )
    with quick_col4:
        quick_y = st.number_input(
            "Y Raf (Y)",
            min_value=1,
            max_value=state.warehouse_config.shelves_per_row,
            value=1,
            step=1,
        )

    quick_shelf_id = f"A{int(quick_aisle):02d}-S{int(quick_side):02d}-R{int(quick_row):03d}-Y{int(quick_y):02d}"
    st.caption(f"Hızlı seçim kodu: {quick_shelf_id}")

    search_text = st.text_input("Raf kodunda ara", value=quick_shelf_id)
    filtered_shelf_ids = [sid for sid in shelf_ids if search_text.strip().upper() in sid.upper()]
    if not filtered_shelf_ids:
        st.warning("Arama kriterine uyan raf yok. Tüm raf listesi gösterildi.")
        filtered_shelf_ids = shelf_ids

    selected_shelf = st.selectbox("Raf seç", options=filtered_shelf_ids)
    selected_state = next((s for s in state.shelves if s.shelf_id == selected_shelf), None)

    if selected_state is not None:
        st.write(
            {
                "raf": selected_state.shelf_id,
                "kullanım_oranı": round(selected_state.utilization, 3),
                "aktif_sipariş_sayısı": len(selected_state.placements),
                "manuel_dolu": selected_state.manual_full,
                "boş_alan_cm2": selected_state.free_area,
            }
        )

        full_col, free_col, clear_col = st.columns(3)
        with full_col:
            if st.button("Bu rafı DOLU işaretle"):
                ok, message = mark_shelf_manual_full(state, selected_shelf, True)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)

        with free_col:
            if st.button("Bu rafı tekrar AÇ"):
                ok, message = mark_shelf_manual_full(state, selected_shelf, False)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)

        with clear_col:
            if st.button("Rafı tek tuşla BOŞALT"):
                ok, message = clear_shelf(state, selected_shelf)
                if ok:
                    save_state(state)
                    st.success(message)
                else:
                    st.error(message)

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
        with cancel_col:
            if st.button("Vazgeç"):
                st.session_state.confirm_clear_all_shelves = False
                st.info("Toplu boşaltma iptal edildi.")

with tab3:
    st.subheader("Operasyon Özeti")
    total_area = sum(s.area for s in state.shelves)
    used_area = sum(s.used_area for s in state.shelves)
    utilization = (used_area / total_area) if total_area else 0.0

    st.metric("Genel alan kullanım oranı", f"{utilization * 100:.2f}%")
    st.metric("Toplam yerleşen sipariş", len(state.orders))

    if state.orders:
        closest_date = state.orders[-1].ship_date
        near_count = orders_in_date_window(state, closest_date, state.algorithm_config.ship_date_cluster_days)
        st.info(
            f"Son sipariş tarihi çevresinde (+/- {state.algorithm_config.ship_date_cluster_days} gün) toplam {near_count} sipariş var."
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
    st.dataframe(rows, use_container_width=True)
