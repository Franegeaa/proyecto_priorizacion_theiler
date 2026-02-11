import streamlit as st
from datetime import date
import pandas as pd
from modules.utils.exporters import dataframe_to_excel_bytes
from modules.utils.app_utils import ordenar_maquinas_personalizado
from modules.ui_components.render_save_section import render_save_section

def render_details_section(schedule, detalle_maquina, df, cfg=None, pm=None): # Added cfg param
    """Renders the interactive details section."""
    st.subheader("🔎 Detalle interactivo")
    modo = st.radio("Ver detalle por:", ["Plan Completo (Todas)", "Máquina", "Orden de Trabajo (OT)"], horizontal=True)

    if modo == "Orden de Trabajo (OT)":
        if not schedule.empty: 
            opciones = ["(Todas)"] + sorted(schedule["OT_id"].unique().tolist())
            elegido = st.selectbox("Elegí OT:", opciones)
            df_show = schedule if elegido == "(Todas)" else schedule[schedule["OT_id"] == elegido]
            df_show = df_show.drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            
            # --- Sanitize for Streamlit/Arrow ---
            # Drop internal columns
            df_show = df_show.loc[:, ~df_show.columns.str.startswith("_")]
            # Convert object columns to string to handle mixed types (e.g. Troquel/IDs)
            for col in df_show.select_dtypes(include=['object']).columns:
                df_show[col] = df_show[col].fillna("").astype(str)
            # ------------------------------------

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

    elif modo == "Máquina":
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
            
            # Add "Eliminar" column (Virtual)
            df_full["Eliminar OT"] = False
            
            # --- FILTERING LOGIC ---
            col_f1, col_f2, col_f3 = st.columns([1, 2, 2])
            
            with col_f1:
                show_skipped = st.toggle("Mostrar Saltados", value=False)
            
            with col_f2:
                # Get unique processes from the full dataset (before other filters to avoid disappearing options?)
                # Or after? Usually user wants to see what's available. 
                # Let's use unique values from df_full (which is sorted but not filtered yet)
                unique_procs = sorted(df_full["Proceso"].astype(str).unique().tolist())
                filtro_proc = st.multiselect("Filtrar por Proceso:", options=unique_procs, placeholder="(Todos)")
                
            with col_f3:
                unique_maqs = sorted(df_full["Maquina"].astype(str).unique().tolist())
                filtro_maq = st.multiselect("Filtrar por Máquina:", options=unique_maqs, placeholder="(Todas)")
            
            # Apply Filters
            if not show_skipped:
                df_full = df_full[~df_full["IsSkipped"].astype(bool)]
            
            if filtro_proc:
                df_full = df_full[df_full["Proceso"].astype(str).isin(filtro_proc)]
                
            if filtro_maq:
                df_full = df_full[df_full["Maquina"].astype(str).isin(filtro_maq)]
            
            # Rename for display
            df_editor = df_full.rename(columns={
                "IsOutsourced": "Tercerizar",
                "IsSkipped": "Saltar",
                "ManualPriority": "Prioridad Manual",
                "Urgente": "Urgente" 
            })
            
            # Select columns to show/edit
            cols_editable = ["Maquina", "Proceso", "OT_id", "Cliente-articulo", "CantidadPliegos",  "Prioridad Manual", "Inicio", "Fin", "DueDate", "Urgente", "Tercerizar", "Saltar", "Eliminar OT", "Colores", "CodigoTroquel", "PliAnc", "PliLar", "Duracion_h"]
            cols_final = [c for c in cols_editable if c in df_editor.columns]
            df_editor = df_editor[cols_final]

            # --- RENDER EDITOR ---
            edited_df = st.data_editor(
                df_editor,
                column_config={
                    "Urgente": st.column_config.CheckboxColumn(
                        "Urgente",
                        help="Prioridad absoluta en este proceso.",
                        default=False,
                    ),
                    "Prioridad Manual": st.column_config.NumberColumn(
                        "Prioridad",
                        help="1 = Máxima prioridad. Dejá 9999 para auto.",
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
                    "Maquina": st.column_config.TextColumn(disabled=True),
                    "OT_id": st.column_config.TextColumn(disabled=True), 
                    "Cliente-articulo": st.column_config.TextColumn("Producto", disabled=True),
                    "CantidadPliegos": st.column_config.NumberColumn("Cant. Pliegos", disabled=True),
                    "Proceso": None,
                    "Colores": st.column_config.TextColumn(disabled=True),
                    "CodigoTroquel": st.column_config.TextColumn(disabled=True),
                    "PliAnc": st.column_config.TextColumn("Ancho", disabled=True),
                    "PliLar": st.column_config.TextColumn("Largo", disabled=True),
                    "Duracion_h": st.column_config.NumberColumn("Duración (hs)", disabled=True),
                    "DueDate": st.column_config.DatetimeColumn(format="D/M HH:mm", disabled=True), 
                },
                use_container_width=True,
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

                    rows_prio = edited_df[edited_df["Prioridad Manual"] != 9999]
                    for idx, row in rows_prio.iterrows():
                        ot = str(row["OT_id"])
                        maq = str(row["Maquina"])
                        
                        # Normalize machine name to handle aliases (Manual 1 -> Troq Nº 2 Ema, etc)
                        from modules.utils.config_loader import normalize_machine_name
                        maq_normalized = normalize_machine_name(maq)
                        
                        if maq_normalized not in ["TERCERIZADO", "SALTADO"]:
                            key = (ot, maq_normalized)
                            overrides["manual_priorities"][key] = int(row["Prioridad Manual"])
                            has_changes = True

                    # Remove 9999s explicitly
                    rows_reset = edited_df[edited_df["Prioridad Manual"] == 9999]
                    for idx, row in rows_reset.iterrows():
                         ot = str(row["OT_id"])
                         maq = str(row["Maquina"])
                         key = (ot, maq)
                         if key in overrides["manual_priorities"]:
                             del overrides["manual_priorities"][key]
                             has_changes = True
                    
                    for idx, row in edited_df.iterrows():
                        ot = str(row["OT_id"])
                        proc = str(row["Proceso"])
                        key_op = (ot, proc)
                        
                        # Outsourced
                        if row["Tercerizar"]:
                            if key_op not in overrides["outsourced_processes"]:
                                overrides["outsourced_processes"].add(key_op)
                                has_changes = True
                        else:
                            if key_op in overrides["outsourced_processes"]:
                                overrides["outsourced_processes"].remove(key_op)
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

                        current_urgency = bool(row["Urgente"])
                        # We store the state. The scheduler applies it.
                        if overrides["urgency_overrides"].get(key_op) != current_urgency:
                             overrides["urgency_overrides"][key_op] = current_urgency
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
            render_save_section(pm)
            
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

    if not schedule.empty:
        st.subheader("📆 **Visualización por Día**")
        d_seleccionado = st.date_input("Seleccioná la fecha a visualizar:", value=date.today())
        
        sel_start = pd.to_datetime(d_seleccionado)
        sel_end = sel_start + pd.Timedelta(days=1)
        
        mask = (schedule["Inicio"] < sel_end) & (schedule["Fin"] > sel_start)
        df_dia = schedule[mask].copy()
        
        if not df_dia.empty:
            df_dia.sort_values(by=["Maquina", "Inicio"], inplace=True)

            # --- FILTERS ---
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                unique_procs = sorted(df_dia["Proceso"].astype(str).unique().tolist())
                filtro_proc = st.multiselect("Filtrar por Proceso:", options=unique_procs, placeholder="(Todos)", key="daily_proc_filter")
                
            with col_f2:
                unique_maqs = sorted(df_dia["Maquina"].astype(str).unique().tolist())
                filtro_maq = st.multiselect("Filtrar por Máquina:", options=unique_maqs, placeholder="(Todas)", key="daily_maq_filter")

            if filtro_proc:
                df_dia = df_dia[df_dia["Proceso"].astype(str).isin(filtro_proc)]
                
            if filtro_maq:
                df_dia = df_dia[df_dia["Maquina"].astype(str).isin(filtro_maq)]
            # ----------------
            cols_day = ["Maquina", "OT_id", "Cliente", "Cliente-articulo", "Proceso", "Inicio", "Fin", "Duracion_h", "CantidadPliegos", "DueDate"]
            cols_final = [c for c in cols_day if c in df_dia.columns]
            
            df_show_day = df_dia[cols_final]
            
            for col in df_show_day.select_dtypes(include=['object']).columns:
                df_show_day[col] = df_show_day[col].fillna("").astype(str)

            st.dataframe(df_show_day, use_container_width=True)
            
            buf = dataframe_to_excel_bytes(df_show_day, sheet_name=f"Dia {d_seleccionado}")
            st.download_button(
                label=f"⬇️ Descargar Plan del {d_seleccionado}",
                data=buf,
                file_name=f"Plan_Dia_{d_seleccionado}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_day_view"
            )
        else:
            st.warning(f"No hay tareas planificadas para el {d_seleccionado}.")
    else:
        st.info("No hay tareas planificadas.")
