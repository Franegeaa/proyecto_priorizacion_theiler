import streamlit as st
import pandas as pd
from datetime import date
from modules.config_loader import cargar_config, horas_por_dia
from modules.scheduler import programar

# New modules
from modules.data_processor import process_uploaded_dataframe
from modules.ui_components import (
    render_machine_speed_inputs,
    render_daily_params_section,
    render_active_machines_selector,
    render_downtime_section,
    render_overtime_section,
    render_pending_processes_section,
    render_details_section,
    render_download_section,
    render_descartonador_ids_section # New import
)
from modules.visualizations import render_gantt_chart

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    df = pd.read_excel(archivo)

    # Load Config
    if "cfg" not in st.session_state:
        st.session_state.cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")
    cfg = st.session_state.cfg   # <- SIEMPRE usar el mismo cfg    

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
    cfg["custom_ids"] = render_descartonador_ids_section(cfg_plan) # Pass filtered config or full config? Full config has all machines. Better to use cfg_plan if we only care about active ones? 
    # Actually logic uses cfg["maquinas"] so it will see filtered ones.
    # But wait, render function uses cfg["maquinas"]. 
    # Let's pass cfg_plan so we only edit IDs for ACTIVE machines.
    
    # 4. UI: Downtimes
    # Returns the list of downtimes (dicts)
    cfg["downtimes"] = render_downtime_section(maquinas_activas, fecha_inicio_plan)

    # 5. UI: Overtime
    # Returns dict of {Machine: {Date: Hours}}
    cfg["horas_extras"] = render_overtime_section(maquinas_activas, fecha_inicio_plan)

    # 6. Data Processing
    # Apply transformations to DF
    df = process_uploaded_dataframe(df)

    # 7. UI: Pending Processes (Imagen de Planta)
    # Returns list of pending processes (dicts)
    cfg["pending_processes"] = render_pending_processes_section(maquinas_activas, df, cfg)

    # 8. Scheduler Execution
    st.info("🧠 Generando programa…")

    @st.cache_data(show_spinner="🧠 Calculando planificación...")
    def generar_planificacion(df_in, cfg_in, fecha_in, hora_in):
        # Tip: Streamlit caches based on hash of args.
        return programar(df_in, cfg_in, start=fecha_in, start_time=hora_in)

    schedule, carga_md, resumen_ot, detalle_maquina = generar_planificacion(df, cfg_plan, fecha_inicio_plan, hora_inicio_plan)

    # 9. Metrics
    col1, col2, col3, col4 = st.columns(4)
    total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
    atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes atrasadas", atrasadas)
    col3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
    col4.metric("Jornada (h/día)", f"{horas_por_dia(cfg):.1f}")
    
    # --- METRICA DE RETRASO POR MAQUINA (Solicitado por Usuario) ---
    if not schedule.empty and "Atraso_h" in schedule.columns:
        retraso_maq = schedule.groupby("Maquina")["Atraso_h"].sum().sort_values(ascending=False)
        retraso_maq = retraso_maq[retraso_maq > 0]
        
        if not retraso_maq.empty:
            st.markdown("##### 🚨 Máquinas con retraso acumulado (Necesitan Horas Extras?)")
            st.caption("Suma de horas de retraso de todas las tareas en cada máquina (respecto al DueDate de la OT).")
            
            # Display clearly all machines
            # We use a grid of 4 columns
            for i in range(0, len(retraso_maq), 4):
                cols = st.columns(4)
                chunk = retraso_maq.iloc[i : i+4]
                for j, (maq, atraso) in enumerate(chunk.items()):
                    with cols[j]:
                         st.metric(f"{maq}", f"{atraso:.1f} h", delta="-Retraso", delta_color="inverse")
    render_gantt_chart(schedule, cfg)

    # 11. Details Section
    render_details_section(schedule, detalle_maquina, df)

    # 12. Export Section
    render_download_section(schedule, resumen_ot, carga_md)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
