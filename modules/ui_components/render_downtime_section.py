import streamlit as st
from datetime import date, time
import pandas as pd

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
