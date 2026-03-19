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
    render_daily_schedule_view
)

from modules.utils.visualizations import render_gantt_chart
from modules.printing_suggestions import render_printing_suggestions

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

# Load Config (Always active)
if "cfg" not in st.session_state:
    st.session_state.cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")
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

    # -------------------------------------------------
        
    # --- MANUAL OVERRIDES INJECTION ---
    if "manual_overrides" not in st.session_state:
        st.session_state.manual_overrides = {
            "blacklist_ots": set(),
            "manual_priorities": {},
            "outsourced_processes": set(),
            "skipped_processes": set(),
            "urgency_overrides": {},
            "mp_overrides": {}
        }
    cfg["manual_overrides"] = st.session_state.manual_overrides
    # ----------------------------------

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    df = pd.read_excel(archivo)
    # 3.1 UI: Descartonador IDs (New)

    # 8. Scheduler Execution
    st.info("🧠 Generando programa…")
    

    # Apply transformations to DF
    df = process_uploaded_dataframe(df)

    cfg["custom_ids"] = render_descartonador_ids_section(cfg) 

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

    # @st.cache_data(show_spinner="🧠 Calculando planificación...")
    def generar_planificacion(df_in, cfg_in, fecha_in, hora_in):
        return programar(df_in, cfg_in, start=fecha_in, start_time=hora_in)

    # --- PLANT PARTITIONING ---
    tab1, tab2 = st.tabs(["🏭 Planta 1 (General)", "📦 Planta 2 (Cartonaje)"])

    # Split Orders
    mask_p2 = df["Cliente"].astype(str).str.upper().str.contains("CARTONAJE", na=False)
    df_p1 = df[~mask_p2].copy()
    df_p2 = df[mask_p2].copy()

    def run_shed_ui(df_shed, shed_name, container, suffix=""):
        if df_shed.empty:
            container.warning(f"No hay órdenes pendientes para {shed_name}.")
            return

        cfg_shed = cfg_plan.copy()
        if "Planta 2" in shed_name:
            cfg_shed["planta"] = 2
            # --- PLANTA 2 MACHINE CONFIGURATION ---
            maquinas_p1 = cfg_shed["maquinas"]
            
            def get_m(name):
                m = maquinas_p1[maquinas_p1["Maquina"] == name]
                return m.iloc[0].to_dict() if not m.empty else None

            p2_list = []
            # Troqueladoras
            for new_n, p1_n in [
                ("Duyan 2", "Duyan"), 
                ("Y-TroqNº2", "Troq Nº 2 Ema"), 
                ("Z-TroqNº1", "Troq Nº 1 Gus")
            ]:
                m = get_m(p1_n)
                if m:
                    m = m.copy(); m["Maquina"] = new_n; p2_list.append(m)
            
            # Iberica (Shared)
            m_ib = get_m("Iberica")
            if m_ib: p2_list.append(m_ib)
            
            # Descartonadoras (2 ones, same characteristics)
            m_desc = get_m("Descartonadora 1")
            if m_desc:
                for m_name in ["Descartonadora P2-1", "Descartonadora P2-2"]:
                    m = m_desc.copy(); m["Maquina"] = m_name; p2_list.append(m)
            
            cfg_shed["maquinas"] = pd.DataFrame(p2_list)
        else:
            cfg_shed["planta"] = 1

        # Filter machines for this shed if "Planta" column exists, 
        # otherwise rely on the user having active machines selected or machine names matching.
        # But for now, we'll use all active machines and let the scheduler handle it 
        # based on which tasks are present.
        
        schedule, carga_md, resumen_ot, detalle_maquina = generar_planificacion(df_shed, cfg_shed, fecha_inicio_plan, hora_inicio_plan)
        
        with container:
            st.subheader(f"Planificación - {shed_name}")
            render_gantt_chart(schedule, cfg_shed, key_suffix=suffix)

            # 9. Metrics
            m1, m2, m3, m4 = st.columns(4)
            total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
            atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
            horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

            m1.metric("Órdenes planificadas", total_ots)
            m2.metric("Órdenes atrasadas", atrasadas)
            m3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
            m4.metric("Jornada (h/día)", f"{horas_por_dia(cfg_shed):.1f}")

            # Sections
            with st.expander("🛠️ Ver Controles de Máquina", expanded=False):
                cfg_shed["manual_assignments"] = render_manual_machine_assignment(cfg_shed, df_shed, maquinas_activas, key_suffix=suffix)
            
            render_details_section(schedule, detalle_maquina, df_shed, cfg_shed, key_suffix=suffix)
            
            with st.expander("📋 Ver Detalle de Tareas", expanded=False):
                render_daily_details_section(schedule, key_suffix=suffix)
            
            with st.expander("🗓️ Ver Calendario de Tareas", expanded=False):
                render_daily_schedule_view(schedule, cfg_shed, key_suffix=suffix)

            render_capacity_analysis(schedule, cfg_shed, fecha_inicio_plan, resumen_ot, carga_md, key_suffix=suffix)
            render_delayed_orders_section(resumen_ot, schedule, cfg_shed, key_suffix=suffix)
            render_download_section(schedule, resumen_ot, carga_md, key_suffix=suffix)

    run_shed_ui(df_p1, "Planta 1", tab1, suffix="p1")
    run_shed_ui(df_p2, "Planta 2", tab2, suffix="p2")

    # --- GLOBAL ACTIONS (Save applies to all) ---
    st.divider()
    render_save_section(pm)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
