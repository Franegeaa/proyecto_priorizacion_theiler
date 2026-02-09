import streamlit as st

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
