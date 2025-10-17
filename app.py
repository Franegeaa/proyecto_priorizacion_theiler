import streamlit as st
import pandas as pd
from datetime import date
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

if archivo is not None:
    df = pd.read_excel(archivo)
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    st.subheader("⚙️ Parámetros de jornada")
    st.write(f"Jornada laboral: {horas_por_dia(cfg)} h/día")

    # ---------------------------------------------------
    # Normalización de columnas (mantener segunda si hay duplicadas)
    # ---------------------------------------------------
    col_counts = Counter(df.columns)
    cols_final, seen = [], Counter()
    for c in df.columns:
        seen[c] += 1
        if col_counts[c] > 1 and seen[c] == 1:
            continue
        cols_final.append(c)
    df = df[cols_final]

    # Renombres base
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

    # Colores combinados
    color_cols = [c for c in df.columns if str(c).startswith("Color")]
    df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1) if color_cols else ""

    # Flags SOLO pendientes (_SNDpd u otros)
    def to_bool_series(names):
        for c in names:
            if c in df.columns:
                return df[c].astype(str).str.strip().str.lower().isin(["verdadero", "true", "si", "sí", "1", "x"])
        return pd.Series(False, index=df.index)

    df["_PEN_Guillotina"]   = to_bool_series(["GuillotinadoSNDpd"])
    df["_PEN_Barnizado"]    = to_bool_series(["Barnizado.1"])  # la segunda "Barnizado" (pendiente)
    df["_PEN_Encapado"]     = to_bool_series(["EncapadoSNDpd", "EncapadoSND"])
    df["_PEN_OPP"]          = to_bool_series(["OPPSNDpd", "OPPSND"])
    df["_PEN_Troquelado"]   = to_bool_series(["TroqueladoSNDpd", "TroqueladoSND"])
    df["_PEN_Descartonado"] = to_bool_series(["DescartonadoSNDpd", "DescartonadoSND"])
    df["_PEN_Ventana"]      = to_bool_series(["PegadoVSNDpd", "PegadoVSND"])
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])

    # Troquel preferido
    for c in ["CodigoTroquel", "CodigoTroquelTapa", "CodigoTroquelCuerpo", "CodTroTapa", "CodTroCuerpo"]:
        if c in df.columns:
            df["CodigoTroquel"] = df[c]
            break

    # Impresión: separar Offset/Flexo por MateriaPrima
    mat = df.get("MateriaPrima", "").astype(str).str.lower()
    imp_pend = to_bool_series(["ImpresionSNDpd", "ImpresionSND"])
    df["_PEN_ImpresionFlexo"]  = imp_pend & mat.str.contains("micro", na=False)
    df["_PEN_ImpresionOffset"] = imp_pend & mat.str.contains("cartulina", na=False)

    # OT_id para identificar la orden (si aún no existe)
    if "OT_id" not in df.columns:
        df["OT_id"] = (
            df["CodigoProducto"].astype(str).str.strip() + "-" +
            df["Subcodigo"].astype(str).str.strip()
        )

    # Listar OTs con impresión pendiente
    ot_flexo = df.loc[df["_PEN_ImpresionFlexo"], "OT_id"].tolist()
    ot_offset = df.loc[df["_PEN_ImpresionOffset"], "OT_id"].tolist()

    # Consola (servidor)
    print(f"Impresión Flexo pendiente ({len(ot_flexo)}): {ot_flexo}")
    print(f"Impresión Offset pendiente ({len(ot_offset)}): {ot_offset}")
    
    # Verificación mínima
    if "CantidadPliegos" not in df.columns:
        st.error("⚠️ Falta 'CANT/DDP' / 'CantidadPliegos' en el Excel.")
        st.stop()
    if "FechaEntrega" not in df.columns:
        st.error("⚠️ Falta columna de fecha ('FECH/ENT.' / 'FechaEntrega').")
        st.stop()

    st.info("🧠 Generando programa…")
    schedule, carga_md, resumen_ot = programar(df, cfg, start=date.today())

    # ==========================
    # Métricas principales
    # ==========================
    col1, col2, col3, col4 = st.columns(4)
    total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
    atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes atrasadas", atrasadas)
    col3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
    col4.metric("Jornada (h/día)", f"{horas_por_dia(cfg):.1f}")

    # ==========================
    # Seguimiento por OT (Gantt)
    # ==========================
    st.subheader("📊 Seguimiento por Orden (Timeline)")
    if not schedule.empty and _HAS_PLOTLY:
        fig = None
        try:
            fig = px.timeline(
                schedule,
                x_start="Inicio", x_end="Fin",
                y="OT_id", color="Proceso",
                hover_data=["Maquina", "Cliente", "Atraso_h", "DueDate"],
                title="Procesos por OT",
            )
            fig.update_yaxes(autorange="reversed")
        except Exception:
            fig = None

        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No se pudo renderizar el gráfico. Verificá que las columnas de fechas estén correctas.")
    elif not _HAS_PLOTLY:
        st.info("Para ver el Gantt instalá Plotly: `pip install plotly`")

    # ==========================
    # Filtro por OT
    # ==========================
    st.subheader("🔎 Detalle por OT")
    if not schedule.empty:
        opciones = ["(Todas)"] + sorted(schedule["OT_id"].unique().tolist())
        elegido = st.selectbox("Elegí OT:", opciones)
        df_show = schedule if elegido == "(Todas)" else schedule[schedule["OT_id"] == elegido]
        st.dataframe(df_show, use_container_width=True)
    else:
        st.info("No hay tareas planificadas (verificá pendientes o MPPlanta).")

    # ==========================
    # Carga por máquina / día
    # ==========================
    st.subheader("⚙️ Carga por máquina y día")
    if not carga_md.empty:
        st.dataframe(carga_md.sort_values(["Fecha","Maquina"]), use_container_width=True)
    else:
        st.info("No hay carga registrada (puede que no haya tareas planificadas).")

    # ==========================
    # Resumen por OT (Fin vs Entrega)
    # ==========================
    st.subheader("📦 Resumen por OT (Fin vs Entrega)")
    if not resumen_ot.empty:
        st.dataframe(resumen_ot.sort_values(["EnRiesgo","Atraso_h","Fin_OT"], ascending=[False, False, True]),
                     use_container_width=True)
    else:
        st.info("Sin resumen disponible.")

    # ==========================
    # Exportación a Excel
    # ==========================
    st.subheader("💾 Exportar")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        schedule.to_excel(w, index=False, sheet_name="Schedule")
        if not resumen_ot.empty:
            resumen_ot.to_excel(w, index=False, sheet_name="Resumen_OT")
        if not carga_md.empty:
            carga_md.to_excel(w, index=False, sheet_name="Carga_Maquina_Dia")
    buf.seek(0)
    st.download_button(
        "⬇️ Descargar Excel de planificación",
        data=buf,
        file_name="Plan_Produccion_Theiler.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
