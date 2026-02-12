import streamlit as st

def render_machine_speed_inputs(cfg):
    """Renders the section to adjust machine speeds and setup times."""
    st.subheader("Configurar velocidades de máquina")
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
