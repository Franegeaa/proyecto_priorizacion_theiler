import pandas as pd
import streamlit as st

def obtener_analisis_impresion(schedule, df_original, fecha_hoy):
    """
    Analiza las órdenes de impresión programadas y sugiere un reordenamiento.
    Devuelve:
    - sugerencias: lista de diccionarios para mostrar en la UI
    - nuevas_prioridades: dict {(OT_id, Maquina): ManualPriority} para inyectar si el usuario acepta
    """
    if schedule.empty:
        return [], {}
        
    rel_cols = ["OT_id", "PrioriImp", "FechaImDdp", "Cliente-articulo"]
    cols_to_use = [c for c in rel_cols if c in df_original.columns]
    
    if "OT_id" not in cols_to_use or "PrioriImp" not in cols_to_use:
        return [], {}
        
    # Unimos la info necesaria
    df_merged = schedule.merge(
        df_original[cols_to_use].drop_duplicates(subset=["OT_id"]), 
        on="OT_id", 
        how="left",
        suffixes=('', '_orig')
    )
    
    mask_imp = df_merged["Proceso"].str.lower().str.contains("impresion")
    df_imp = df_merged[mask_imp].copy()
    
    if df_imp.empty:
        return [], {}
        
    # Identificar tareas que caen hoy
    df_imp["EsHoy"] = df_imp["Inicio"].dt.date <= fecha_hoy
    
    # Preprocesar campos
    df_imp["PrioriImp_Num"] = pd.to_numeric(df_imp["PrioriImp"], errors="coerce").fillna(999)
    # Parsear FechaImDdp si no se parseó correctamente en otro lado
    if "FechaImDdp" in df_imp.columns:
        df_imp["Fecha_dt"] = pd.to_datetime(df_imp["FechaImDdp"], errors="coerce")
    else:
        df_imp["Fecha_dt"] = pd.NaT
    
    nuevas_prioridades = {}
    sugerencias = []
    
    # Procesar máquina por máquina para respetar colas
    for maquina, g in df_imp.groupby("Maquina"):
        hoy = g[g["EsHoy"]].copy()
        futuro = g[~g["EsHoy"]].copy()
        
        # Bloquear tareas de hoy (Prioridades 1 a N) para que no se muevan de lugar
        hoy = hoy.sort_values("Inicio")
        for i, (_, row) in enumerate(hoy.iterrows()):
            nuevas_prioridades[(str(row["OT_id"]), str(row["Maquina"]))] = i + 1
            
        if futuro.empty:
            continue
            
        # Orden ideal para el futuro
        futuro_ideal = futuro.sort_values(
            by=["Fecha_dt", "PrioriImp_Num"], 
            ascending=[True, True], 
            na_position="last"
        )
        
        # Asignar prioridades futuras (empezando con un número alto para no chocar con las de hoy)
        base_prio = 50
        for i, (_, row) in enumerate(futuro_ideal.iterrows()):
            nuevas_prioridades[(str(row["OT_id"]), str(row["Maquina"]))] = base_prio + i
            
        # Detectar sugerencias para UI evaluando cómo estaban programadas de forma natural (por "Inicio")
        futuro_actual = futuro.sort_values("Inicio")
        orden_actual_ots = futuro_actual["OT_id"].tolist()
        orden_ideal_ots = futuro_ideal["OT_id"].tolist()
        
        if orden_actual_ots != orden_ideal_ots:
            for i, ot in enumerate(orden_ideal_ots):
                idx_actual = orden_actual_ots.index(ot)
                # Solo sugerimos cosas que mejoran sensiblemente (se adelantan)
                if idx_actual > i + 1:
                    ot_desplazada = orden_actual_ots[i]
                    row_info = futuro_ideal.iloc[i]
                    
                    fecha_str = "-"
                    if pd.notna(row_info.get("Fecha_dt")):
                        fecha_str = row_info["Fecha_dt"].strftime("%Y-%m-%d")
                        
                    sugerencias.append({
                        "Máquina": maquina,
                        "Acción": "Adelantar",
                        "OT": ot,
                        "Cliente/Producto": row_info.get("Cliente-articulo", ""),
                        "Prioridad (Excel)": row_info.get("PrioriImp_Num") if row_info.get("PrioriImp_Num") != 999 else "Normal",
                        "Fecha Solicitada": fecha_str,
                        "Desplaza a": ot_desplazada
                    })
                    
    return sugerencias, nuevas_prioridades

def render_printing_suggestions(schedule, df_original, fecha_hoy):
    """
    Renderiza la sección de sugerencias en la UI y maneja el evento de aplicar.
    Devuelve True si se debe recargar la app ("rerun").
    """
    if schedule is None or schedule.empty:
        return False
        
    sugerencias, nuevas_prioridades = obtener_analisis_impresion(schedule, df_original, fecha_hoy)
    
    if not sugerencias:
        return False

    with st.expander("💡 Sugerencias de Optimización (Impresión)", expanded=True):
        st.info("El sistema ha detectado oportunidades para reprogramar la impresión según las prioridades indicadas en el Excel.")
        df_sug = pd.DataFrame(sugerencias)
        
        # Separar Flexo y Offset para mayor claridad
        mascara_flexo = df_sug["Máquina"].str.lower().str.contains("flexo")
        df_flexo = df_sug[mascara_flexo]
        df_offset = df_sug[~mascara_flexo]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Sugerencias Flexo (Micro)**")
            if df_flexo.empty:
                st.write("Sin sugerencias importantes")
            else:
                st.dataframe(df_flexo, hide_index=True)
                
        with col2:
            st.markdown("**Sugerencias Offset (Cartulina/Papel)**")
            if df_offset.empty:
                st.write("Sin sugerencias importantes")
            else:
                st.dataframe(df_offset, hide_index=True)
                
        st.markdown(
            "> **Nota**: Aplicar sugerencias anclará las tareas programadas para el día de 'hoy' "
            "y reordenará las futuras siguiendo la **Fecha Imp** y **Prioridad Imp**."
        )
        
        if st.button("✨ Aplicar Sugerencias y Re-planificar", type="primary"):
            # Integrar las sugerencias en manual_priorities de session_state
            if "manual_overrides" not in st.session_state:
                st.session_state.manual_overrides = {"manual_priorities": {}}
                
            if "manual_priorities" not in st.session_state.manual_overrides:
                st.session_state.manual_overrides["manual_priorities"] = {}
                
            # Actualizar prioridades
            for k, v in nuevas_prioridades.items():
                st.session_state.manual_overrides["manual_priorities"][k] = v
                
            # Guardar en persistencia automáticamente si está conectado
            if "persistence" in st.session_state and st.session_state.persistence.connected:
                try:
                    st.session_state.persistence.save_manual_overrides(st.session_state.manual_overrides)
                except Exception as e:
                    st.warning(f"No se pudo persistir la configuración: {e}")
                    
            st.success("Sugerencias aplicadas. La página se recargará.")
            st.rerun()
            
    return False
