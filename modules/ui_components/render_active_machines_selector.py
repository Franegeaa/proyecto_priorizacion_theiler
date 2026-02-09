import streamlit as st
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
