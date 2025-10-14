import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
from modules.config_loader import cargar_config, horas_por_dia
from modules.scheduler import programar

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")

st.title("📦 Planificador de Producción – Theiler Packaging")

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    df = pd.read_excel(archivo)
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    st.subheader("⚙️ Parámetros de jornada")
    st.write(f"Jornada laboral: {horas_por_dia(cfg)} h/día")

    for c in ["Colores","Tamano","PegadoTipo","MateriaPrima","ImpresionOffset","ImpresionFlexo",
              "Encapado","OPP","Descartonado","Ventana","Pegado","CodigoTroquel","FechaEntregaAjustada"]:
        if c not in df.columns:
            df[c] = None

    st.info("🧠 Generando programa...")
    # --- Renombrar columnas importantes ---

    df.rename(columns={
    "ORDEN": "CodigoProducto",
    "Ped.": "Subcodigo",
    "CLIENTE": "Cliente",
    "Razon Social": "RazonSocial",
    "CANT/DDP": "CantidadPliegos",
    "FECH/ENT.": "FechaEntrega",
    "Mat/Prim1": "MateriaPrima",
    "CodTroTapa": "CodigoTroquelTapa",
    "CodTroCuerpo": "CodigoTroquelCuerpo",
    "Off Set": "ImpresionOffset",
    "Barnizado": "Barnizado",
    "FlexoDdp": "ImpresionFlexo",
    "Stamping": "Stamping",
    "Encapado": "Encapado",
    "PegadoPed": "Pegado",
    "Guillotinar": "Guillotinado",
    "Troquelar": "Troquelado",
    "DescartonadoSNDpd": "Descartonado",
    "Boca1_ddp": "Bocas",
    "Poses": "Poses",
    "Color1": "Color1",
    "Color2": "Color2",
    "Color3": "Color3",
    "Color4": "Color4",
    "Barnizado": "Barnizado_V",
    "ImpresionSNDpd": "Impresion_V",
    "TroqueladoSNDpd": "Troquelado_V",
    "GuillotinadoSNDpd": "Guillotinado_V",
    "DescartonadoSNDpd": "Descartonado_V",
    "PegadoSNDpd": "Pegado_V",
    "PegadoVSNDpd": "Pegado_ventana_V",
    "TienePrensado": "Prensado_V",
    "MPPlanta": "MateriaPrima_V",
    }, inplace=True)
    
    # --- Concatenar los colores (Color 1–5) en una sola columna 'Colores' ---
    color_cols = [c for c in df.columns if c.startswith("Color")]
    if color_cols:
        df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1)
    else:
        df["Colores"] = ""

    # --- Verificación básica ---
    if "CantidadPliegos" not in df.columns:
        st.error("⚠️ No se encontró la columna 'CANT/DDP' o 'CantidadPliegos' en el Excel. Revisá el nombre exacto.")
        st.stop()

    if "FechaEntrega" not in df.columns:
        st.error("⚠️ No se encontró la columna de fecha ('FECH/ENT.'). Revisá el nombre exacto en el archivo.")
        st.stop()

    st.success("✅ Columnas estandarizadas correctamente.")
    schedule = programar(df, cfg, start=date.today())

    st.success("✅ Programa generado correctamente")
    st.dataframe(schedule, use_container_width=True)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        schedule.to_excel(w, index=False, sheet_name="Programa")
    buf.seek(0)
    st.download_button("⬇️ Descargar programa", data=buf,
                       file_name="Programa_Produccion.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
