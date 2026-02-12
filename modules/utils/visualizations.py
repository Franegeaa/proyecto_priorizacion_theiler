import streamlit as st
import pandas as pd
from datetime import date
from .config_loader import es_dia_habil
from .app_utils import color_map_procesos, ordenar_maquinas_personalizado

# Import Plotly conditionally
try:
    import plotly.express as px
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False

def render_gantt_chart(schedule, cfg):
    st.subheader("📊 Seguimiento (Gantt)")
    
    if not _HAS_PLOTLY:
        st.info("Para ver el Gantt instalá Plotly: `pip install plotly`")
        return

    if schedule.empty:
         st.info("No hay tareas planificadas para mostrar el seguimiento.")
         return

    schedule_gantt = schedule.copy() # Copiamos el original

    # Asegurarnos que las fechas no sean nulas
    min_plan_date = schedule_gantt["Inicio"].min().date() if not schedule_gantt["Inicio"].isnull().all() else date.today()
    max_plan_date = schedule_gantt["Fin"].max().date() if not schedule_gantt["Fin"].isnull().all() else date.today()

    st.markdown("##### 📅 Filtros de Fecha para el Gantt") 

    tipo_filtro = st.radio(
        "Seleccionar Rango de Fechas:",
        ["Día", "Ver todo", "Semana",  "Mes"], 
        index=0,
        horizontal=True,
        key="filtro_fecha_radio"
        )
    
    range_start_dt = None 
    range_end_dt = None   

    if tipo_filtro == "Día":
        fecha_dia = st.date_input("Seleccioná el día:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_dia")
        range_start_dt = pd.to_datetime(fecha_dia) + pd.Timedelta(hours=7) 
        range_end_dt = range_start_dt + pd.Timedelta(hours=9) 

    elif tipo_filtro == "Semana":
        fecha_semana = st.date_input("Seleccioná un día de la semana:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_semana")
        start_of_week = fecha_semana - pd.Timedelta(days=fecha_semana.weekday())
        range_start_dt = pd.to_datetime(start_of_week) + pd.Timedelta(hours=7) 
        range_end_dt = range_start_dt + pd.Timedelta(days=7) + pd.Timedelta(hours=9) 

    elif tipo_filtro == "Mes":
        fecha_mes = st.date_input("Seleccioná un día del mes:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_mes")
        range_start_dt = pd.to_datetime(fecha_mes.replace(day=1)) + pd.Timedelta(hours=7)
        next_month = (fecha_mes.replace(day=28) + pd.Timedelta(days=4))
        range_end_dt = pd.to_datetime(next_month.replace(day=1)) + pd.Timedelta(hours=9)

    elif tipo_filtro == "Ver todo":
        range_start_dt = pd.to_datetime(min_plan_date) + pd.Timedelta(hours=7)
        range_end_dt = pd.to_datetime(min_plan_date) + pd.Timedelta(days=10) + pd.Timedelta(hours=9)

    elif tipo_filtro == "Rango personalizado":
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fecha_inicio_filtro = st.date_input( 
                "Desde:",
                value=min_plan_date,
                min_value=min_plan_date,
                max_value=max_plan_date,
                )

        with col_f2:
            fecha_fin_filtro = st.date_input(
                "Hasta:",
                value=max_plan_date,
                min_value=min_plan_date,
                max_value=max_plan_date,
                )
        range_start_dt = pd.to_datetime(fecha_inicio_filtro)
        range_end_dt = pd.to_datetime(fecha_fin_filtro) + pd.Timedelta(days=1)
    
    if range_start_dt is not None and range_end_dt is not None:
        schedule_gantt = schedule_gantt[
            (schedule_gantt["Fin"] > range_start_dt) &
            (schedule_gantt["Inicio"] < range_end_dt)
        ]

    def configurar_eje_x(fig_obj):
        """Ajusta el eje X segun el filtro activo."""
        if fig_obj is None:
            return

        if range_start_dt is not None and range_end_dt is not None:
            fig_obj.update_xaxes(range=[range_start_dt, range_end_dt])

        if tipo_filtro == "Día":
            fig_obj.update_xaxes(
                dtick=3600000, 
                tickformat="%H:%M",
                tickangle=0,
                showgrid=True,
                gridcolor="rgba(128, 128, 128, 0.3)",
                gridwidth=1.2,
                layer="below traces",
                tickfont=dict(size=11, color="#666666"),
            )
        else:
            fig_obj.update_xaxes(
                dtick=86400000, 
                tickformat="%d %b", 
                tickangle=0,
                showgrid=True,
                gridcolor="rgba(128, 128, 128, 0.3)",
                gridwidth=1.5,
                layer="below traces",
                tickfont=dict(size=11, color="#666666"),
            )

            if range_start_dt is not None and range_end_dt is not None:
                dias_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
                fechas = pd.date_range(start=range_start_dt.date(), end=range_end_dt.date(), freq="D")
                ticktext = [f"{f.strftime('%d %b')}<br>{dias_es[f.weekday()]}" for f in fechas]
                tickvals = [pd.Timestamp(f) for f in fechas]
                
                # Check holidays and weekends
                for i, f in enumerate(fechas):
                    tickvals.append(f)
                    dia_habil = es_dia_habil(f, cfg) 
                    
                    # Highlight non-working days
                    if not dia_habil:
                         fig_obj.add_vrect(
                            x0=f,
                            x1=f + pd.Timedelta(days=1),
                            fillcolor="rgba(255, 0, 0, 0.15)",
                            layer="below", 
                            line_width=0,
                        )
                         ticktext[i] = f"<b><span style='color:red'>{f.strftime('%d %b')}<br>{dias_es[f.weekday()]}</span></b>"
                
                fig_obj.update_xaxes(ticktext=ticktext, tickvals=tickvals)

    vista = st.radio(
        "Seleccioná el tipo de seguimiento:",
        ["Por Máquina", "Por Orden de Trabajo (OT)"],
        horizontal=True
    )

    fig = None
    if schedule_gantt.empty:
        st.info("No hay tareas planificadas en el rango de fechas seleccionado.")
    else:  
        try:
            if vista == "Por Orden de Trabajo (OT)":
                opciones_ot = ["(Todas)"] + sorted(schedule_gantt["OT_id"].unique().tolist())
                ot_seleccionada = st.selectbox(
                    "Seguimiento por OT:",
                    opciones_ot,
                    key="gantt_ot_select"
                )
                data_gantt = schedule_gantt if ot_seleccionada == "(Todas)" else schedule_gantt[schedule_gantt["OT_id"] == ot_seleccionada]

                if data_gantt.empty:
                    st.info("La OT seleccionada no tiene tareas planificadas (o fue filtrada por fecha).")
                else:
                    categorias_ot = sorted(data_gantt["OT_id"].dropna().unique().tolist())
                    fig = px.timeline(
                        data_gantt,
                        x_start="Inicio", x_end="Fin",
                        y="OT_id", color="Proceso",
                        color_discrete_map=color_map_procesos,
                        category_orders={"OT_id": categorias_ot},
                        hover_data=["Maquina", "Cliente", "DueDate"],
                        title="Procesos por Orden de Trabajo",
                    )
                    if tipo_filtro == "Día":
                        fig.update_layout(
                            yaxis=dict(
                                categoryorder="array",
                                categoryarray=categorias_ot
                            ),
                            bargap=0.80,
                            bargroupgap=1,
                        )
                        fig.update_traces(selector=dict(type="bar"), width=0.5)
                    if tipo_filtro != "Ver todo" and opciones_ot != "(Todas)" and tipo_filtro != "Semana" and tipo_filtro != "Mes":
                        fig.update_layout(
                            height=max(300, 30 * len(categorias_ot)),
                        )
                    fig.update_yaxes(autorange="reversed")
                    configurar_eje_x(fig)

            elif vista == "Por Máquina":
                maquinas_unicas = schedule_gantt["Maquina"].dropna().unique().tolist()
                maquinas_ordenadas = ordenar_maquinas_personalizado(maquinas_unicas)
                fig = px.timeline(
                    schedule_gantt,
                    x_start="Inicio", x_end="Fin",
                    y="Maquina", color="Proceso",
                    color_discrete_map=color_map_procesos,
                    category_orders={"Maquina": maquinas_ordenadas},
                    hover_data=["OT_id", "Cliente", "DueDate"],
                    title="Procesos por Máquina", 
                )
                categorias_maquinas = maquinas_ordenadas
                fig.update_layout(
                    bargap=0.35,
                    bargroupgap=0.0,
                    height=max(420, 50 * len(categorias_maquinas))
                )
                fig.update_traces(selector=dict(type="bar"), width=0.5)
                fig.update_yaxes(autorange="reversed")
                configurar_eje_x(fig)

        except Exception as e:
            st.warning(f"No se pudo renderizar el gráfico: {e}")

    if fig is not None:
        df_downtimes = pd.DataFrame(cfg.get("downtimes", []))

        if not df_downtimes.empty and vista == "Por Máquina":
            df_downtimes["start"] = pd.to_datetime(df_downtimes["start"], errors="coerce")
            df_downtimes["end"] = pd.to_datetime(df_downtimes["end"], errors="coerce")
            df_downtimes["Proceso"] = "🔧 Paro programado"

            fig_paros = px.timeline(
                df_downtimes,
                x_start="start", x_end="end",
                y="maquina",
                color="Proceso",
                color_discrete_map={"🔧 Paro programado": "red"},
                opacity=0.8,
                hover_data={"start": True, "end": True},
            )

            fig_paros.update_traces(marker=dict(line_width=0), width=0.2)
            for trace in fig_paros.data:
                fig.add_trace(trace)

            fig.add_annotation(
                text="🔧 Paros programados",
                xref="paper", yref="paper",
                x=1.03, y=1,
                showarrow=False,
                font=dict(color="red", size=12)
            )
        st.plotly_chart(fig)
