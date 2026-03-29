import streamlit as st
from datetime import date
import pandas as pd
from modules.utils.exporters import dataframe_to_excel_bytes
from modules.utils.app_utils import ordenar_maquinas_personalizado
from modules.ui_components.render_save_section import render_save_section

def render_details_section(schedule, detalle_maquina, df, cfg=None, pm=None): # Added cfg param
    """Renders the interactive details section."""
    st.subheader("🔎 Busqueda de tareas")
    st.markdown("""
    <style>
    [data-testid="stDataEditor"] td,
    [data-testid="stDataEditor"] th,
    [data-testid="stDataEditor"] .gdg-cell,
    [data-testid="stDataEditor"] div,
    [data-testid="stDataEditor"] span {
        font-size: 11px !important;
        font-weight: 600 !important;
    }
    [data-testid="stDataFrame"] td,
    [data-testid="stDataFrame"] th {
        font-size: 11px !important;
        font-weight: 600 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # if modo == "Orden de Trabajo (OT)":
    if not schedule.empty: 
        # Obtener nombres de las OTs para el desplegable
        ot_mapping = schedule.drop_duplicates(subset=["OT_id"])[["OT_id", "Cliente-articulo"]]
        opciones_format = []
        for _, row in ot_mapping.iterrows():
            ot_id = row["OT_id"]
            nombre = row["Cliente-articulo"]
            nombre_str = str(nombre).strip() if pd.notna(nombre) else ""
            if not nombre_str:
                nombre_str = "Sin Nombre"
            opciones_format.append(f"{ot_id} | {nombre_str}")
            
        opciones = ["(Ninguna)", "(Todas)"] + sorted(opciones_format)
        elegido_str = st.selectbox("Elegí OT:", opciones)
        
        if elegido_str == "(Ninguna)":
            elegido = "(Ninguna)"
            df_show = pd.DataFrame(columns=schedule.columns)
        elif elegido_str == "(Todas)":
            elegido = "(Todas)"
            df_show = schedule
        else:
            elegido = elegido_str.split(" | ")[0]
            df_show = schedule[schedule["OT_id"] == elegido]
            
        df_show = df_show.drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
        
        # --- Sanitize for Streamlit/Arrow ---
        # Drop internal columns
        df_show = df_show.loc[:, ~df_show.columns.str.startswith("_")]
        # Convert object columns to string to handle mixed types (e.g. Troquel/IDs)
        for col in df_show.select_dtypes(include=['object']).columns:
            df_show[col] = df_show[col].fillna("").astype(str)
        # ------------------------------------

        st.dataframe(df_show, width='stretch')
        
        # --- Custom Download Button ---
        # buf = dataframe_to_excel_bytes(df_show, sheet_name="Detalle OT")
        # st.download_button(
        #     label="⬇️ Descargar Datos en Excel",
        #     data=buf,
        #     file_name=f"Detalle_OT_{elegido if elegido != '(Todas)' else 'Todas'}.xlsx",
        #     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        #     key="btn_dl_ot_detail"
        # )
        # # ------------------------------
    else:
        st.info("No hay tareas planificadas.")
    
    st.subheader("🔎 Detalle interactivo")
    modo = st.radio("Ver detalle por:", ["Plan Completo (Todas)", "Máquina"], horizontal=True)

    if modo == "Máquina":
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
            
            # --- Sanitize for Streamlit/Arrow ---
            # Drop internal columns
            df_maquina_display = df_maquina_display.loc[:, ~df_maquina_display.columns.str.startswith("_")]
            # Convert object columns to string
            for col in df_maquina_display.select_dtypes(include=['object']).columns:
                df_maquina_display[col] = df_maquina_display[col].fillna("").astype(str)
            # ------------------------------------

            st.dataframe(df_maquina_display, width='stretch')
            
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

    else: # "Plan Completo (Todas)"

        if not schedule.empty:
            st.write("📋 **Planificación Completa (Todas las Órdenes) - Edición**")
            st.caption("Editá la tabla para ajustar prioridades o marcar excepciones.")
            
            # --- PREPARE DATA FOR EDITOR ---
            df_full = schedule.sort_values(by=["Proceso", "Maquina", "Inicio"]).copy()

            # --- MERGE STATIC COLUMNS (Colores, Troquel) ---
            # Needed because schedule might not carry them by default, but df (input) does.
            if "CodigoTroquel" not in df_full.columns and "CodigoTroquel" in df.columns:
                 # Use drop_duplicates on right side to avoid exploding rows if product repeats in df
                 right_df = df[["CodigoProducto", "Subcodigo", "CodigoTroquel"]].drop_duplicates()
                 df_full = df_full.merge(
                     right_df,
                     how="left",
                     on=["CodigoProducto", "Subcodigo"]
                 )
            
            if "Colores" not in df_full.columns and "Colores" in df.columns:
                 right_df = df[["CodigoProducto", "Subcodigo", "Colores"]].drop_duplicates()
                 df_full = df_full.merge(
                     right_df,
                     how="left",
                     on=["CodigoProducto", "Subcodigo"]
                 )

            if "PliAnc" not in df_full.columns and "PliAnc" in df.columns:
                 right_df = df[["CodigoProducto", "Subcodigo", "PliAnc"]].drop_duplicates()
                 df_full = df_full.merge(
                     right_df,
                     how="left",
                     on=["CodigoProducto", "Subcodigo"]
                 )

            if "PliLar" not in df_full.columns and "PliLar" in df.columns:
                 right_df = df[["CodigoProducto", "Subcodigo", "PliLar"]].drop_duplicates()
                 df_full = df_full.merge(
                     right_df,
                     how="left",
                     on=["CodigoProducto", "Subcodigo"]
                 )

            
            # Add editing columns if not present
            if "ManualPriority" not in df_full.columns: df_full["ManualPriority"] = 9999
            if "IsOutsourced" not in df_full.columns: df_full["IsOutsourced"] = False
            if "IsSkipped" not in df_full.columns: df_full["IsSkipped"] = False
            
            # Ensure MateriaPrimaPlanta is boolean for checkbox display
            if "MateriaPrimaPlanta" in df_full.columns:
                df_full["MateriaPrimaPlanta"] = df_full["MateriaPrimaPlanta"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
            else:
                df_full["MateriaPrimaPlanta"] = False
            
            # Add "Eliminar" column (Virtual)
            df_full["Eliminar OT"] = False
            
            # --- CALCULATE ESTIMATED COMPLETION DATE PER OT ---
            # Group by OT_id and get the max 'Fin' date
            ot_completion = df_full.groupby("OT_id")["Fin"].max().reset_index()
            ot_completion.rename(columns={"Fin": "FechaEntregaEstimada"}, inplace=True)
            
            # Merge back into df_full
            df_full = df_full.merge(ot_completion, on="OT_id", how="left")
            
            # --- INJECT IDLE ROWS (TIEMPO OCIOSO) ---
            idle_rows = []
            
            # Exclude virtual machines from idle calculations
            real_tasks = df_full[~df_full["Maquina"].isin(["SALTADO", "TERCERIZADO", "POOL_DESCARTONADO"])].copy()
            
            for maquina, group in real_tasks.groupby("Maquina"):
                # Sort Chronologically
                group = group.sort_values(by="Inicio")
                
                prev_fin = None
                for _, row in group.iterrows():
                    curr_inicio = row["Inicio"]
                    if pd.notna(curr_inicio) and pd.notna(prev_fin):
                        # Convert both to datetime to be safe
                        inicio_dt = pd.to_datetime(curr_inicio)
                        fin_dt = pd.to_datetime(prev_fin)
                        
                        if inicio_dt > fin_dt:
                            # Calculate duration in hours
                            gap_h = (inicio_dt - fin_dt).total_seconds() / 3600.0
                            
                            idle_rows.append({
                                "Maquina": maquina,
                                "Proceso": "Inactivo",
                                "OT_id": "---",
                                "Cliente-articulo": "=== TIEMPO OCIOSO ===",
                                "Cliente": "N/A",
                                "Inicio": fin_dt,
                                "Fin": inicio_dt,
                                "Duracion_h": gap_h,
                                "IsSkipped": False, # Required for filter logic
                                "Eliminar OT": False,
                                "IsOutsourced": False,
                                "MateriaPrimaPlanta": False,
                                "Urgente": False,
                                "ManualPriority": 9999
                            })
                    
                    # Update prev_fin
                    if pd.notna(row["Fin"]):
                        # If a task finishes later, update. 
                        # We use max in case of overlapping or parallel tasks (unlikely but safe)
                        if prev_fin is None or pd.to_datetime(row["Fin"]) > pd.to_datetime(prev_fin):
                            prev_fin = row["Fin"]
                            
            if idle_rows:
                df_idle = pd.DataFrame(idle_rows)
                df_full = pd.concat([df_full, df_idle], ignore_index=True)
                # Re-sort everything including the new rows
                df_full.sort_values(by=["Maquina", "Inicio"], inplace=True)
            
            # --- FILTERING LOGIC ---
            col_f1, col_f2, col_f3 = st.columns([1, 2, 2])
            
            with col_f1:
                show_skipped = st.toggle("Mostrar Saltados", value=False)
            
            with col_f2:
                unique_procs = sorted(df_full["Proceso"].astype(str).unique().tolist())
                filtro_proc = st.multiselect("Filtrar por Proceso:", options=unique_procs, placeholder="(Todos)")
                
            with col_f3:
                unique_maqs = sorted(df_full["Maquina"].astype(str).unique().tolist())
                filtro_maq = st.multiselect("Filtrar por Máquina:", options=unique_maqs, placeholder="(Todas)")
            
            # --- DATE FILTER ---
            col_d1, col_d2 = st.columns(2)
            # Calculate min/max dates from data
            fechas_inicio = pd.to_datetime(df_full["Inicio"], errors="coerce").dropna()
            fecha_min = fechas_inicio.min().date() if not fechas_inicio.empty else date.today()
            fecha_max = fechas_inicio.max().date() if not fechas_inicio.empty else date.today()
            
            with col_d1:
                filtro_fecha_desde = st.date_input("Inicio desde:", value=fecha_min, min_value=fecha_min, max_value=fecha_max, key="filtro_fecha_desde")
            with col_d2:
                filtro_fecha_hasta = st.date_input("Inicio hasta:", value=fecha_max, min_value=fecha_min, max_value=fecha_max, key="filtro_fecha_hasta")

            # Apply Filters
            if not show_skipped:
                df_full = df_full[~df_full["IsSkipped"].astype(bool)]
            
            if filtro_proc:
                df_full = df_full[df_full["Proceso"].astype(str).isin(filtro_proc)]
                
            if filtro_maq:
                df_full = df_full[df_full["Maquina"].astype(str).isin(filtro_maq)]
            
            # Apply date filter
            if filtro_fecha_desde and filtro_fecha_hasta:
                df_full["_inicio_date"] = pd.to_datetime(df_full["Inicio"], errors="coerce").dt.date
                df_full = df_full[(df_full["_inicio_date"] >= filtro_fecha_desde) & (df_full["_inicio_date"] <= filtro_fecha_hasta)]
                df_full.drop(columns=["_inicio_date"], inplace=True)
            
            # Rename for display
            df_editor = df_full.rename(columns={
                "IsOutsourced": "Tercerizar",
                "IsSkipped": "Saltar",
                "ManualPriority": "Prioridad",
                "Urgente": "Urgente",
                "MateriaPrimaPlanta": "MP Pendiente",
                "PeliculaArt": "Chapa Pend",
                "TroquelArt": "Troquel Pend",
                "FechaLlegadaChapas": "Llegada Chapas",
                "FechaLlegadaTroquel": "Llegada Troquel"
            })
            
            # Pre-fill 'Prioridad' with Excel priority if it wasn't manually overridden yet
            if "PrioriImp" in df_editor.columns:
                 # Ensure proper numeric typing to avoid errors with object comparisons
                 df_editor["Prioridad"] = pd.to_numeric(df_editor["Prioridad"], errors="coerce").fillna(9999)
                 df_editor["PrioriImp"] = pd.to_numeric(df_editor["PrioriImp"], errors="coerce").fillna(9999)
                 
                 # Si la prioridad manual es 9999 (el default sin override), miramos si hay en el Excel
                 mask_no_override = df_editor["Prioridad"] == 9999
                 mask_excel_has_val = df_editor["PrioriImp"] != 9999
                 mask_excel_valid = df_editor["PrioriImp"].notna()
                 # Barnizado comparte la prioridad de Impresión (PrioriImp)
                 mask_es_impresion = df_editor["Proceso"].astype(str).str.lower().str.contains("impresi|barniz", na=False)
                 
                 final_mask = mask_no_override & mask_excel_has_val & mask_excel_valid & mask_es_impresion
                 df_editor.loc[final_mask, "Prioridad"] = df_editor.loc[final_mask, "PrioriImp"]
            
            # Pre-fill 'Prioridad' con PrioriTr para Troquelado
            if "PrioriTr" in df_editor.columns:
                 df_editor["Prioridad"] = pd.to_numeric(df_editor["Prioridad"], errors="coerce").fillna(9999)
                 df_editor["PrioriTr"] = pd.to_numeric(df_editor["PrioriTr"], errors="coerce").fillna(9999)
                 
                 mask_no_override_tr = df_editor["Prioridad"] == 9999
                 mask_excel_has_val_tr = df_editor["PrioriTr"] != 9999
                 mask_excel_valid_tr = df_editor["PrioriTr"].notna()
                 mask_es_troquelado = df_editor["Proceso"].astype(str).str.lower().str.contains("troquel", na=False)
                 
                 final_mask_tr = mask_no_override_tr & mask_excel_has_val_tr & mask_excel_valid_tr & mask_es_troquelado
                 df_editor.loc[final_mask_tr, "Prioridad"] = df_editor.loc[final_mask_tr, "PrioriTr"]

            # Pre-fill 'Prioridad' con PrioriDesc para Descartonado
            if "PrioriDesc" in df_editor.columns:
                 df_editor["Prioridad"] = pd.to_numeric(df_editor["Prioridad"], errors="coerce").fillna(9999)
                 df_editor["PrioriDesc"] = pd.to_numeric(df_editor["PrioriDesc"], errors="coerce").fillna(9999)
                 
                 mask_no_override_desc = df_editor["Prioridad"] == 9999
                 mask_excel_has_val_desc = df_editor["PrioriDesc"] != 9999
                 mask_excel_valid_desc = df_editor["PrioriDesc"].notna()
                 mask_es_descartonado = df_editor["Proceso"].astype(str).str.lower().str.contains("descarton", na=False)
                 
                 final_mask_desc = mask_no_override_desc & mask_excel_has_val_desc & mask_excel_valid_desc & mask_es_descartonado
                 df_editor.loc[final_mask_desc, "Prioridad"] = df_editor.loc[final_mask_desc, "PrioriDesc"]

            # Select columns to show/edit
            cols_editable = ["Maquina", "Proceso", "OT_id", "Cliente-articulo", "CantidadPliegos",  "Prioridad", "Inicio", "Fin", "DueDate", "FechaEntregaEstimada", "Saltar", "Urgente", "Chapa Pend", "Llegada Chapas", "Troquel Pend", "Llegada Troquel", "MP Pendiente", "Tercerizar", "Eliminar OT", "Colores", "CodigoTroquel", "PliAnc", "PliLar", "Duracion_h"]
            cols_final = [c for c in cols_editable if c in df_editor.columns]
            df_editor = df_editor[cols_final]
            
            # Ensure proper types for booleans and dates
            if "Chapa Pend" in df_editor.columns:
                 df_editor["Chapa Pend"] = df_editor["Chapa Pend"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
            if "Troquel Pend" in df_editor.columns:
                 df_editor["Troquel Pend"] = df_editor["Troquel Pend"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
            if "Llegada Chapas" in df_editor.columns:
                 df_editor["Llegada Chapas"] = pd.to_datetime(df_editor["Llegada Chapas"], errors="coerce")
            if "Llegada Troquel" in df_editor.columns:
                 df_editor["Llegada Troquel"] = pd.to_datetime(df_editor["Llegada Troquel"], errors="coerce")

            # --- PERSISTENT COLUMN SELECTION ---
            if "details_column_order" not in st.session_state:
                st.session_state.details_column_order = cols_final
            
            # Ensure saved columns still exist in the current dataframe to prevent Streamlit errors
            valid_saved_cols = [c for c in st.session_state.details_column_order if c in cols_final]
            
            with st.expander("⚙️ Configurar Columnas Visibles", expanded=False):
                # The multiselect order determines the DataFrame column order.
                selected_cols = st.multiselect(
                    "Agrega, quita o reordena columnas borrándolas y volviéndolas a agregar:",
                    options=cols_final,
                    default=valid_saved_cols,
                    key="details_col_multiselect_widget"
                )
                
                # Update saved order, only if changed to avoid unnecessary reruns
                if st.session_state.details_column_order != selected_cols:
                    st.session_state.details_column_order = selected_cols
                    st.rerun()

            # --- COLORING LOGIC BY DUE DATE & IDLE ---
            from datetime import date
            def highlight_due_date(row):
                # We need to return an array of styles with the same length as the row
                bg_color = ""
                
                # Check for idle row first
                if str(row.get("Proceso")) == "Inactivo":
                    bg_color = "background-color: rgba(135, 206, 250, 0.5); font-style: italic; color: black;"
                    return [bg_color] * len(row)
                
                try:
                    due_date = pd.to_datetime(row["DueDate"])
                    if pd.notna(due_date):
                        today = date.today()
                        # Calculate start of current week (Monday) and end of current week (Sunday)
                        start_of_this_week = today - pd.Timedelta(days=today.weekday())
                        end_of_this_week = start_of_this_week + pd.Timedelta(days=6)
                        
                        start_of_next_week = end_of_this_week + pd.Timedelta(days=1)
                        end_of_next_week = start_of_next_week + pd.Timedelta(days=6)
                        
                        due_date_date = due_date.date()
                        
                        if due_date_date < start_of_this_week:
                            # Past Due -> Red
                            bg_color = "background-color: rgba(255, 50, 50, 0.6); font-weight: bold;"
                        elif start_of_this_week <= due_date_date <= end_of_this_week:
                            # This week -> Orange
                            bg_color = "background-color: rgba(255, 140, 0, 0.8); color: black; font-weight: bold;"
                        elif start_of_next_week <= due_date_date <= end_of_next_week:
                            # Next week -> Yellow
                            bg_color = "background-color: rgba(255, 220, 0, 0.8); color: black; font-weight: bold;"
                except Exception:
                    pass
                
                return [bg_color] * len(row)

            # Apply styler and general formatting
            styled_df = df_editor.style.apply(highlight_due_date, axis=1).set_properties(**{'font-size': '11px', 'font-weight': '600'})
            
            format_dict = {}
            if "CantidadPliegos" in df_editor.columns:
                format_dict["CantidadPliegos"] = "{:.0f}"
            if "PliAnc" in df_editor.columns:
                # Convert to numeric if not already, to prevent formatting errors on strings
                df_editor["PliAnc"] = pd.to_numeric(df_editor["PliAnc"], errors="coerce")
                format_dict["PliAnc"] = "{:.2f}"
            if "PliLar" in df_editor.columns:
                df_editor["PliLar"] = pd.to_numeric(df_editor["PliLar"], errors="coerce")
                format_dict["PliLar"] = "{:.2f}"
            if "Duracion_h" in df_editor.columns:
                df_editor["Duracion_h"] = pd.to_numeric(df_editor["Duracion_h"], errors="coerce")
                format_dict["Duracion_h"] = "{:.2f}"
                
            if format_dict:
                styled_df = styled_df.format(format_dict, na_rep="")

            # --- RENDER EDITOR ---
            edited_df = st.data_editor(
                styled_df,
                column_config={
                    "Urgente": st.column_config.CheckboxColumn(
                        "Urgente",
                        help="Prioridad absoluta en este proceso.",
                        default=False,
                    ),
                    "MP Pendiente": st.column_config.CheckboxColumn(
                        "MP Pendiente",
                        help="Materia Prima pendiente. Desactivar cuando llegue el material.",
                        default=False,
                    ),
                    "Chapa Pend": st.column_config.CheckboxColumn(
                        "Chapa Pend",
                        help="Chapa pendiente (PeliculaArt). Desactivar cuando llegue la chapa.",
                        default=False,
                    ),
                    "Llegada Chapas": st.column_config.DateColumn(
                        "Llegada Chapas",
                        help="Fecha de llegada de chapas. Editable.",
                        format="DD/MM/YYYY",
                    ),
                    "Troquel Pend": st.column_config.CheckboxColumn(
                        "Troquel Pend",
                        help="Troquel pendiente (TroquelArt). Desactivar cuando llegue el troquel.",
                        default=False,
                    ),
                    "Llegada Troquel": st.column_config.DateColumn(
                        "Llegada Troquel",
                        help="Fecha de llegada de troquel. Editable.",
                        format="DD/MM/YYYY",
                    ),
                    "Prioridad": st.column_config.NumberColumn(
                        "Prioridad",
                        help="Prioridad. Si venía del Excel se muestra aquí. Cambiala para sobreescribirla o dejala en 9999 para modo automático.",
                        min_value=1,
                        max_value=9999,
                        step=1,
                    ),
                    "Tercerizar": st.column_config.CheckboxColumn(
                        "Tercerizar",
                        help="Marcar para asignar a proveedor externo",
                        default=False,
                    ),
                    "Saltar": st.column_config.CheckboxColumn(
                        "Saltar",
                        help="Marcar para saltar este proceso",
                        default=False,
                    ),
                    "Eliminar OT": st.column_config.CheckboxColumn(
                        "Eliminar OT",
                        help="Marcar para eliminar TODA la orden",
                        default=False,
                    ),
                    "Inicio": st.column_config.DatetimeColumn(format="D/M HH:mm", disabled=True),
                    "Fin": st.column_config.DatetimeColumn(format="D/M HH:mm", disabled=True),
                    "FechaEntregaEstimada": st.column_config.DatetimeColumn("Fin Estimado", format="D/M HH:mm", disabled=True),
                    "Maquina": st.column_config.TextColumn(disabled=True),
                    "OT_id": None, 
                    "Cliente-articulo": st.column_config.TextColumn("Producto", disabled=True),
                    "CantidadPliegos": st.column_config.NumberColumn("Cant. Pliegos", disabled=True),
                    "Proceso": None,
                    "Colores": st.column_config.TextColumn(disabled=True),
                    "CodigoTroquel": st.column_config.TextColumn(disabled=True),
                    "PliAnc": st.column_config.NumberColumn("Ancho", disabled=True, format="%.2f"),
                    "PliLar": st.column_config.NumberColumn("Largo", disabled=True, format="%.2f"),
                    "Duracion_h": st.column_config.NumberColumn("Duración (hs)", disabled=True, format="%.2f"),
                    "DueDate": st.column_config.DatetimeColumn(format="D/M HH:mm", disabled=True), 
                },
                column_order=st.session_state.details_column_order,
                width='stretch',
                height=600,
                hide_index=True,
                key="editor_plan_completo"
            )

            # --- PROCESS CHANGES BUTTON ---
            col_btn, col_info = st.columns([1, 3])
            
            if col_btn.button("Aplicar Cambios y Recalcular"):
                if cfg and "manual_overrides" in st.session_state:
                    overrides = st.session_state.manual_overrides
                    has_changes = False
                    
                    if "urgency_overrides" not in overrides:
                        overrides["urgency_overrides"] = {}
                    if "mp_overrides" not in overrides:
                        overrides["mp_overrides"] = {}
                    if "pelicula_overrides" not in overrides:
                        overrides["pelicula_overrides"] = {}
                    if "troquel_overrides" not in overrides:
                        overrides["troquel_overrides"] = {}
                    if "fecha_chapas_overrides" not in overrides:
                        overrides["fecha_chapas_overrides"] = {}
                    if "fecha_troquel_overrides" not in overrides:
                        overrides["fecha_troquel_overrides"] = {}

                    from modules.utils.config_loader import normalize_machine_name
                    
                    # Create a normalized mapping to avoid ° vs º lookup failures
                    maq_to_proc_norm = {}
                    for m, p in zip(cfg["maquinas"]["Maquina"], cfg["maquinas"]["Proceso"]):
                        maq_to_proc_norm[normalize_machine_name(m)] = p
                    
                    rows_prio = edited_df[(pd.to_numeric(edited_df["Prioridad"], errors="coerce").fillna(9999) != 9999) & (edited_df["OT_id"] != "---")]
                    for idx, row in rows_prio.iterrows():
                        ot = str(row["OT_id"])
                        maq = str(row["Maquina"])
                        
                        maq_normalized = normalize_machine_name(maq)
                        
                        if maq_normalized not in ["TERCERIZADO", "SALTADO"]:
                            # First, remove any existing priorities for this OT that correspond to the SAME process type
                            # This prevents stale priorities from competing with the new one
                            current_proc = maq_to_proc_norm.get(maq_normalized, "")
                            if current_proc:
                                stale_keys = []
                                for (p_ot, p_maq) in list(overrides["manual_priorities"].keys()):
                                    if p_ot == ot and normalize_machine_name(p_maq) != maq_normalized:
                                        # Check if the other machine does the same process
                                        other_proc = maq_to_proc_norm.get(normalize_machine_name(p_maq), "")
                                        if other_proc == current_proc or (current_proc in other_proc and len(current_proc)>3):
                                            stale_keys.append((p_ot, p_maq))
                                for sk in stale_keys:
                                    del overrides["manual_priorities"][sk]
                                    has_changes = True

                            # Set the new priority
                            key = (ot, maq_normalized)
                            overrides["manual_priorities"][key] = int(row["Prioridad"])
                            has_changes = True

                    # Remove 9999s explicitly
                    rows_reset = edited_df[(pd.to_numeric(edited_df["Prioridad"], errors="coerce").fillna(9999) == 9999) & (edited_df["OT_id"] != "---")]
                    for idx, row in rows_reset.iterrows():
                         ot = str(row["OT_id"])
                         maq = str(row["Maquina"])
                         
                         from modules.utils.config_loader import normalize_machine_name
                         maq_normalized = normalize_machine_name(maq)
                         
                         key = (ot, maq_normalized)
                         if key in overrides["manual_priorities"]:
                             del overrides["manual_priorities"][key]
                             has_changes = True
                             
                         # Also try to delete original exact string just in case there's old corrupted data
                         exact_key = (ot, maq)
                         if exact_key in overrides["manual_priorities"]:
                             del overrides["manual_priorities"][exact_key]
                             has_changes = True
                    
                    for idx, row in edited_df.iterrows():
                        ot = str(row["OT_id"])
                        if ot == "---":
                            continue # Ignore dummy rows (Inactivo)
                            
                        proc = str(row["Proceso"])
                        key_op = (ot, proc)
                        
                        # Outsourced
                        if row["Tercerizar"]:
                            if key_op not in overrides["outsourced_processes"]:
                                overrides["outsourced_processes"].add(key_op)
                                has_changes = True
                                
                            # NUEVO: Si tercerizamos Troquelado, el Descartonado de la misma OT se terceriza también.
                            if proc.strip().lower() == "troquelado":
                                key_desc = (ot, "Descartonado")
                                if key_desc not in overrides["outsourced_processes"]:
                                    overrides["outsourced_processes"].add(key_desc)
                                    has_changes = True
                        else:
                            if key_op in overrides["outsourced_processes"]:
                                overrides["outsourced_processes"].remove(key_op)
                                has_changes = True
                                
                            # Si se des-terceriza Troquelado, también quitamos Descartonado (opcional, pero consistente)
                            if proc.strip().lower() == "troquelado":
                                key_desc = (ot, "Descartonado")
                                if key_desc in overrides["outsourced_processes"]:
                                    overrides["outsourced_processes"].remove(key_desc)
                                    has_changes = True
                                
                        # Skipped
                        if row["Saltar"]:
                            if key_op not in overrides["skipped_processes"]:
                                overrides["skipped_processes"].add(key_op)
                                has_changes = True
                        else:
                            if key_op in overrides["skipped_processes"]:
                                overrides["skipped_processes"].remove(key_op)
                                has_changes = True

                        # Urgente override
                        current_urgency = bool(row["Urgente"])
                        if overrides["urgency_overrides"].get(key_op) != current_urgency:
                             overrides["urgency_overrides"][key_op] = current_urgency
                             has_changes = True

                        # MP Pendiente override — solo guardar cuando se DESTILDA (False)
                        # Si está tildado (True), NO guardamos nada: el valor viene del Excel.
                        current_mp = bool(row["MP Pendiente"])
                        all_procs_for_ot = edited_df[edited_df["OT_id"] == ot]["Proceso"].unique()
                        if not current_mp:
                             # Usuario destildó → guardar False para TODOS los procesos de la OT
                             for p in all_procs_for_ot:
                                 if overrides["mp_overrides"].get((ot, str(p))) != False:
                                     overrides["mp_overrides"][(ot, str(p))] = False
                                     has_changes = True
                        else:
                             # Usuario tildó (o ya estaba tildado) → REMOVER override para que use el Excel
                             for p in all_procs_for_ot:
                                 if (ot, str(p)) in overrides["mp_overrides"]:
                                     del overrides["mp_overrides"][(ot, str(p))]
                                     has_changes = True
                                
                        # Chapa Pendiente override
                        if "Chapa Pend" in row:
                            current_chapa = bool(row["Chapa Pend"])
                            if not current_chapa:
                                 for p in all_procs_for_ot:
                                     if overrides["pelicula_overrides"].get((ot, str(p))) != False:
                                         overrides["pelicula_overrides"][(ot, str(p))] = False
                                         has_changes = True
                            else:
                                 for p in all_procs_for_ot:
                                     if (ot, str(p)) in overrides["pelicula_overrides"]:
                                         del overrides["pelicula_overrides"][(ot, str(p))]
                                         has_changes = True                 

                        # Troquel Pendiente override
                        if "Troquel Pend" in row:
                            current_troq = bool(row["Troquel Pend"])
                            if not current_troq:
                                 for p in all_procs_for_ot:
                                     if overrides["troquel_overrides"].get((ot, str(p))) != False:
                                         overrides["troquel_overrides"][(ot, str(p))] = False
                                         has_changes = True
                            else:
                                 for p in all_procs_for_ot:
                                     if (ot, str(p)) in overrides["troquel_overrides"]:
                                         del overrides["troquel_overrides"][(ot, str(p))]
                                         has_changes = True

                        # Llegada Chapas override
                        if "Llegada Chapas" in row:
                            dt_chapa = row["Llegada Chapas"]
                            for p in all_procs_for_ot:
                                if pd.notna(dt_chapa):
                                    if overrides["fecha_chapas_overrides"].get((ot, str(p))) != dt_chapa:
                                        overrides["fecha_chapas_overrides"][(ot, str(p))] = dt_chapa
                                        has_changes = True
                                else:
                                    if (ot, str(p)) in overrides["fecha_chapas_overrides"]:
                                        del overrides["fecha_chapas_overrides"][(ot, str(p))]
                                        has_changes = True

                        # Llegada Troquel override
                        if "Llegada Troquel" in row:
                            dt_troq = row["Llegada Troquel"]
                            for p in all_procs_for_ot:
                                if pd.notna(dt_troq):
                                    if overrides["fecha_troquel_overrides"].get((ot, str(p))) != dt_troq:
                                        overrides["fecha_troquel_overrides"][(ot, str(p))] = dt_troq
                                        has_changes = True
                                else:
                                    if (ot, str(p)) in overrides["fecha_troquel_overrides"]:
                                        del overrides["fecha_troquel_overrides"][(ot, str(p))]
                                        has_changes = True
                                        
                        # Delete OT (Blacklist)
                        if row["Eliminar OT"]:
                            overrides["blacklist_ots"].add(ot)
                            has_changes = True
                            
                    if has_changes:
                        st.success("✅ Cambios registrados. Recalculando...")
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios.")

            # --- SAVE SECTION ---
            #render_save_section(pm)
            
            # --- RESTORE SECTION (For Blacklisted OTs) ---
            if cfg and "manual_overrides" in st.session_state:
                blacklist = st.session_state.manual_overrides["blacklist_ots"]
                if blacklist:
                     with st.expander(f"♻️ Restaurar Órdenes Eliminadas ({len(blacklist)})"):
                        to_restore = st.multiselect("Seleccionar OT para restaurar:", sorted(list(blacklist)))
                        if st.button("Restaurar Seleccionadas"):
                            for ot in to_restore:
                                st.session_state.manual_overrides["blacklist_ots"].remove(ot)
                            st.rerun()
                            
        else:
            st.info("No hay tareas planificadas.")
