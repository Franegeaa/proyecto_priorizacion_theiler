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
    render_descartonador_ids_section,
    render_die_preferences,
    render_manual_machine_assignment,
    render_capacity_analysis,
    render_save_section
)

from modules.utils.visualizations import render_gantt_chart

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
        # 1. LOAD LOCKED ASSIGNMENTS (History)
        if usar_historial:
            locks = pm.get_locked_assignments()
            cfg["locked_assignments"] = locks
            # if locks:
            #     st.toast(f"🔒 Se cargaron {len(locks)} asignaciones fijas del historial.", icon="🛡️")
        
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
    # -------------------------------------------------
        
    # --- MANUAL OVERRIDES INJECTION ---
    if "manual_overrides" not in st.session_state:
        st.session_state.manual_overrides = {
            "blacklist_ots": set(),
            "manual_priorities": {},
            "outsourced_processes": set(),
            "skipped_processes": set()
        }
    cfg["manual_overrides"] = st.session_state.manual_overrides
    # ----------------------------------

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    df = pd.read_excel(archivo)
    
    # 1. UI: Machine Speeds
    render_machine_speed_inputs(cfg)
    
    # 2. UI: Daily Parameters
    fecha_inicio_plan, hora_inicio_plan, feriados_lista = render_daily_params_section()
    cfg["feriados"] = feriados_lista 

    # 3. UI: Active Machines
    maquinas_activas = render_active_machines_selector(cfg)

    # Filter config for scheduler
    cfg_plan = cfg.copy()
    cfg_plan["maquinas"] = cfg["maquinas"][cfg["maquinas"]["Maquina"].isin(maquinas_activas)].copy()
    
    # 3.1 UI: Descartonador IDs (New)
    cfg["custom_ids"] = render_descartonador_ids_section(cfg_plan) 
    
    # 3.2 UI: Die Preferences (New)
    render_die_preferences(cfg_plan) # Updates cfg in place (and saves to disk) 
    
    # 4. UI: Downtimes
    cfg["downtimes"] = render_downtime_section(maquinas_activas, fecha_inicio_plan)

    # 5. UI: Overtime
    cfg["horas_extras"] = render_overtime_section(maquinas_activas, fecha_inicio_plan)

    # 6. Data Processing
    # Apply transformations to DF
    df = process_uploaded_dataframe(df)

    # 7. UI: Pending Processes (Imagen de Planta)
    cfg["pending_processes"] = render_pending_processes_section(maquinas_activas, df, cfg)

    # 7.1 UI: Manual Assignment
    cfg_plan["manual_assignments"] = render_manual_machine_assignment(cfg_plan, df, maquinas_activas)

    # 8. Scheduler Execution
    st.info("🧠 Generando programa…")

    @st.cache_data(show_spinner="🧠 Calculando planificación...")
    def generar_planificacion(df_in, cfg_in, fecha_in, hora_in):
        return programar(df_in, cfg_in, start=fecha_in, start_time=hora_in)

    schedule, carga_md, resumen_ot, detalle_maquina = generar_planificacion(df, cfg_plan, fecha_inicio_plan, hora_inicio_plan)
    st.session_state.last_schedule = schedule

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

    render_gantt_chart(schedule, cfg)

    # 11. Details Section
    render_details_section(schedule, detalle_maquina, df, cfg)

    # --- SAVE SECTION ---
    render_save_section(pm)

    # 12. Export Section
    render_download_section(schedule, resumen_ot, carga_md)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
