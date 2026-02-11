import streamlit as st
from datetime import date, time
import pandas as pd

def render_daily_params_section(default_date=None, default_time=None):
    """Renders the Daily Parameters section (Date, Time, Holidays)."""
    st.subheader("⚙️ Parámetros de jornada") 
    
    with st.expander("Añadir Parámetros de Jornada", expanded=False):
        today = date.today()
        if default_date is None: default_date = today
        if default_time is None: default_time = pd.to_datetime("07:00").time()

        fecha_inicio_plan = st.date_input(
            "📅 Fecha de inicio de la planificación:",
            value=default_date,
            min_value=today,
        )

        hora_inicio_plan = st.time_input(
            "⏰ Hora de inicio de la planificación:",
            value=default_time
        )

        # Input de Feriados
        placeholder_feriados = "Pega una lista de fechas una debajo de la otra (ej. 21/11/2025)"
        feriados_texto = st.text_area(
            "Días feriados (opcional):",
            placeholder_feriados,
            height=100
        )
        
        feriados_lista = []
        if feriados_texto and feriados_texto.strip() != placeholder_feriados:
            texto_limpio = feriados_texto.replace(",", "\n")
            fechas_str = [f.strip() for f in texto_limpio.split("\n") if f.strip()]
            
            for f_str in fechas_str:
                try:
                    feriados_lista.append(pd.to_datetime(f_str, dayfirst=True, errors='raise').date())
                except Exception:
                    st.warning(f"No se pudo entender la fecha feriado: '{f_str}'. Ignorando.")
        
        if feriados_lista:
            st.info(f"Se registrarán {len(feriados_lista)} días feriados que no se planificarán.")
            
    return fecha_inicio_plan, hora_inicio_plan, feriados_lista
