import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from modules.config_loader import cargar_config, horas_por_dia, get_horas_totales_dia
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
    
    # --- VISUALIZACIÓN DE CARGA DE TRABAJO (REQ. USUARIO) ---
    if not schedule.empty:
        st.markdown("### 📊 Análisis de Capacidad (Cuello de Botella)")
        st.caption("Muestra el 'Punto Crítico' de cada máquina: el momento donde la diferencia entre la carga acumulada y la capacidad disponible es más desfavorable (o más ajustada).")
        st.info("💡 Si una barra roja supera a la azul, significa que en algún momento del plan **faltarán horas** para cumplir con una entrega, aunque luego sobre tiempo.")

        # Filtrar procesos tercerizados
        outsourced = {"stamping", "plastificado", "encapado", "cuño"}
        schedule_viz = schedule[~schedule["Proceso"].astype(str).str.lower().isin(outsourced)].copy()
        
        # Pre-calcular el mapa de capacidad diaria para el rango completo del plan
        # Esto optimiza no llamar a get_horas_totales_dia millones de veces
        fecha_min = schedule_viz["Inicio"].min().date() if not schedule_viz.empty else fecha_inicio_plan
        fecha_max = schedule_viz["DueDate"].max().date() if not schedule_viz.empty and pd.notna(schedule_viz["DueDate"].max()) else fecha_inicio_plan
        
        # Extendemos un poco el horizonte por seguridad
        fecha_max = max(fecha_max, (pd.Timestamp(fecha_inicio_plan) + timedelta(days=30)).date())
        
        dias_rango = pd.date_range(start=fecha_inicio_plan, end=fecha_max)
        capacity_map = {} # { (maquina, fecha): horas }
        
        # Identificar maquinas relevantes
        maquinas_viz = schedule_viz["Maquina"].unique()
        
        # Llenar mapa de capacidad
        for maq in maquinas_viz:
            for d in dias_rango:
                capacity_map[(maq, d.date())] = get_horas_totales_dia(d.date(), cfg, maquina=maq)

        data_bottleneck = []

        for maq in maquinas_viz:
            # 1. Obtener tareas y ordenar por Fecha Compromiso (DueDate)
            tasks_m = schedule_viz[schedule_viz["Maquina"] == maq].copy()
            if tasks_m.empty: continue
            
            tasks_m.sort_values("DueDate", inplace=True)
            
            # 2. Calcular Carga Acumulada
            tasks_m["CargaAcumulada"] = tasks_m["Duracion_h"].cumsum()
            
            max_deficit = -float('inf')
            critical_point = None # (Carga, Capacidad, Balance, FechaCritica)
            
            # 3. Analizar tarea por tarea (Punto de chequeo)
            current_capacity = 0.0
            last_date_checked = pd.Timestamp(fecha_inicio_plan).date() - timedelta(days=1)
            
            # Optimizacion: Iterar fechas en lugar de tareas si hay muchas tareas? 
            # Mejor iterar tareas, son los deadlines los que importan.
            
            cumulative_cap = 0.0
            # Pre-calcular vector de capacidad acumulada seria mejor, pero vamos simple
            
            for idx, task in tasks_m.iterrows():
                due_dt = task["DueDate"]
                if pd.isna(due_dt): continue
                
                # Deadline efectivo: DueDate y asumimos hasta fin del turno o final del dia?
                # Para ser seguros, contemos capacidad hasta ese día inclusive.
                due_date = due_dt.date()
                
                if due_date < fecha_inicio_plan:
                    due_date = fecha_inicio_plan # Ya estamos jugados
                
                # Sumar capacidad desde inicio hasta due_date
                # (Podríamos optimizar no recalculando desde cero siempre)
                # Vamos a calcular incrementalmente
                cap_hasta_deadline = 0.0
                
                # Calculo rapido usando el mapa y rango de fechas
                # Generamos rango desde inicio hasta due_date
                # Cuidado: esto puede ser lento si hay muchas tareas.
                # Mejor estrategia:
                # 1. Tener un array de dias y sus capacidades.
                # 2. Sumar slice del array.
                
                # Version Correcta y Simple para este volumen de datos:
                # Sumar capacidad disponible en el rango [fecha_inicio_plan, due_date]
                # usando el mapa pre-calculado
                
                # Optimizacion local: Sumar solo lo nuevo si las fechas avanzan (que deberían por el sort)
                # Pero si hay varias tareas mismo dia, es igual.
                
                # Reset para cada maq? No, incremental es mejor.
                # Si due_date > last_date_checked: sumar dias intermedios
                
                if due_date > last_date_checked:
                    delta_dias = pd.date_range(start=last_date_checked + timedelta(days=1), end=due_date)
                    for d in delta_dias:
                        current_capacity += capacity_map.get((maq, d.date()), 0.0)
                    last_date_checked = due_date
                
                # Ahora current_capacity tiene la capacidad acumulada hasta task.DueDate
                # CargaAcumulada tiene la carga hasta task inclusive
                
                load = task["CargaAcumulada"]
                capacity = current_capacity
                balance = capacity - load # Negativo es malo
                deficit = load - capacity # Positivo es malo
                
                if deficit > max_deficit:
                    max_deficit = deficit
                    critical_point = {
                        "Maquina": maq,
                        "Horas Necesarias": load,
                        "Horas Disponibles": capacity,
                        "Balance": balance,
                        "Fecha Critica": due_date
                    }
            
            # Si encontramos punto critico, lo guardamos.
            # Si todo sobra (max_deficit < 0), guardamos el punto final (última tarea) 
            # para mostrar el estado general "sano".
            if max_deficit <= 0:
                # Tomar la ultima tarea
                last_task = tasks_m.iloc[-1]
                critical_point = {
                    "Maquina": maq,
                    "Horas Necesarias": last_task["CargaAcumulada"],
                    "Horas Disponibles": current_capacity, # Capacidad hasta el final
                    "Balance": current_capacity - last_task["CargaAcumulada"],
                    "Fecha Critica": last_task["DueDate"].date() if pd.notna(last_task["DueDate"]) else "N/A"
                }

            if critical_point:
                data_bottleneck.append(critical_point)

        df_disp = pd.DataFrame(data_bottleneck)
        
        if not df_disp.empty:
            df_chart = df_disp.sort_values("Horas Necesarias", ascending=False)
            
            # Transformar a formato largo
            df_long = df_chart.melt(id_vars=["Maquina", "Balance", "Fecha Critica"], 
                                    value_vars=["Horas Necesarias", "Horas Disponibles"], 
                                    var_name="Tipo", value_name="Horas")
            
            import plotly.express as px
            fig_carga = px.bar(
                df_long, 
                x="Maquina", 
                y="Horas",
                color="Tipo",
                barmode="group",
                text="Horas",
                title="Punto Crítico: Carga vs Capacidad",
                color_discrete_map={"Horas Necesarias": "#EF553B", "Horas Disponibles": "#636EFA"},
                hover_data=["Balance", "Fecha Critica"]
            )
            fig_carga.update_traces(texttemplate='%{text:.1f} h', textposition='outside')
            fig_carga.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
            st.plotly_chart(fig_carga, use_container_width=True)
            
            # Alerta de Riesgo Global
            maquinas_riesgo = df_chart[df_chart["Balance"] < 0]
            if not maquinas_riesgo.empty:
                st.error(f"🚨 Crítico: {len(maquinas_riesgo)} máquinas no llegan a tiempo con sus entregas en el peor escenario.")
                st.markdown("**Detalle del Cuello de Botella (Peor Momento):**")
                
                st.dataframe(maquinas_riesgo[["Maquina", "Fecha Critica", "Horas Necesarias", "Horas Disponibles", "Balance"]].style.format({
                    "Horas Necesarias": "{:.1f}", 
                    "Horas Disponibles": "{:.1f}", 
                    "Balance": "{:.1f}",
                    "Fecha Critica": "{:%Y-%m-%d}"
                }))
            else:
                st.success("✅ Todas las máquinas tienen capacidad suficiente para cumplir sus plazos.")

    render_gantt_chart(schedule, cfg)

    # 11. Details Section
    render_details_section(schedule, detalle_maquina, df)

    # 12. Export Section
    render_download_section(schedule, resumen_ot, carga_md)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
