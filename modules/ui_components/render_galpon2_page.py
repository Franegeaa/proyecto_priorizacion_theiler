"""
Página principal del Galpón 2 (Cartonaje).

Renderiza toda la UI del planificador del Galpón 2:
  - Parámetros de jornada
  - Ejecución del scheduler G2
  - Gantt de resultados
  - Tabla de detalle básica
  - Descarga de resultados
"""

import streamlit as st
import pandas as pd
from datetime import date, time

from modules.galpon2.config_g2 import cargar_config_galpon2
from modules.galpon2.scheduler_g2 import programar_galpon2
from modules.utils.visualizations import render_gantt_chart
from modules.utils.config_loader import horas_por_dia


def render_galpon2_page(df_ordenes: pd.DataFrame):
    """
    Renderiza la interfaz completa del Galpón 2.

    Parámetros:
        df_ordenes: DataFrame ya procesado (resultado de load_and_process_excel)
    """

    st.markdown("---")
    st.header("🏭 Galpón 2 — Planificación Cartonaje")
    st.caption(
        "Planifica exclusivamente las órdenes de **Clientes CARTONAJE**. "
        "Flujo: **Guillotina → Troquelado → Prensado**"
    )

    # ----------------------------------------------------------------
    # Verificar que haya órdenes de Cartonaje en el Excel
    # ----------------------------------------------------------------
    if "Cliente" not in df_ordenes.columns:
        st.warning("El Excel no tiene columna 'Cliente'. No se puede filtrar Cartonaje.")
        return

    df_cartonaje_check = df_ordenes[
        df_ordenes["Cliente"].astype(str).str.lower().str.contains("cartonaje", na=False)
    ]

    if df_cartonaje_check.empty:
        st.info("ℹ️ No hay órdenes de clientes **CARTONAJE** en el Excel cargado.")
        return

    st.success(f"✅ Se encontraron **{len(df_cartonaje_check)}** órdenes de Cartonaje para planificar.")

    # ----------------------------------------------------------------
    # Configuración de jornada (reutiliza cfg G1 para fechas/feriados)
    # ----------------------------------------------------------------
    with st.expander("⚙️ Parámetros de Jornada – Galpón 2", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio = st.date_input(
                "📅 Fecha de inicio",
                value=date.today(),
                key="g2_fecha_inicio"
            )
        with col2:
            hora_inicio = st.time_input(
                "⏰ Hora de inicio",
                value=time(7, 0),
                key="g2_hora_inicio"
            )

    # ----------------------------------------------------------------
    # Cargar configuración del G2
    # ----------------------------------------------------------------
    if "cfg_g2" not in st.session_state:
        st.session_state.cfg_g2 = cargar_config_galpon2()
    cfg_g2 = st.session_state.cfg_g2

    # Resetear locked_assignments en cada rerun para que _Prensa_Asignada
    # se recalcule limpiamente desde el df de órdenes
    cfg_g2["locked_assignments"] = {}

    # ----------------------------------------------------------------
    # Tabla de máquinas del G2 (informativa + velocidades editables)
    # ----------------------------------------------------------------
    with st.expander("🔧 Máquinas del Galpón 2", expanded=False):
        maq_df = cfg_g2["maquinas"][["Maquina", "Proceso", "Capacidad_pliegos_hora"]].copy()
        maq_df.columns = ["Máquina", "Proceso", "Velocidad (pl/h)"]
        st.dataframe(maq_df, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------
    # Ejecutar planificación
    # ----------------------------------------------------------------
    st.info("🧠 Calculando planificación del Galpón 2…")

    @st.cache_data(show_spinner="🧠 Calculando planificación Galpón 2...")
    def _ejecutar_g2(df_in, cfg_in, fecha_in, hora_in):
        return programar_galpon2(df_in, cfg_in, start=fecha_in, start_time=hora_in)

    try:
        schedule_g2, carga_g2, resumen_g2, detalle_g2 = _ejecutar_g2(
            df_ordenes, cfg_g2, fecha_inicio, hora_inicio
        )
    except Exception as e:
        st.error(f"❌ Error al planificar el Galpón 2: {e}")
        import traceback
        st.code(traceback.format_exc())
        return

    if schedule_g2 is None or schedule_g2.empty:
        st.warning("⚠️ No se generó planificación. Verificá que las órdenes de Cartonaje tengan procesos pendientes.")
        return

    # ----------------------------------------------------------------
    # Métricas rápidas
    # ----------------------------------------------------------------
    col1, col2, col3 = st.columns(3)
    total_ots = resumen_g2["OT_id"].nunique() if not resumen_g2.empty else 0
    atrasadas = int(resumen_g2["EnRiesgo"].sum()) if not resumen_g2.empty and "EnRiesgo" in resumen_g2.columns else 0
    horas_extra = float(carga_g2["HorasExtra"].sum()) if not carga_g2.empty and "HorasExtra" in carga_g2.columns else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes en riesgo", atrasadas)
    col3.metric("Horas extra (total)", f"{horas_extra:.1f} h")

    # ----------------------------------------------------------------
    # Gantt del G2
    # ----------------------------------------------------------------
    render_gantt_chart(schedule_g2, cfg_g2)

    # ----------------------------------------------------------------
    # Tabla de detalle de tareas
    # ----------------------------------------------------------------
    with st.expander("📋 Detalle de Tareas – Galpón 2", expanded=False):
        if not schedule_g2.empty:
            cols_mostrar = [c for c in ["OT_id", "Cliente", "Proceso", "Maquina", "Inicio", "Fin", "Duracion_h", "DueDate"]
                            if c in schedule_g2.columns]
            df_show = schedule_g2[cols_mostrar].copy()
            if "Inicio" in df_show.columns:
                df_show["Inicio"] = pd.to_datetime(df_show["Inicio"]).dt.strftime("%d/%m %H:%M")
            if "Fin" in df_show.columns:
                df_show["Fin"] = pd.to_datetime(df_show["Fin"]).dt.strftime("%d/%m %H:%M")
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------
    # Descarga
    # ----------------------------------------------------------------
    with st.expander("⬇️ Descargar Resultados – Galpón 2", expanded=False):
        if not schedule_g2.empty:
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                schedule_g2.to_excel(writer, sheet_name="Plan_G2", index=False)
                if not resumen_g2.empty:
                    resumen_g2.to_excel(writer, sheet_name="Resumen_OT_G2", index=False)
                if not carga_g2.empty:
                    carga_g2.to_excel(writer, sheet_name="Carga_Maquinas_G2", index=False)
            buffer.seek(0)
            st.download_button(
                label="📥 Descargar Excel – Galpón 2",
                data=buffer,
                file_name=f"plan_galpon2_{fecha_inicio.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="g2_download"
            )
