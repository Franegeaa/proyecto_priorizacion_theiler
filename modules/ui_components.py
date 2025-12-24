import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
from .app_utils import ordenar_maquinas_personalizado
from .exporters import generar_excel_bytes, generar_csv_maquina_str, generar_csv_ot_str, generar_excel_ot_bytes, dataframe_to_excel_bytes

def render_machine_speed_inputs(cfg):
    """Renders the section to adjust machine speeds and setup times."""
    maquinas_todas = sorted(cfg["maquinas"]["Maquina"].unique().tolist())
    
    with st.expander("Añadir un velocidades de máquina (opcional)"):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            d_maquina_s = st.selectbox(
                "Máquina", 
                options=maquinas_todas, 
                key="d_maquina_s"
            )

        maquina = d_maquina_s

        vel_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Capacidad_pliegos_hora"].values[0]
        setup_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_base_min"].values[0]
        setup_min_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_menor_min"].values[0]

        with col2:
            vel_valor = st.number_input("Velocidad de máquina (pliegos/hora)", value=int(vel_valor), key=f"vel_{maquina}")
            if vel_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Capacidad_pliegos_hora"] = int(vel_valor)
            else:
                st.warning("La velocidad debe ser mayor que 0.")
        with col3:
            setup_valor = st.number_input("Setup base (min)", value=int(setup_valor), key=f"setup_{maquina}")
            if setup_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_base_min"] = int(setup_valor)
            else:
                st.warning("El setup base debe ser mayor que 0.")
        with col4:
            setup_min_valor = st.number_input("Setup menor (min)", value=int(setup_min_valor), key=f"setup_menor_{maquina}")
            if setup_min_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_menor_min"] = int(setup_min_valor)
            else:
                st.warning("El setup menor debe ser mayor que 0.")

def render_daily_params_section(default_date=None, default_time=None):
    """Renders the Daily Parameters section (Date, Time, Holidays)."""
    st.subheader("⚙️ Parámetros de jornada") 
    
    with st.expander("Añadir Parámetros de Jornada", expanded=False):
        today = date.today()
        if default_date is None: default_date = today
        if default_time is None: default_time = pd.to_datetime("07:00").time()

        fecha_inicio_plan = st.date_input(
            "📅 Fecha de inicio de la planificación:",
            value=default_date,
            min_value=today,
        )

        hora_inicio_plan = st.time_input(
            "⏰ Hora de inicio de la planificación:",
            value=default_time
        )

        # Input de Feriados
        placeholder_feriados = "Pega una lista de fechas (ej. 21/11/2025), una por línea o separadas por coma."
        feriados_texto = st.text_area(
            "Días feriados (opcional):",
            placeholder_feriados,
            height=100
        )
        
        feriados_lista = []
        if feriados_texto and feriados_texto.strip() != placeholder_feriados:
            texto_limpio = feriados_texto.replace(",", "\n")
            fechas_str = [f.strip() for f in texto_limpio.split("\n") if f.strip()]
            
            for f_str in fechas_str:
                try:
                    feriados_lista.append(pd.to_datetime(f_str, dayfirst=True, errors='raise').date())
                except Exception:
                    st.warning(f"No se pudo entender la fecha feriado: '{f_str}'. Ignorando.")
        
        if feriados_lista:
            st.info(f"Se registrarán {len(feriados_lista)} días feriados que no se planificarán.")
            
    return fecha_inicio_plan, hora_inicio_plan, feriados_lista


def render_active_machines_selector(cfg):
    """Returns list of selected machines."""
    st.subheader("🏭 Máquinas Disponibles")
    maquinas_todas = sorted(cfg["maquinas"]["Maquina"].unique().tolist())
    maquinas_activas = st.multiselect(
        "Seleccioná las máquinas que se usarán en esta planificación:",
        options=maquinas_todas,
        default=[m for m in maquinas_todas if "Manual 3" not in m and "Descartonadora 3" not in m and "Iberica" not in m and "Descartonadora 4" not in m]
    )
    
    if len(maquinas_activas) < len(maquinas_todas):
        st.warning(f"Planificando solo con {len(maquinas_activas)} de {len(maquinas_todas)} máquinas.")
        
    return maquinas_activas

def render_downtime_section(maquinas_activas, fecha_inicio_plan):
    """Manages downtime inputs and returns the list of downtimes."""
    st.subheader("🔧 Tiempo Fuera de Servicio (Paros Programados)")

    if "downtimes" not in st.session_state:
        st.session_state.downtimes = []

    with st.expander("Añadir un paro de máquina (opcional)"):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            d_maquina = st.selectbox(
                "Máquina", 
                options=maquinas_activas, 
                key="d_maquina"
            )
        with col2:
            d_fecha_inicio = st.date_input("Fecha Inicio", value=fecha_inicio_plan, key="d_fecha_inicio")
        with col3:
            d_hora_inicio = st.time_input("Hora Inicio", value=time(8, 0), key="d_hora_inicio")
        
        col4, col5, col6 = st.columns([2, 1, 1])
        with col4:
            st.write("")
        with col5:
            d_fecha_fin = st.date_input("Fecha Fin", value=d_fecha_inicio, key="d_fecha_fin")
        with col6:
            d_hora_fin = st.time_input("Hora Fin", value=time(12, 0), key="d_hora_fin")

        if st.button("Añadir Paro"):
            dt_inicio = datetime.combine(d_fecha_inicio, d_hora_inicio)
            dt_fin = datetime.combine(d_fecha_fin, d_hora_fin)
            
            if dt_fin <= dt_inicio:
                st.error("Error: La fecha/hora de fin debe ser posterior a la de inicio.")
            else:
                st.session_state.downtimes.append({
                    "maquina": d_maquina,
                    "start": dt_inicio,
                    "end": dt_fin
                })
                st.success(f"Paro añadido para {d_maquina} de {dt_inicio} a {dt_fin}")

        # Ensure dictionary format
        downtimes = pd.DataFrame(st.session_state.downtimes).drop_duplicates().to_dict(orient="records")
        st.session_state.downtimes = downtimes

    if st.session_state.downtimes:
        st.write("Paros programados:")
        for i, dt in enumerate(st.session_state.downtimes):
            st.info(f"{i+1}: **{dt['maquina']}** fuera de servicio desde {dt['start']} hasta {dt['end']}")
            
    return st.session_state.downtimes

def render_overtime_section(maquinas_activas, fecha_inicio_plan):
    """Manages overtime inputs and returns the dict of overtimes."""
    st.subheader("⏳ Horas Extras")
    
    start_of_week_plan = fecha_inicio_plan 
    dias_semana = []
    lista_dias_str = []
    map_str_date = {}
    
    for i in range(7):
        dia_actual = start_of_week_plan + timedelta(days=i)
        nombre = dia_actual.strftime('%A')
        label = f"{nombre} {dia_actual.strftime('%d/%m')}"
        dias_semana.append(dia_actual)
        lista_dias_str.append(label)
        map_str_date[label] = dia_actual # Key object for dictionary

    horas_extras_general = {}
    
    with st.expander("Planificar Horas Extras (por máquina)"):
        maquinas_con_extras = st.multiselect(
            "Seleccioná las máquinas que harán horas extras:",
            options=maquinas_activas, 
            default=[]
        )
        
        if maquinas_con_extras:
            st.markdown("---")
            for maq in maquinas_con_extras:
                st.markdown(f"#### 🏭 {maq}")
                
                dias_sel_maq = st.multiselect(
                    f"Días de horas extras para {maq}:",
                    options=lista_dias_str,
                    default=[],
                    key=f"dias_he_{maq}"
                )
                
                horas_extras_maq = {}
                if dias_sel_maq:
                    cols_he = st.columns(len(dias_sel_maq)) if len(dias_sel_maq) <= 4 else st.columns(4)
                    
                    for idx, dia_label in enumerate(dias_sel_maq):
                        col_obj = cols_he[idx % 4]
                        fecha_obj = map_str_date[dia_label]
                        
                        with col_obj:
                            horas = st.number_input(
                                f"{dia_label} ({maq})",
                                min_value=0.0, 
                                max_value=24.0, 
                                value=2.0, 
                                step=0.5,
                                label_visibility="collapsed",
                                key=f"he_{maq}_{fecha_obj}"
                            )
                            st.caption(f"{dia_label}")
                            
                            if horas > 0:
                                horas_extras_maq[fecha_obj] = horas
                
                if horas_extras_maq:
                    horas_extras_general[maq] = horas_extras_maq
                st.markdown("---")

        if horas_extras_general:
             st.info(f"Se han configurado horas extras para {len(horas_extras_general)} máquinas.")

    return horas_extras_general

def render_pending_processes_section(maquinas_activas, df, cfg):
    """Manages the 'Imagen de Planta' section."""
    st.subheader("📸 Imagen de Planta (Procesos en Curso)")
    
    if "pending_processes" not in st.session_state:
        st.session_state.pending_processes = []

    with st.expander("Cargar procesos en curso (Prioridad Absoluta)"):
        st.info("⚠️ Los procesos cargados aquí se agendarán **primero** en la máquina seleccionada.")
        
        col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns([2, 1.5, 2, 1, 1])
        
        with col_p1:
            pp_maquina = st.selectbox("Máquina", options=maquinas_activas, key="pp_maquina")
            
        # Get machine process
        cfg_maq = cfg["maquinas"]
        proc_maq = cfg_maq.loc[cfg_maq["Maquina"] == pp_maquina, "Proceso"]
        proc_maq_val = proc_maq.iloc[0] if not proc_maq.empty else ""

        # Simple mapping helper
        def normalize_proc_key(p):
            p = str(p).lower().replace("ó","o").replace("é","e").replace("í","i").replace("á","a").replace("ú","u").replace(" ", "")
            return p

        col_target = None
        p_clean = normalize_proc_key(proc_maq_val)
        
        # Try to find corresponding column in df
        for c in df.columns:
            if c.startswith("_PEN_"):
                suffix = c.replace("_PEN_", "").lower()
                if suffix == p_clean:
                    col_target = c
                    break
        
        if not col_target:
            if "flexo" in p_clean: col_target = "_PEN_ImpresionFlexo"
            elif "offset" in p_clean: col_target = "_PEN_ImpresionOffset"
            elif "troquel" in p_clean: col_target = "_PEN_Troquelado"
            elif "pegad" in p_clean: col_target = "_PEN_Pegado"
        
        if col_target and col_target in df.columns:
            ots_disponibles = sorted(df[df[col_target] == True]["OT_id"].unique().tolist())
        else:
            ots_disponibles = sorted(df["OT_id"].unique().tolist()) if "OT_id" in df.columns else []

        with col_p2:
            pp_ot = st.selectbox("Orden de Trabajo (OT)", options=ots_disponibles, key="pp_ot")
            
        with col_p3:
            cliente_val = ""
            if pp_ot:
                 try: 
                     cliente_val = df.loc[df["OT_id"] == pp_ot, "Cliente"].iloc[0]
                 except: 
                     cliente_val = ""
            st.text_input("Cliente", value=cliente_val, disabled=True, key=f"pp_cli_{pp_ot}")

        with col_p4:
            pp_qty = st.number_input("Cant. Pendiente", min_value=1, value=1000, step=100, key="pp_qty")
            
        with col_p5:
            st.write("") 
            st.write("") 
            if st.button("➕ Cargar", key="btn_add_pp"):
                st.session_state.pending_processes.append({
                    "maquina": pp_maquina,
                    "ot_id": pp_ot,
                    "cantidad_pendiente": pp_qty
                })
                st.success(f"Cargado: {pp_maquina} -> {pp_ot} ({pp_qty})")

        if st.session_state.pending_processes:
            st.write("📋 **Procesos en Curso Cargados:**")
            h1, h2, h3, h4 = st.columns([3, 3, 2, 1])
            h1.markdown("**Máquina**")
            h2.markdown("**OT**")
            h3.markdown("**Cant.**")
            
            for i, item in enumerate(st.session_state.pending_processes):
                c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
                with c1: st.write(item["maquina"])
                with c2: st.write(item["ot_id"])
                with c3: st.write(item["cantidad_pendiente"])
                with c4:
                    if st.button("❌", key=f"del_pp_{i}"):
                        st.session_state.pending_processes.pop(i)
                        st.rerun()
            
            st.markdown("---")
            if st.button("Limpiar TODO", key="btn_clear_pp"):
               st.session_state.pending_processes = []
               st.rerun()

    return st.session_state.pending_processes

def render_details_section(schedule, detalle_maquina, df):
    """Renders the interactive details section."""
    st.subheader("🔎 Detalle interactivo")
    modo = st.radio("Ver detalle por:", ["Orden de Trabajo (OT)", "Máquina"], horizontal=True)

    if modo == "Orden de Trabajo (OT)":
        if not schedule.empty: 
            opciones = ["(Todas)"] + sorted(schedule["OT_id"].unique().tolist())
            elegido = st.selectbox("Elegí OT:", opciones)
            df_show = schedule if elegido == "(Todas)" else schedule[schedule["OT_id"] == elegido]
            df_show = df_show.drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_show, use_container_width=True)
            
            # --- Custom Download Button ---
            buf = dataframe_to_excel_bytes(df_show, sheet_name="Detalle OT")
            st.download_button(
                label="⬇️ Descargar Datos en Excel",
                data=buf,
                file_name=f"Detalle_OT_{elegido if elegido != '(Todas)' else 'Todas'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_ot_detail"
            )
            # ------------------------------
        else:
            st.info("No hay tareas planificadas.")

    else:
        if not schedule.empty and detalle_maquina is not None and not detalle_maquina.empty:
            maquinas_disponibles = ordenar_maquinas_personalizado(detalle_maquina["Maquina"].unique().tolist())
            maquina_sel = st.selectbox("Seleccioná una máquina:", maquinas_disponibles)

            df_maquina = schedule[schedule["Maquina"] == maquina_sel].copy()

            if "CodigoTroquel" not in df_maquina.columns and "CodigoTroquel" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "CodigoTroquel"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )

            if "Colores" not in df_maquina.columns and "Colores" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "Colores"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )
            
            df_maquina.sort_values(by="Inicio", inplace=True)

            # Columns selection
            if any(k in maquina_sel.lower() for k in ["troq", "manual", "autom", "duyan", "iberica"]):
                st.write("🧱 Mostrando código de troquel (agrupamiento interno).")
                cols = ["OT_id", "Cliente-articulo", "PliAnc","PliLar", "Bocas","CantidadPliegosNetos", "CantidadPliegos", "CodigoTroquel", "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate"]
            elif "bobina" in maquina_sel.lower():
                 st.write("📜 Mostrando detalles de bobina (Materia Prima / Medidas).")
                 cols = ["OT_id", "Cliente-articulo", "MateriaPrima", "Gramaje", "PliAnc", "PliLar", "CantidadPliegos", "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate"]
            elif any(k in maquina_sel.lower() for k in ["offset", "flexo", "impres", "heidel"]):
                st.write("🎨 Mostrando colores del trabajo de impresión.")
                cols = ["OT_id", "Cliente-articulo", "Poses", "CantidadPliegosNetos","CantidadPliegos", "Colores", "CodigoTroquel", "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate"]
            else:
                cols = ["OT_id", "Cliente-articulo", "CantidadPliegos", "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate"]

            cols_exist = [c for c in cols if c in df_maquina.columns]
            df_maquina_display = df_maquina[cols_exist].drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_maquina_display, use_container_width=True)
            
            # --- Custom Download Button ---
            buf = dataframe_to_excel_bytes(df_maquina_display, sheet_name=f"Detalle {maquina_sel[:25]}")
            safe_name = maquina_sel.replace("/", "_").replace("\\", "_")
            st.download_button(
                label="⬇️ Descargar Datos en Excel",
                data=buf,
                file_name=f"Detalle_Maquina_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_maq_detail"
            )
            # ------------------------------
        else:
            st.info("No hay detalle por máquina disponible.")

def render_download_section(schedule, resumen_ot, carga_md):
    """Renders the unified download section."""
    st.subheader("💾 Exportar")

    if schedule.empty:
        st.info("No hay plan para exportar.")
        return

    # Generate buffers
    buf_excel = generar_excel_bytes(schedule, resumen_ot, carga_md)
    buf_ot, df_ot_horiz = generar_excel_ot_bytes(schedule)
    csv_str_maq = generar_csv_maquina_str(schedule)
    csv_str_ot = generar_csv_ot_str(df_ot_horiz)

    st.write("---")
    col_maq, col_ot = st.columns(2)
    
    with col_maq:
        st.markdown("#### 🏭 Por Máquina")
        st.caption("Planificación vertical, ideal para operarios.")
        
        st.download_button(
            "⬇️ Excel (Por Máquina + Datos)",
            data=buf_excel,
            file_name="Plan_Produccion_Theiler.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_excel_maq"
        )
        
        # st.download_button(
        #     "⬇️ CSV (Compatible Excel 2010)",
        #     data=csv_str_maq,
        #     file_name="Plan_Produccion_Theiler.csv",
        #     mime="text/csv",
        #     key="btn_csv_maq"
        # )

    with col_ot:
        st.markdown("#### 📦 Por Orden de Trabajo")
        st.caption("Visión de flujo (horizontal).")

        st.download_button(
            "⬇️ Excel (Horizontal por OT)",
            data=buf_ot,
            file_name="Plan_Produccion_Por_OT.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_excel_ot"
        )
        
        # if csv_str_ot:
        #     st.download_button(
        #         "⬇️ CSV (Horizontal compatible 2010)",
        #         data=csv_str_ot,
        #         file_name="Plan_Produccion_Por_OT.csv",
        #         mime="text/csv",
        #         key="btn_csv_ot"
        #     )
