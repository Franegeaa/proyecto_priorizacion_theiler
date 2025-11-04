import streamlit as st
import pandas as pd
from datetime import date, timedelta
from io import BytesIO
from collections import Counter

from modules.config_loader import cargar_config, horas_por_dia
from modules.scheduler import programar

# Opcional: Plotly para Gantt
try:
    import plotly.express as px
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

color_map_procesos = {
    "Guillotina": "dimgray",        # Gris oscuro
    "Impresión Offset": "mediumseagreen", # Verde mar
    "Impresión Flexo": "darkorange",    # Naranja oscuro
    "Barnizado": "gold",            # Dorado (o "Barniz" si se llama así)
    "Barniz": "gold",               # Añade variantes si es necesario
    "OPP": "slateblue",             # Azul pizarra
    "Stamping": "firebrick",        # Rojo ladrillo
    "Cuño": "darkcyan",             # Cian oscuro (Añade si es un proceso)
    "Encapado": "sandybrown",       # Marrón arena (Añade si es un proceso)
    "Troquelado": "lightcoral",     # Coral claro
    "Descartonado": "dodgerblue",   # Azul brillante
    "Ventana": "skyblue",           # Azul cielo
    "Pegado": "mediumpurple",         # Púrpura medio
}

def ordenar_maquinas_personalizado(lista_maquinas):
    """Ordena máquinas según prioridad operativa definida por el usuario."""
    prioridades = [
        (1, ["guillotina"]),
        (2, ["offset"]),
        (3, ["flexo"]),
        (4, ["automat", "automát"]),
        (5, ["manual 1", "manual-1", "manual1"]),
        (6, ["manual 2", "manual-2", "manual2"]),
        (7, ["descartonadora 1"]),
        (8, ["descartonadora 2"]),
        (9, ["ventana"]),
        (10, ["pegadora", "pegado"]),
    ]

    def clave(nombre):
        nombre_str = str(nombre).lower()
        for prioridad, patrones in prioridades:
            if any(pat in nombre_str for pat in patrones):
                return (prioridad, nombre_str)
        return (len(prioridades) + 1, nombre_str)

    return sorted(lista_maquinas, key=clave, reverse=True)

if archivo is not None:
    df = pd.read_excel(archivo)
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    st.subheader("⚙️ Parámetros de jornada")

    # ... (toda tu lógica de renombrado y limpieza de 'df' va aquí) ...
    # ... (Renombres base) ...
    df.rename(columns={
        "ORDEN": "CodigoProducto",
        "Ped.": "Subcodigo",
        "CLIENTE": "Cliente",
        "Razon Social": "RazonSocial",
        "CANT/DDP": "CantidadPliegos",
        "FECH/ENT.": "FechaEntrega",
        "Mat/Prim1": "MateriaPrima",
        "MPPlanta": "MateriaPrimaPlanta",
        "CodTroTapa": "CodigoTroquelTapa",
        "CodTroCuerpo": "CodigoTroquelCuerpo",
        "Pli Anc": "PliAnc",
        "Pli Lar": "PliLar",
    }, inplace=True)

    # ... (Colores combinados) ...
    color_cols = [c for c in df.columns if str(c).startswith("Color")]
    df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1) if color_cols else ""

    # ... (Flags SOLO pendientes) ...
    def to_bool_series(names):
        for c in names:
            if c in df.columns:
                return df[c].astype(str).str.strip().str.lower().isin(["verdadero", "true", "si", "sí", "1", "x"])
        return pd.Series(False, index=df.index)

    df["_PEN_Guillotina"]   = to_bool_series(["GuillotinadoSNDpd"])
    df["_PEN_Barnizado"]    = to_bool_series(["Barnizado.1"])
    df["_PEN_Encapado"]     = to_bool_series(["Encapado", "EncapadoSND"])
    df["_PEN_OPP"]          = to_bool_series(["OPPSNDpd", "OPPSND"])
    df["_PEN_Troquelado"]   = to_bool_series(["TroqueladoSNDpd", "TroqueladoSND"])
    df["_PEN_Descartonado"] = to_bool_series(["DescartonadoSNDpd", "DescartonadoSND"])
    df["_PEN_Ventana"]      = to_bool_series(["PegadoVSNDpd", "PegadoVSND"])
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])
    df["_IMP_Dorso"]      = to_bool_series(["Dorso"])        # Flexo → doble pasada
    df["_IMP_FreyDorDpd"] = to_bool_series(["FreyDorDpd"])    # Offset → doble pasada

    # ... (Troquel preferido) ...
    for c in ["CodigoTroquel", "CodigoTroquelTapa", "CodigoTroquelCuerpo", "CodTroTapa", "CodTroCuerpo"]:
        if c in df.columns:
            df["CodigoTroquel"] = df[c]
            break

    # ... (Impresión: separar Offset/Flexo) ...
    mat = df.get("MateriaPrima", "").astype(str).str.lower()
    imp_pend = to_bool_series(["ImpresionSNDpd", "ImpresionSND"])
    df["_PEN_ImpresionFlexo"]  = imp_pend & (mat.str.contains("micro", na=False) | mat.str.contains("carton", na=False))
    df["_PEN_ImpresionOffset"] = imp_pend & (mat.str.contains("cartulina", na=False) | mat.str.contains("papel", na=False))

    # ... (OT_id) ...
    if "OT_id" not in df.columns:
        df["OT_id"] = (
            df["CodigoProducto"].astype(str).str.strip() + "-" +
            df["Subcodigo"].astype(str).str.strip()
        )

    st.info("🧠 Generando programa…")
    schedule, carga_md, resumen_ot, detalle_maquina = programar(df, cfg, start=date.today())

    # ==========================
    # Métricas principales
    # ==========================
    # ... (tus métricas no cambian) ...
    col1, col2, col3, col4 = st.columns(4)
    total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
    atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes atrasadas", atrasadas)
    col3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
    col4.metric("Jornada (h/día)", f"{horas_por_dia(cfg):.1f}")

    # ==========================
    # Seguimiento visual (Gantt)
    # ==========================
    st.subheader("📊 Seguimiento (Gantt)")
    if not schedule.empty and _HAS_PLOTLY:
        schedule_gantt = schedule.copy() # Copiamos el original

        # Asegurarnos que las fechas no sean nulas
        min_plan_date = schedule_gantt["Inicio"].min().date() if not schedule_gantt["Inicio"].isnull().all() else date.today()
        max_plan_date = schedule_gantt["Fin"].max().date() if not schedule_gantt["Fin"].isnull().all() else date.today()

        st.markdown("##### 📅 Filtros de Fecha para el Gantt") # Título corregido

        tipo_filtro = st.radio(
            "Seleccionar Rango de Fechas:",
            ["Ver todo", "Día", "Semana",  "Mes"], # "Rango personalizado"],
            index=0,
            horizontal=True,
            key="filtro_fecha_radio"
            )
        
        range_start_dt = None # CORREGIDO: renombrado
        range_end_dt = None   # CORREGIDO: renombrado

        if tipo_filtro == "Día":
            fecha_dia = st.date_input("Seleccioná el día:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_dia")
            range_start_dt = pd.to_datetime(fecha_dia) + pd.Timedelta(hours=7) # CORREGIDO: Asignar a variable correcta
            range_end_dt = range_start_dt + pd.Timedelta(hours=9) # CORREGIDO: Asignar a variable correcta

        elif tipo_filtro == "Semana":
            fecha_semana = st.date_input("Seleccioná un día de la semana:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_semana")
            start_of_week = fecha_semana - pd.Timedelta(days=fecha_semana.weekday())
            range_start_dt = pd.to_datetime(start_of_week) + pd.Timedelta(hours=7) # CORREGIDO: Asignar a variable correcta y convertir a datetime
            range_end_dt = range_start_dt + pd.Timedelta(days=7) + pd.Timedelta(hours=9) # CORREGIDO: Asignar a variable correcta

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
                # CORREGIDO: Usar st.date_input (tu código tenía st.date.input)
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
        
        # --- BLOQUE DE FILTRADO CORREGIDO ---
        # 1. Movido FUERA del 'elif'
        # 2. Lógica de solapamiento ARREGLADA
        if range_start_dt is not None and range_end_dt is not None:
            
            # Lógica de solapamiento correcta:
            # La tarea termina DESPUÉS de que el rango empieza Y
            # la tarea empieza ANTES de que el rango termine.
            schedule_gantt = schedule_gantt[
                (schedule_gantt["Fin"] > range_start_dt) &
                (schedule_gantt["Inicio"] < range_end_dt)
            ]
        # --- FIN DE LA CORRECCIÓN ---

        def configurar_eje_x(fig_obj):
            """Ajusta el eje X segun el filtro activo."""
            if fig_obj is None:
                return

            if range_start_dt is not None and range_end_dt is not None:
                fig_obj.update_xaxes(range=[range_start_dt, range_end_dt])

            if tipo_filtro == "Día":
                fig_obj.update_xaxes(
                    dtick=3600000,  # 1 hora en milisegundos
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
                    dtick=86400000,  # 1 día en milisegundos
                    tickformat="%d %b",  # Día y mes
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
                    fig_obj.update_xaxes(ticktext=ticktext, tickvals=tickvals)


        vista = st.radio(
            "Seleccioná el tipo de seguimiento:",
            ["Por Orden de Trabajo (OT)", "Por Máquina"],
            horizontal=True
        )

        fig = None
        todas_las_ot = sorted(schedule["OT_id"].dropna().unique().tolist())
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
                        # CORREGIDO: Mensaje más claro
                        st.info("La OT seleccionada no tiene tareas planificadas (o fue filtrada por fecha).")
                    else:
                        categorias_ot = sorted(data_gantt["OT_id"].dropna().unique().tolist())
                        fig = px.timeline(
                            data_gantt,
                            x_start="Inicio", x_end="Fin",
                            y="OT_id", color="Proceso",
                            color_discrete_map=color_map_procesos,
                            category_orders={"OT_id": categorias_ot},
                            hover_data=["Maquina", "Cliente", "Atraso_h", "DueDate"],
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
                        hover_data=["OT_id", "Cliente", "Atraso_h", "DueDate"],
                        title="Procesos por Máquina", # Título corregido
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
            st.plotly_chart(fig, use_container_width=True)
            
    elif not _HAS_PLOTLY:
        st.info("Para ver el Gantt instalá Plotly: `pip install plotly`")
    else:
        st.info("No hay tareas planificadas para mostrar el seguimiento.")

    # ==========================
    # 📋 Detalle (OT / Máquina)
    # ==========================

    st.subheader("🔎 Detalle interactivo")
    modo = st.radio("Ver detalle por:", ["Orden de Trabajo (OT)", "Máquina"], horizontal=True)

    # --- CORRECCIÓN: Usar 'schedule' (el DF completo) para las tablas de detalle ---
    if modo == "Orden de Trabajo (OT)":
        if not schedule.empty: # Usar 'schedule'
            opciones = ["(Todas)"] + sorted(schedule["OT_id"].unique().tolist()) # Usar 'schedule'
            elegido = st.selectbox("Elegí OT:", opciones)
            df_show = schedule if elegido == "(Todas)" else schedule[schedule["OT_id"] == elegido] # Usar 'schedule'
            df_show = df_show.drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_show, use_container_width=True)
        else:
            st.info("No hay tareas planificadas (verificá pendientes o MPPlanta).")

    else:
        if not schedule.empty and detalle_maquina is not None and not detalle_maquina.empty: # Usar 'schedule'
            maquinas_disponibles = ordenar_maquinas_personalizado(detalle_maquina["Maquina"].unique().tolist())
            maquina_sel = st.selectbox("Seleccioná una máquina:", maquinas_disponibles)

            # Reunir detalle completo para esa máquina
            df_maquina = schedule[schedule["Maquina"] == maquina_sel].copy() # Usar 'schedule'

            # ... (Lógica para agregar CodigoTroquel y Colores) ...
            if "CodigoTroquel" not in df_maquina.columns and "CodigoTroquel" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "CodigoTroquel"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )

            if "Colores" not in df_maquina.columns and "Colores" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "Colores"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )
            
            df_maquina.sort_values(by="Inicio", inplace=True)

            # ... (Lógica de columnas dinámicas) ...
            if any(k in maquina_sel.lower() for k in ["troquel", "manual", "autom"]):
                st.write("🧱 Mostrando código de troquel (agrupamiento interno).")
                cols = ["OT_id", "CodigoTroquel", "Proceso", "Inicio", "Fin", "DueDate"]
            elif any(k in maquina_sel.lower() for k in ["offset", "flexo", "impres"]):
                st.write("🎨 Mostrando colores del trabajo de impresión.")
                cols = ["OT_id", "Cliente", "Colores", "Proceso", "Inicio", "Fin", "DueDate"]
            else:
                cols = ["OT_id", "Cliente", "Proceso", "Inicio", "Fin", "DueDate"]

            cols_exist = [c for c in cols if c in df_maquina.columns]
            df_maquina_display = df_maquina[cols_exist].drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_maquina_display, use_container_width=True)
        else:
            st.info("No hay detalle por máquina disponible (verificá que se hayan generado tareas).")
    # --- FIN DE LA CORRECCIÓN ---

    # ==========================
    # Carga por máquina / día
    # ==========================

    st.subheader("⚙️ Carga por máquina y día")
    if not carga_md.empty:
        st.dataframe(carga_md.sort_values(["Fecha","Maquina"]), use_container_width=True)
    else:
        st.info("No hay carga registrada (puede que no haya tareas planificadas).")

    # ==========================
    # Resumen por OT
    # ==========================
    st.subheader("📦 Resumen por OT (Fin vs Entrega)")
    if not resumen_ot.empty:
        resumen_display = resumen_ot.sort_values(["EnRiesgo","Atraso_h","Fin_OT"], ascending=[False, False, True]).copy()
        st.dataframe(resumen_display, use_container_width=True)
    else:
        st.info("Sin resumen disponible.")

    # ==========================
    # Exportación a Excel
    # ==========================

    st.subheader("💾 Exportar")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        schedule.to_excel(w, index=False, sheet_name="Schedule") # Exporta el schedule completo
        if not resumen_ot.empty:
            resumen_ot.to_excel(w, index=False, sheet_name="Resumen_OT")
        if not carga_md.empty:
            carga_md.to_excel(w, index=False, sheet_name="Carga_Maquina_Dia")
        if 'detalle_maquina' in locals() and not detalle_maquina.empty:
            detalle_maquina.to_excel(w, index=False, sheet_name="Detalle_Maquina")
    buf.seek(0)
    st.download_button(
        "⬇️ Descargar Excel de planificación",
        data=buf,
        file_name="Plan_Produccion_Theiler.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")

