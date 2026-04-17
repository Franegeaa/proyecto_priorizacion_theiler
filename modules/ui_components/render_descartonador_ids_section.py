import streamlit as st

def render_descartonador_ids_section(cfg):
    """Renders input fields to override Descartonador (or other) IDs."""
    st.subheader("🆔 Configurar IDs de Descartonadoras")
    
    # Default/Hardcoded values to start with (prevent empty starts)
    defaults = {
        "descartonadora 1": 40,
        "descartonadora 2": 194,
        "descartonadora 3": 247957750,
        "descartonadora 4": 0 # Unknown default
    }
    
    maquinas = sorted(cfg["maquinas"]["Maquina"].unique().tolist())
    descartonadoras = [m for m in maquinas if "descartonad" in m.lower()]
    
    custom_ids = {}
    
    if descartonadoras:
        with st.expander("Editar IDs de Descartonadoras", expanded=False):
            cols = st.columns(min(len(descartonadoras), 4))
            for i, maq in enumerate(descartonadoras):
                col = cols[i % 4]
                default_val = defaults.get(maq.lower(), 0)
                
                with col:
                    val = st.number_input(
                        f"ID {maq}", 
                        value=default_val, 
                        step=1, 
                        key=f"id_cfg_{maq}"
                    )
                    custom_ids[maq] = int(val)
    else:
        st.info("No hay Descartonadoras en la configuración activa.")
        
    return custom_ids
