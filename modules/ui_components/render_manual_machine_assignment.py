import streamlit as st
import pandas as pd
from modules.schedulers.machines import validar_medidas_troquel

def render_manual_machine_assignment(cfg, df, maquinas_activas):
    """
    Renders UI for manual assignment of OTs to specific machines:
    - Troqueladora Manual 3
    - Iberica
    - Descartonadora 3
    - Descartonadora 4
    """

    # Target machines for this feature
    # We normalise names to partial matches as user requested: 
    # "Troqueladora manual 3", "Iberica", "Descartonadora 3", "Descartonadora 4"
    # But maquinas_activas comes from DB which might have different naming.
    # We look for partial matches.
    
    target_keywords = ["Troq Nº 1 Gus", "Troq Nº 2 Ema", "Duyan", "Manual 3", "Iberica", "Descartonadora 3", "Descartonadora 4"]
    
    active_targets = []
    for m in maquinas_activas:
        for k in target_keywords:
            if k.lower() in m.lower():
                active_targets.append(m)
                break
    
    active_targets = sorted(list(set(active_targets)))

    if not active_targets:
        return {}
        
    st.subheader("📌 Asignación Manual de Trabajos")
    st.info("Utiliza esta sección para asignar manualmente órdenes a máquinas específicas. Estas órdenes **NO** serán procesadas por la lógica automática.")
    
    if "manual_assignments" not in st.session_state:
        st.session_state.manual_assignments = {}

    mode = st.radio("Modo de Asignación:", ["Por Tarea (Búsqueda inteligente)"], horizontal=True)

    if mode == "Por Máquina (Lista)":
        with st.expander("Configurar Asignaciones Manuales", expanded=True):
            cols = st.columns(min(len(active_targets), 3))
            
            for i, maq in enumerate(active_targets):
                col = cols[i % 3]
                
                # Determine candidates
                candidates = []
                if not df.empty:
                    # Ensure OT_id exists
                    if "OT_id" not in df.columns:
                         if "CodigoProducto" in df.columns and "Subcodigo" in df.columns:
                            temp_ots = df["CodigoProducto"].astype(str) + "-" + df["Subcodigo"].astype(str)
                            candidates = sorted(temp_ots.unique().tolist())
                    else:
                        # Filter based on process
                        mask_relevant = pd.Series([True] * len(df), index=df.index)
                        
                        if "troquel" in maq.lower() or "manual" in maq.lower() or "iberica" in maq.lower():
                            if "_PEN_Troquelado" in df.columns:
                                mask_relevant = mask_relevant & df["_PEN_Troquelado"]
                            
                            if "MateriaPrimaPlanta" in df.columns:
                                 is_missing = df["MateriaPrimaPlanta"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
                                 mask_relevant = mask_relevant & (~is_missing)

                            if "TroquelArt" in df.columns and "FechaLlegadaTroquel" in df.columns:
                                 req_troq = df["TroquelArt"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
                                 has_date = pd.notna(df["FechaLlegadaTroquel"]) & (df["FechaLlegadaTroquel"].astype(str).str.strip() != "")
                                 mask_relevant = mask_relevant & ((~req_troq) | has_date)

                        elif "descartonad" in maq.lower():
                            if "_PEN_Descartonado" in df.columns:
                                mask_relevant = mask_relevant & df["_PEN_Descartonado"]
                            
                            if "MateriaPrimaPlanta" in df.columns:
                                 is_missing = df["MateriaPrimaPlanta"].astype(str).str.strip().str.lower().isin(["si", "true", "verdadero", "1", "x"])
                                 mask_relevant = mask_relevant & (~is_missing)
                                
                        candidates = sorted(df.loc[mask_relevant, "OT_id"].unique().tolist())

                # Retrieve previous selection
                prev_sel = st.session_state.manual_assignments.get(maq, [])
                
                with col:
                    sel = st.multiselect(
                        f"Órdenes para {maq}",
                        options=candidates,
                        default=[x for x in prev_sel if x in candidates],
                        key=f"manual_assign_{maq}"
                    )
                    
                    if sel:

                        st.session_state.manual_assignments[maq] = sel
                    else:
                        if maq in st.session_state.manual_assignments:
                             del st.session_state.manual_assignments[maq]

    else: # "Por Tarea (Búsqueda inteligente)"
        st.caption("Busca una tarea específica y asígnala a una máquina compatible (se validan medidas y restricciones).")
        
        # 1. Prepare global candidates list (All Troquelado/Descartonado tasks)
        # We need a dataframe with ID + Description for search
        if not df.empty:
            df_search = df.copy()
            if "OT_id" not in df_search.columns:
                 df_search["OT_id"] = df_search["CodigoProducto"].astype(str) + "-" + df_search["Subcodigo"].astype(str)
            
            # Filter only relevant tasks (Troquelado OR Descartonado pending)
            mask_troq = df_search["_PEN_Troquelado"] if "_PEN_Troquelado" in df_search.columns else pd.Series([False]*len(df_search))
            mask_desc = df_search["_PEN_Descartonado"] if "_PEN_Descartonado" in df_search.columns else pd.Series([False]*len(df_search))
            
            df_search = df_search[mask_troq | mask_desc].copy()
            
            if not df_search.empty:
                # Create Search Column: Safe access to columns
                # Descripcion might not exist, use 'Cliente-articulo' or try to get Descripcion safely
                desc_col = df_search["Descripcion"].astype(str) if "Descripcion" in df_search.columns else df_search.get("Cliente-articulo", pd.Series([""]*len(df_search))).astype(str)
                
                df_search["SearchLabel"] = df_search["OT_id"] + " | " + df_search["Cliente"].astype(str) + " | " + desc_col
                search_options = sorted(df_search["SearchLabel"].unique().tolist())
                
                selected_label = st.selectbox("🔍 Buscar Tarea (OT | Cliente | Descripción):", [""] + search_options, index=0)
                
                if selected_label:
                    ot_id = selected_label.split(" | ")[0]
                    # Get Task Details
                    task_row = df_search[df_search["OT_id"] == ot_id].iloc[0]
                    
                    st.markdown(f"#### Detalles para OT: **{ot_id}**")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.write(f"**Cliente:** {task_row['Cliente']}")
                    with c2: st.write(f"**Artículo:** {task_row.get('Descripcion', '-')}")
                    with c3: 
                        anc = task_row.get('PliAnc', 0)
                        lar = task_row.get('PliLar', 0)
                        st.write(f"**Medidas:** {anc} x {lar} cm")
                    with c4: st.write(f"**Cantidad:** {task_row.get('CantidadPliegos', 0)}")
                    
                    # 2. Check Compatibility with Active Targets
                    compatible_machines = []
                    rejected_machines = []
                    
                    # Need dimensions for validation
                    anc = float(task_row.get('PliAnc', 0) or 0)
                    lar = float(task_row.get('PliLar', 0) or 0)
                    
                    # Is it Troquelado or Descartonado?
                    is_troq = task_row.get("_PEN_Troquelado", False)
                    is_desc = task_row.get("_PEN_Descartonado", False)
                    
                    for maq in active_targets:
                        # Check Process Match
                        maq_lower = maq.lower()
                        match_proc = False
                        if is_troq and any(k in maq_lower for k in ["troq", "manual", "iberica", "duyan"]): match_proc = True
                        if is_desc and "descartonad" in maq_lower: match_proc = True
                        
                        if not match_proc: continue
                        
                        # VALIDATE CONSTRAINTS
                        reason = None
                        
                        # Dimension Check (Only for Troquelado machines)
                        if is_troq:
                            if not validar_medidas_troquel(maq, anc, lar):
                                from modules.schedulers.machines import obtener_descripcion_rango
                                rango_desc = obtener_descripcion_rango(maq)
                                reason = f"Medidas {anc}x{lar} fuera de rango. ({rango_desc})"
                        
                        # If passed logic checks, check hard constraints like MatPrima if needed?
                        # User said "parametros limitantes", usually refers to physical size.
                        # We also check MP status just in case to be helpful.
                        if "MateriaPrimaPlanta" in task_row:
                             is_missing = str(task_row["MateriaPrimaPlanta"]).strip().lower() in ["si", "true", "verdadero", "1", "x"]
                             if is_missing:
                                 reason = "Falta Materia Prima."
                        
                        if reason:
                            rejected_machines.append((maq, reason))
                        else:
                            compatible_machines.append(maq)
                            
                    # 3. Render Assignment UI
                                
                    if compatible_machines:
                        st.success(f"✅ {len(compatible_machines)} máquinas compatibles encontradas.")
                        
                        target_maq = st.selectbox("Seleccionar Máquina Destino:", compatible_machines)
                        
                        # Check if already assigned
                        current_assign = None
                        for m, ots in st.session_state.manual_assignments.items():
                            if ot_id in ots:
                                current_assign = m
                                break
                        
                        if current_assign:
                            st.warning(f"⚠️ Esta OT ya está asignada manualmente a: **{current_assign}**")
                            if st.button(f"Mover a {target_maq}"):
                                # Remove from old
                                st.session_state.manual_assignments[current_assign].remove(ot_id)
                                if not st.session_state.manual_assignments[current_assign]:
                                    del st.session_state.manual_assignments[current_assign]
                                
                                # Add to new
                                if target_maq not in st.session_state.manual_assignments:
                                    st.session_state.manual_assignments[target_maq] = []
                                st.session_state.manual_assignments[target_maq].append(ot_id)
                                st.rerun()
                        else:
                            if st.button(f"Asignar a {target_maq}"):
                                if target_maq not in st.session_state.manual_assignments:
                                    st.session_state.manual_assignments[target_maq] = []
                                st.session_state.manual_assignments[target_maq].append(ot_id)
                                st.success(f"Asignada correctamente a {target_maq}")
                                st.rerun()
                    else:
                        st.error("❌ No se encontraron máquinas compatibles para esta tarea.")

                    # SHOW REJECTED MACHINES ALWAYS
                    if rejected_machines:
                        with st.expander(f"Ver {len(rejected_machines)} máquinas no compatibles y razones", expanded=not compatible_machines):
                            for m, r in rejected_machines:
                                st.write(f"- **{m}**: {r}")
            else:
                st.info("No hay tareas pendientes de Troquelado/Descartonado.")
        else:
            st.warning("No hay datos cargados.")

    # Re-build assignments dict from session_state for return
    final_assignments = st.session_state.manual_assignments
    return final_assignments
