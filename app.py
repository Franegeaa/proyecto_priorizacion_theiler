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
    
    cfg["ignore_constraints"] = ignore_constraints

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
    
    # --- MANUAL OVERRIDES INJECTION ---
    if "manual_overrides" not in st.session_state:
        st.session_state.manual_overrides = {
            "blacklist_ots": set(),
            "manual_priorities": {},
            "outsourced_processes": set(),
            "skipped_processes": set()
        }
    cfg_plan["manual_overrides"] = st.session_state.manual_overrides
    # ----------------------------------
    
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
        st.markdown("### 📊 Análisis de Capacidad y Carga")
        
        # --- EXPLICACIÓN DE MODOS DE ANÁLISIS ---
        # 1. Detectar Cuello de Botella: Busca el primer momento en el futuro donde la demada acumulada supera la capacidad acumulada.
        #    Es útil para saber CUÁNDO va a fallar la planta si no se toman medidas (horas extra).
        # 2. Análisis Temporal: Muestra una foto estática de un periodo (ej. mañana, o la semana que viene).
        #    Compara cuántas horas de trabajo caen en ese periodo vs cuántas horas máquina hay disponibles.
        
        modo_analisis = st.radio(
            "Modo de Análisis:",
            ["Detectar Cuello de Botella (Próximo Vencimiento)", "Análisis Temporal (Carga por Periodo)"],
            index=0,
            horizontal=True
        )

        # ---------------------------------------------------------
        # MODO 1: DETECTAR CUELLO DE BOTELLA (LÓGICA ORIGINAL)
        # ---------------------------------------------------------
        if modo_analisis == "Detectar Cuello de Botella (Próximo Vencimiento)":
            st.caption("Muestra el **Primer Punto Crítico** cronológico de cada máquina. Es decir, la primera orden que no llegaría a tiempo según la capacidad actual.")
            st.info("💡 La barra roja indica las horas necesarias acumuladas hasta ese primer vencimiento fallido.")

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
                
                critical_point = None # (Carga, Capacidad, Balance, FechaCritica)
                found_bottleneck = False
                
                # 3. Analizar tarea por tarea (Punto de chequeo)
                current_capacity = 0.0
                last_date_checked = pd.Timestamp(fecha_inicio_plan).date() - timedelta(days=1)
                
                for idx, task in tasks_m.iterrows():
                    due_dt = task["DueDate"]
                    if pd.isna(due_dt): continue
                    
                    due_date = due_dt.date()
                    if due_date < fecha_inicio_plan:
                        due_date = fecha_inicio_plan 
                    
                    # Actualizar capacidad acumulada hasta due_date
                    if due_date > last_date_checked:
                        delta_dias = pd.date_range(start=last_date_checked + timedelta(days=1), end=due_date)
                        for d in delta_dias:
                            current_capacity += capacity_map.get((maq, d.date()), 0.0)
                        last_date_checked = due_date
                    
                    load = task["CargaAcumulada"]
                    capacity = current_capacity
                    deficit = load - capacity 
                    
                    # TOLERANCIA DE 0.1 HORAS (6 minutos) para no alertar por redondeos
                    if deficit > 0.1:
                        found_bottleneck = True
                        critical_point = {
                            "Maquina": maq,
                            "Horas Necesarias": load,
                            "Horas Disponibles": capacity,
                            "Balance": capacity - load, # Será negativo
                            "Fecha Critica": due_date
                        }
                        break # STOP at FIRST bottleneck!
                
                # Si NO encontramos cuello de botella (todo ok), mostramos el final
                if not found_bottleneck:
                    last_task = tasks_m.iloc[-1]
                    # Asegurar que capacity llegue hasta el ultimo due date
                    # Y ademas, aseguramos mirar al menos 1 semana hacia adelante para que la barra
                    # de "Horas Disponibles" muestre el potencial de la semana (ej 42.5h) y no quede corta
                    # si las ordenes terminan mañana.
                    last_due = last_task["DueDate"].date()
                    min_lookahead = pd.Timestamp(fecha_inicio_plan).date() + timedelta(days=7)
                    target_date = max(last_due, min_lookahead)

                    if target_date > last_date_checked:
                        delta_dias = pd.date_range(start=last_date_checked + timedelta(days=1), end=target_date)
                        for d in delta_dias:
                            current_capacity += capacity_map.get((maq, d.date()), 0.0)
                    
                    # --- VISUAL ADJUSTMENT: Cap displayed available hours ---
                    # Si sobra mucha capacidad, cortamos la visualizacion a 1 semana (aprox 5 dias)
                    # para que la barra no quede gigante.
                    req_hours = last_task["CargaAcumulada"]
                    true_balance = current_capacity - req_hours
                    
                    visual_capacity = current_capacity
                    if current_capacity > req_hours:
                        weekly_cap = horas_por_dia(cfg) * 5.0
                        # Mostramos como maximo max(Req * 1.2, Weekly) para que se vea que sobra
                        # pero no deforme el grafico con 1000 horas.
                        limit_visual = max(req_hours * 1.2, weekly_cap)
                        visual_capacity = min(current_capacity, limit_visual)

                    # Calcular Dias Habiles Involucrados (desde hoy hasta target_date)
                    # Contamos cuantos dias en el rango tenian capacidad > 0
                    rango_dias = pd.date_range(start=fecha_inicio_plan, end=target_date if 'target_date' in locals() else due_date)
                    dias_habiles_count = sum(1 for d in rango_dias if capacity_map.get((maq, d.date()), 0) > 0)

                    critical_point = {
                        "Maquina": maq,
                        "Horas Necesarias": req_hours,
                        "Horas Disponibles": visual_capacity, # Visualmente topeado
                        "Capacidad Total": current_capacity, # <--- DATO REAL PARA EL TOOLTIP
                        "Balance": true_balance, # Balance REAL para tooltip
                        "Fecha Critica": last_task["DueDate"].date() if pd.notna(last_task["DueDate"]) else "N/A",
                        "Dias Habiles": dias_habiles_count
                    }

                if critical_point:
                    # Si fue encontrado en el loop, calculamos dias habiles tambien
                    if "Dias Habiles" not in critical_point:
                        # Recuperamos la fecha critica del dict
                        f_crit = critical_point["Fecha Critica"]
                        # Definir capacity si no existe (caso raro)
                        cap_real = critical_point["Horas Disponibles"]
                        
                        if isinstance(f_crit, (date, datetime)):
                            r_dias = pd.date_range(start=fecha_inicio_plan, end=f_crit)
                            dH = sum(1 for d in r_dias if capacity_map.get((maq, d.date()), 0) > 0)
                            critical_point["Dias Habiles"] = dH
                        else:
                            critical_point["Dias Habiles"] = 0
                        
                        # Asegurar que Capacidad Total este presente (si era bottleneck, visual=real)
                        if "Capacidad Total" not in critical_point:
                            critical_point["Capacidad Total"] = critical_point["Horas Disponibles"]

                    data_bottleneck.append(critical_point)

            df_disp = pd.DataFrame(data_bottleneck)
            
            if not df_disp.empty:
                df_chart = df_disp.sort_values("Horas Necesarias", ascending=False)
                
                # Transformar a formato largo
                df_long = df_chart.melt(id_vars=["Maquina", "Balance", "Fecha Critica", "Dias Habiles", "Capacidad Total"], 
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
                    title="Próximo Cuello de Botella (Carga vs Capacidad Acumulada)",
                    color_discrete_map={"Horas Necesarias": "#EF553B", "Horas Disponibles": "#636EFA"},
                    hover_data=["Balance", "Capacidad Total", "Dias Habiles", "Fecha Critica"]
                )
                fig_carga.update_traces(texttemplate='%{text:.1f} h', textposition='outside')
                fig_carga.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                st.plotly_chart(fig_carga, use_container_width=True)
                
                # Alerta de Riesgo Global
                maquinas_riesgo = df_chart[df_chart["Balance"] < -0.1]
                if not maquinas_riesgo.empty:
                    st.error(f"🚨 Crítico: Se detectaron cuellos de botella inmediatos en {len(maquinas_riesgo)} máquinas.")
                    st.markdown("**Detalle del Primer Vencimiento en Riesgo:**")
                    
                    st.dataframe(maquinas_riesgo[["Maquina", "Fecha Critica", "Horas Necesarias", "Horas Disponibles", "Balance"]].style.format({
                        "Horas Necesarias": "{:.1f}", 
                        "Horas Disponibles": "{:.1f}", 
                        "Balance": "{:.1f}",
                        "Fecha Critica": "{:%Y-%m-%d}"
                    }))
                else:
                    st.success("✅ Todas las máquinas tienen capacidad suficiente para cumplir sus plazos.")

        # ---------------------------------------------------------
        # MODO 2: ANÁLISIS TEMPORAL (POR PERIODO)
        # ---------------------------------------------------------
        else:
            st.caption("Compara la **Carga Programada** (tareas que caen en el periodo) vs **Capacidad Disponible** en ese rango de tiempo.")
            
            # --- FILTROS DE TIEMPO (REPLICADOS DEL GANTT) ---
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                tipo_filtro_cap = st.radio(
                    "Seleccionar Rango de Tiempo:",
                    ["Día", "Semana", "Rango Personalizado"], 
                    index=0,
                    horizontal=True,
                    key="filtro_cap_radio"
                )
            with col_f2:
                tipo_cliente_cap = st.selectbox(
                    "Filtrar por Cliente:",
                    ["(Todos)", "ESTANDAR", "PERSONALIZADOS"],
                    index=0,
                    key="filtro_cap_cliente"
                )
            
            c_start = None
            c_end = None
            min_date = schedule["Inicio"].min().date() if not schedule.empty else date.today()
            # Extendemos max_date para permitir planificación futura (ej. +180 dias)
            last_schedule_date = schedule["Fin"].max().date() if not schedule.empty else date.today()
            max_date = last_schedule_date + pd.Timedelta(days=180)

            if tipo_filtro_cap == "Día":
                f_dia = st.date_input("Seleccioná el día:", value=min_date, min_value=min_date, max_value=max_date, key="cap_dia")
                c_start = pd.Timestamp(f_dia)
                c_end = c_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            elif tipo_filtro_cap == "Semana":
                f_sem = st.date_input("Seleccioná un día de la semana:", value=min_date, min_value=min_date, max_value=max_date, key="cap_sem")
                start_week = f_sem - pd.Timedelta(days=f_sem.weekday())
                c_start = pd.Timestamp(start_week)
                c_end = c_start + pd.Timedelta(days=7) - pd.Timedelta(seconds=1)
                st.info(f"Mostrando semana: {c_start.date()} al {c_end.date()}")
            elif tipo_filtro_cap == "Rango Personalizado":
                fechas = st.date_input("Seleccioná Rango de Fechas:", value=(min_date, min_date), min_value=min_date, max_value=max_date, key="cap_rango")
                if isinstance(fechas, tuple) and len(fechas) == 2:
                    c_start = pd.Timestamp(fechas[0])
                    c_end = pd.Timestamp(fechas[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                else:
                    st.warning("Seleccioná ambas fechas del rango.")
                    st.stop()
            elif tipo_filtro_cap == "Mes":
                f_mes = st.date_input("Seleccioná un día del mes:", value=min_date, min_value=min_date, max_value=max_date, key="cap_mes")
                c_start = pd.Timestamp(f_mes.replace(day=1))
                next_m = (c_start + pd.Timedelta(days=32)).replace(day=1)
                c_end = next_m - pd.Timedelta(seconds=1)
            else: # Ver todo
                c_start = pd.Timestamp(min_date)
                c_end = pd.Timestamp(max_date) + pd.Timedelta(days=1)


            # CALCULAR CARGA Y CAPACIDAD
            outsourced_procs = {"stamping", "plastificado", "encapado", "cuño"}
            outsourced_keywords = ["stamping", "plastifica", "encapado", "cuño"]
            
            # Helper para saber si una maquina es tercerizada
            def es_maquina_tercerizada(m):
                m_lower = m.lower()
                return any(k in m_lower for k in outsourced_keywords)

            # --- FILTRADO POR CLIENTE (NUEVO) ---
            schedule_filtered = schedule.copy()
            if tipo_cliente_cap == "ESTANDAR":
                # Filtramos los que contienen "estandar" (case insensitive)
                schedule_filtered = schedule_filtered[schedule_filtered["Cliente"].astype(str).str.lower().str.contains("estandar", na=False)]
            elif tipo_cliente_cap == "PERSONALIZADOS":
                # Filtramos los que NO contienen "estandar"
                schedule_filtered = schedule_filtered[~schedule_filtered["Cliente"].astype(str).str.lower().str.contains("estandar", na=False)]
            # Si es (Todos), usamos schedule original (copia)

            # --- LOGICA HIBRIDA Y PERSONALIZADA ---
            # USAMOS schedule_filtered PARA EL CALCULO DE CARGA (DEMANDA)
            # 1. Load_Due: Carga de tareas que VENCEN en el periodo (Demanda Pura)
            mask_due = (schedule_filtered["DueDate"] >= c_start) & (schedule_filtered["DueDate"] <= c_end)
            schedule_due = schedule_filtered[mask_due].copy()

            # 2. Load_Active: Carga de tareas que se EJECUTAN en el periodo
            mask_overlap = (schedule_filtered["Inicio"] < c_end) & (schedule_filtered["Fin"] > c_start)
            schedule_active = schedule_filtered[mask_overlap].copy()
            
            # 3. Load_Future: Tareas que terminan DESPUES del rango (Solo para Rango Personalizado)
            if tipo_filtro_cap == "Rango Personalizado":
                mask_future = schedule_filtered["DueDate"] > c_end
                schedule_future = schedule_filtered[mask_future].copy()
            else:
                schedule_future = pd.DataFrame()

            data_temporal = []
            
            # Obtenemos TODAS las máquinas del plan, pero FILTRAMOS las tercerizadas
            all_machines = sorted(schedule["Maquina"].dropna().unique())
            maquinas_todas = [m for m in all_machines if not es_maquina_tercerizada(m)]
            
            # Calcular días hábiles en el rango para capacidad
            dias_en_rango = pd.date_range(start=c_start.date(), end=c_end.date())
            
            # --- NOTA: LIMIT_HOURS (Estimación) ELIMINADA ---
            # Ahora usamos 'cap_total' (Capacidad Real Calculada) como límite para cada máquina.
            # Esto permite que funcione perfecto para Día, Semana, Mes o Todo.

            for maq in maquinas_todas:
                # A. Capacidad Disponible
                cap_total = 0.0
                dias_habiles = 0
                for d in dias_en_rango:
                    hrs = get_horas_totales_dia(d.date(), cfg, maquina=maq)
                    cap_total += hrs
                    if hrs > 0: dias_habiles += 1
                
                # B. Carga DUE (Vencimiento)
                load_due = schedule_due[schedule_due["Maquina"] == maq]["Duracion_h"].sum()

                # C. Carga ACTIVE (Intersección Real)
                tasks_active = schedule_active[schedule_active["Maquina"] == maq]
                load_active = 0.0
                for _, t in tasks_active.iterrows():
                    overlap_start = max(t["Inicio"], c_start)
                    overlap_end = min(t["Fin"], c_end)
                    if overlap_start < overlap_end:
                        load_active += (overlap_end - overlap_start).total_seconds() / 3600.0

                final_load = 0.0
                
                if tipo_filtro_cap == "Rango Personalizado":
                    # LOGICA RANGO PERSONALIZADO:
                    # 1. Base = load_due (Todas las que terminan en el rango)
                    # 2. Si sobra espacio (cap_total > load_due), sumamos ordenes futuras hasta llenar
                    remaining_cap = max(0, cap_total - load_due)
                    
                    future_load = 0.0
                    if not schedule_future.empty:
                        future_load = schedule_future[schedule_future["Maquina"] == maq]["Duracion_h"].sum()
                    
                    fill = min(future_load, remaining_cap)
                    final_load = load_due + fill
                    
                else:
                    # LOGICA ESTANDAR (Dia/Semana/Mes):
                    # Max(Load_Due, Min(Load_Active, Cap_Total))
                    final_load = max(load_due, min(load_active, cap_total))

                # Solo agregamos si hay algo relevante
                if cap_total > 0 or final_load > 0:
                    data_temporal.append({
                        "Maquina": maq,
                        "Horas Necesarias": final_load,
                        "Horas Disponibles": cap_total,
                        "Balance": cap_total - final_load,
                        "Dias Habiles": dias_habiles
                    })

            df_temp = pd.DataFrame(data_temporal)
            
            if not df_temp.empty:
                df_temp = df_temp.sort_values("Horas Necesarias", ascending=False)
                df_long_t = df_temp.melt(id_vars=["Maquina", "Balance", "Dias Habiles"], 
                                        value_vars=["Horas Necesarias", "Horas Disponibles"], 
                                        var_name="Tipo", value_name="Horas")
                
                import plotly.express as px
                fig_temp = px.bar(
                    df_long_t, 
                    x="Maquina", 
                    y="Horas",
                    color="Tipo",
                    barmode="group",
                    text="Horas",
                    title=f"Carga vs Capacidad ({tipo_filtro_cap})",
                    color_discrete_map={"Horas Necesarias": "#EF553B", "Horas Disponibles": "#00CC96"},
                    hover_data=["Balance", "Dias Habiles"]
                )
                fig_temp.update_traces(texttemplate='%{text:.1f} h', textposition='outside')
                fig_temp.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                st.plotly_chart(fig_temp, use_container_width=True)
            else:
                st.warning("No hay datos de carga ni capacidad para el periodo seleccionado.")

    render_gantt_chart(schedule, cfg)

    # 11. Details Section
    render_details_section(schedule, detalle_maquina, df, cfg)

    # 12. Export Section
    render_download_section(schedule, resumen_ot, carga_md)

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
