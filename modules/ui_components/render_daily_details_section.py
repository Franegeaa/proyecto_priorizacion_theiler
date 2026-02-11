import streamlit as st
import pandas as pd
from datetime import date
from modules.utils.exporters import dataframe_to_excel_bytes

def render_daily_details_section(schedule):
    if not schedule.empty:
        st.subheader("📆 **Visualización por Día**")
        d_seleccionado = st.date_input("Seleccioná la fecha a visualizar:", value=date.today())
        
        sel_start = pd.to_datetime(d_seleccionado)
        sel_end = sel_start + pd.Timedelta(days=1)
        
        mask = (schedule["Inicio"] < sel_end) & (schedule["Fin"] > sel_start)
        df_dia = schedule[mask].copy()
        
        if not df_dia.empty:
            df_dia.sort_values(by=["Maquina", "Inicio"], inplace=True)

            # --- FILTERS ---
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                unique_procs = sorted(df_dia["Proceso"].astype(str).unique().tolist())
                filtro_proc = st.multiselect("Filtrar por Proceso:", options=unique_procs, placeholder="(Todos)", key="daily_proc_filter")
                
            with col_f2:
                unique_maqs = sorted(df_dia["Maquina"].astype(str).unique().tolist())
                filtro_maq = st.multiselect("Filtrar por Máquina:", options=unique_maqs, placeholder="(Todas)", key="daily_maq_filter")

            if filtro_proc:
                df_dia = df_dia[df_dia["Proceso"].astype(str).isin(filtro_proc)]
                
            if filtro_maq:
                df_dia = df_dia[df_dia["Maquina"].astype(str).isin(filtro_maq)]
            # ----------------
            cols_day = ["Maquina", "OT_id", "Cliente", "Cliente-articulo", "Proceso", "Inicio", "Fin", "Duracion_h", "CantidadPliegos", "DueDate"]
            cols_final = [c for c in cols_day if c in df_dia.columns]
            
            df_show_day = df_dia[cols_final]
            
            for col in df_show_day.select_dtypes(include=['object']).columns:
                df_show_day[col] = df_show_day[col].fillna("").astype(str)

            st.dataframe(df_show_day, use_container_width=True)
            
            buf = dataframe_to_excel_bytes(df_show_day, sheet_name=f"Dia {d_seleccionado}")
            st.download_button(
                label=f"⬇️ Descargar Plan del {d_seleccionado}",
                data=buf,
                file_name=f"Plan_Dia_{d_seleccionado}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_day_view"
            )
        else:
            st.warning(f"No hay tareas planificadas para el {d_seleccionado}.")