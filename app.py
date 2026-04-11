import streamlit as st
import pandas as pd
from modules.utils.config_loader import cargar_config, horas_por_dia
from modules.scheduler import programar
from modules.utils.persistence import PersistenceManager
from modules.utils.data_processor import process_uploaded_dataframe

from modules.ui_components import (
    render_machine_speed_inputs,
    render_daily_params_section,
    render_active_machines_selector,
    render_downtime_section,
    render_overtime_section,
    render_pending_processes_section,
    render_details_section,
    render_download_section,
    render_daily_details_section,
    render_descartonador_ids_section,
    render_die_preferences,
    render_manual_machine_assignment,
    render_capacity_analysis,
    render_save_section,
    render_delayed_orders_section,
    render_daily_schedule_view,
    render_create_machine,
    render_galpon2_page
)

from modules.utils.visualizations import render_gantt_chart
from modules.printing_suggestions import render_printing_suggestions

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

# =======================================================
# SELECTOR DE GALPÓN
# =======================================================
galpon_col1, galpon_col2 = st.columns([2, 5])
with galpon_col1:
    galpon_activo = st.radio(
        "Seleccionar Galpón:",
        options=["🏭 Galpón 1 (Producción General)", "📦 Galpón 2 (Cartonaje)"],
        index=0,
        horizontal=True,
        key="galpon_selector"
    )
st.markdown("---")

es_galpon2 = "Galpón 2" in galpon_activo

# Load Config (Always active)
if "cfg" not in st.session_state:
    st.session_state.cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")
    # Guardar copia base inmutable del DataFrame de máquinas para poder
    # reconstruir limpio en cada rerun cuando cambian las máquinas custom.
    st.session_state.cfg["_maquinas_base"] = st.session_state.cfg["maquinas"].copy()
cfg = st.session_state.cfg

# --- SIDEBAR CONFIGURATION (Always visible) ---
with st.sidebar:
    st.markdown("### 🔧 Configuración Avanzada")
    ignore_constraints = st.checkbox(
        "Ignorar restricciones de materiales/herramental (Simulación Teórica)", 
        value=False, 
        help="Si se activa, el planificador ignorará la falta de Materia Prima, Chapas o Troqueles. Útil para ver capacidad teórica."
    )
    cfg["ignore_constraints"] = ignore_constraints



    # --- PERSISTENCE INITIALIZATION (MOVED TO SIDEBAR) ---
    st.markdown("### 💾 Persistencia")
    usar_historial = st.checkbox(
        "Usar historial (Respetar asignaciones previas)", 
        value=False,
        help="Si está activado, el sistema intentará mantener las máquinas asignadas en la planificación anterior para las órdenes de hoy."
    )
    
    if "persistence" not in st.session_state:
        st.session_state.persistence = PersistenceManager()
    pm = st.session_state.persistence
    
    # Initialize defaults
    cfg["locked_assignments"] = {}
    
    if pm.connected:
        # 2. LOAD MANUAL OVERRIDES & OTHER CONFIG (solo si usar_historial)
        if usar_historial:
            # 1. LOAD LOCKED ASSIGNMENTS (History)
            locks = pm.get_locked_assignments()
            cfg["locked_assignments"] = locks

        
            # 2. LOAD MANUAL OVERRIDES (Config params)
            # Remove caching check to force sync with checkbox state
            db_overrides = pm.load_manual_overrides()
            
            # Update session state if we found data
            has_data = (db_overrides["blacklist_ots"] or 
                        db_overrides["manual_priorities"] or 
                        db_overrides["outsourced_processes"] or 
                        db_overrides["skipped_processes"] or
                        db_overrides.get("manual_assignments"))

            if has_data:
                 st.session_state.manual_overrides = db_overrides
                 if "manual_assignments" in db_overrides:
                     st.session_state.manual_assignments = db_overrides["manual_assignments"]

                 # st.toast("⚙️ Configuraciones manuales recuperadas.", icon="📝")

            # 3. LOAD DIE PREFERENCES
            db_die_prefs = pm.load_die_preferences()
            if db_die_prefs:
                cfg["troquel_preferences"] = db_die_prefs
                # Also save locally to keep in sync? Optional. 
                # Let's just use it in memory.
                # st.toast("⚙️ Preferencias de troquel recuperadas de BD.", icon="🏭")
            
            # 4. LOAD HOLIDAYS
            db_holidays = pm.load_holidays()
            if db_holidays:
                 st.session_state.db_holidays = db_holidays

            # 5. LOAD DOWNTIMES
            db_downtimes = pm.load_downtimes()
            if db_downtimes:
                st.session_state.downtimes = db_downtimes

            # 6. LOAD OVERTIME
            db_overtime = pm.load_overtime()
            if db_overtime:
                st.session_state.overtime_config = db_overtime
            elif "overtime_config" not in st.session_state:
                st.session_state.overtime_config = {}

            # 7. LOAD PENDING PROCESSES
            db_pending = pm.load_pending_processes()
            if db_pending:
                 st.session_state.pending_processes = db_pending

            # 8. LOAD CUSTOM MACHINES
            db_custom_machines = pm.load_custom_machines()
            if db_custom_machines:
                st.session_state.custom_machines = db_custom_machines

    # -------------------------------------------------
        
    # --- MANUAL OVERRIDES INJECTION ---
    if "manual_overrides" not in st.session_state:
        st.session_state.manual_overrides = {
            "blacklist_ots": set(),
            "manual_priorities": {},
            "outsourced_processes": set(),
            "skipped_processes": set(),
            "urgency_overrides": {},
            "mp_overrides": {},
            "forzar_inicio_overrides": {}
        }
    cfg["manual_overrides"] = st.session_state.manual_overrides
    # ----------------------------------

@st.cache_data(show_spinner="📥 Procesando archivo Excel...")
def load_and_process_excel(file_bytes):
    import io
    df_raw = pd.read_excel(io.BytesIO(file_bytes))
    return process_uploaded_dataframe(df_raw)

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    # Load and apply transformations to DF
    df = load_and_process_excel(archivo.getvalue())

    # ============================================================
    # Branch: Galpón 2 (Cartonaje) — planificación independiente
    # ============================================================
    if es_galpon2:
        render_galpon2_page(df)
        st.stop()  # No seguir ejecutando el resto del G1

    # ============================================================
    # Branch: Galpón 1 (flujo original completo)
    # ============================================================

    # 3.1 UI: Descartonador IDs (New)

    # 8. Scheduler Execution
    st.info("🧠 Generando programa…")

    cfg["custom_ids"] = render_descartonador_ids_section(cfg)

    # 0. UI: Create / Manage custom machines
    render_create_machine(cfg, persistence=pm)

    # 1. UI: Machine Speeds
    render_machine_speed_inputs(cfg)
    
    # 2. UI: Daily Parameters
    fecha_inicio_plan, hora_inicio_plan, feriados_lista = render_daily_params_section(
        default_holidays=st.session_state.get("db_holidays", []),
        persistence=pm
    )
    cfg["feriados"] = feriados_lista 

    # 3. UI: Active Machines
    maquinas_activas = render_active_machines_selector(cfg)

    # Filter config for scheduler
 
    
    # 4. UI: Downtimes
    cfg["downtimes"] = render_downtime_section(maquinas_activas, fecha_inicio_plan, persistence=pm)

    # 3.2 UI: Die Preferences (New)
    render_die_preferences(cfg)

    cfg["pending_processes"] = render_pending_processes_section(maquinas_activas, df, cfg)

    cfg_plan = cfg.copy()
    cfg_plan["maquinas"] = cfg["maquinas"][cfg["maquinas"]["Maquina"].isin(maquinas_activas)].copy()
    
    if "manual_assignments" in st.session_state:
        cfg_plan["manual_assignments"] = st.session_state.manual_assignments

    @st.cache_data(show_spinner="🧠 Calculando planificación...")
    def generar_planificacion(df_in, cfg_in, fecha_in, hora_in, _machine_hash=None):
        return programar(df_in, cfg_in, start=fecha_in, start_time=hora_in)

    # Hash de máquinas activas para invalidar caché cuando cambian (incluyendo custom)
    _maq_hash = tuple(sorted(cfg_plan["maquinas"]["Maquina"].tolist()))
    schedule, carga_md, resumen_ot, detalle_maquina = generar_planificacion(df, cfg_plan, fecha_inicio_plan, hora_inicio_plan, _machine_hash=_maq_hash)

    st.session_state.last_schedule = schedule

    render_gantt_chart(schedule, cfg)

    cfg_plan["manual_assignments"] = render_manual_machine_assignment(cfg_plan, df, maquinas_activas)

    # 11. Details Section
    render_details_section(schedule, detalle_maquina, df, cfg)

    # --- SAVE SECTION ---
    render_save_section(pm)

    # 12. Daily Details Section
    with st.expander("📋 Ver Detalle de Tareas", expanded=False):
        render_daily_details_section(schedule)
    
    # 12.5. Daily Schedule View (Calendar format)
    with st.expander("🗓️ Ver Calendario de Tareas", expanded=False):
        render_daily_schedule_view(schedule, cfg)
    
    # Updates cfg in place (and saves to disk) 

    # 9. Metrics
    col1, col2, col3, col4 = st.columns(4)
    total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
    atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes atrasadas", atrasadas)
    col3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
    col4.metric("Jornada (h/día)", f"{horas_por_dia(cfg):.1f}")
    
    # 10. Capacity Analysis
    render_capacity_analysis(schedule, cfg, fecha_inicio_plan, resumen_ot, carga_md)

    # 5. UI: Overtime
    cfg["horas_extras"] = render_overtime_section(maquinas_activas, fecha_inicio_plan, persistence=pm)
    
    # 10.5 Printing Suggestions
    render_printing_suggestions(schedule, df, fecha_inicio_plan)

    # 13. Delayed Orders Section
    render_delayed_orders_section(resumen_ot, schedule, cfg)

    # 14. Export Section
    render_download_section(schedule, resumen_ot, carga_md)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
