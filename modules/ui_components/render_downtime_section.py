import streamlit as st
from datetime import datetime, date, time
import pandas as pd

def render_downtime_section(maquinas_activas, fecha_inicio_plan, persistence=None):
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
                
                # Save to DB
                if persistence and persistence.connected:
                    persistence.save_downtimes(st.session_state.downtimes)
                    
                st.success(f"Paro añadido para {d_maquina} de {dt_inicio} a {dt_fin}")

    # Ensure dictionary format AND Manage Deletions
    if st.session_state.downtimes:
        st.write("### Paros programados:")
        
        to_remove = []
        for i, dt in enumerate(st.session_state.downtimes):
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.info(f"🛑 **{dt['maquina']}**: {dt['start']} -> {dt['end']}")
            with col_del:
                if st.button("🗑️", key=f"del_dt_{i}", help="Eliminar paro"):
                    to_remove.append(i)
        
        if to_remove:
            # Remove in reverse order to maintain indices
            for idx in sorted(to_remove, reverse=True):
                del st.session_state.downtimes[idx]
            
            # Save updates
            if persistence and persistence.connected:
                persistence.save_downtimes(st.session_state.downtimes)
            
            st.rerun()

    # Pass final list to scheduler
    final_list = pd.DataFrame(st.session_state.downtimes).drop_duplicates().to_dict(orient="records") if st.session_state.downtimes else []
    
    return final_list
