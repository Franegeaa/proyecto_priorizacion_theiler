import streamlit as st
from modules.utils.config_loader import save_die_preferences

def render_die_preferences(cfg):
    """
    Renders an expandable section to configure preferred Die Codes per Machine.
    Updates the cfg["troquel_preferences"] and saves to JSON.
    """
    st.subheader("⚙️ Preferencias de Troqueles")
    st.caption("Asigna códigos de troqueles específicos a máquinas. Si una OT tiene un troquel listado aquí, se forzará su asignación a esta máquina si es factible.")
    
    # Filter only relevant machines for Die Cutting (Troqueladoras)
    # Includes Manuals, Iberica, Automatica/Duyan
    # We identify them by process name usually, or hardcoded knowledge of the plant
    
    maquinas = sorted(cfg["maquinas"]["Maquina"].unique().tolist())
    die_machines = [
        m for m in maquinas 
        if "manual" in m.lower() or "troq" in m.lower() or "iberica" in m.lower() or "autom" in m.lower() or "duyan" in m.lower()
    ]
    
    if not die_machines:
        st.info("No se encontraron máquinas de troquelado para configurar.")
        return

    # Load current prefs
    current_prefs = cfg.get("troquel_preferences", {})
    
    with st.expander("Configurar Preferencias de Troqueles por Máquina", expanded=False):
        
        # We use a form to avoid saving on every keystroke
        with st.form("die_prefs_form"):
            new_prefs = {}
            
            cols = st.columns(min(len(die_machines), 3))
            
            for i, maq in enumerate(die_machines):
                col = cols[i % 3]
                
                with col:
                    # Get existing codes list
                    codes_list = current_prefs.get(maq, [])
                    # Join for text area
                    text_val = "\n".join(codes_list)
                    
                    st.markdown(f"**{maq}**")
                    new_text = st.text_area(
                        f"Códigos para {maq}",
                        value=text_val,
                        height=100,
                        placeholder="T-123\nT-456",
                        key=f"die_pref_{maq}",
                        help="Ingresa un código por línea."
                    )
                    
                    # Parse back to list
                    # Split by newline, strip, remove empty
                    cleaned_codes = [c.strip() for c in new_text.split("\n") if c.strip()]
                    if cleaned_codes:
                        new_prefs[maq] = cleaned_codes
            
            submitted = st.form_submit_button("💾 Guardar Preferencias")
            
            if submitted:
                # Update Config Object
                cfg["troquel_preferences"] = new_prefs
                # Save to disk
                if save_die_preferences(new_prefs):
                    # --- DB PERSISTENCE ---
                    if "persistence" in st.session_state and st.session_state.persistence.connected:
                        if st.session_state.persistence.save_die_preferences(new_prefs):
                             st.toast("Y también en la base de datos!", icon="☁️")
                    # ----------------------
                    st.success("✅ Preferencias guardadas correctamente.")
                else:
                    st.error("❌ Error al guardar preferencias.")
