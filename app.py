import streamlit as st 
import pandas as pd
from datetime import date
from io import BytesIO
from collections import Counter
from modules.config_loader import cargar_config, horas_por_dia
from modules.scheduler import programar

# -------------------------------------------------------------------------------------
# 🧭 Configuración de la página
# -------------------------------------------------------------------------------------
st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

# -------------------------------------------------------------------------------------
# 📥 Subir archivo
# -------------------------------------------------------------------------------------
archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

if archivo is not None:
    df = pd.read_excel(archivo)
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    st.subheader("⚙️ Parámetros de jornada")
    st.write(f"Jornada laboral: {horas_por_dia(cfg)} h/día")

    # ---------------------------------------------------------------------------------
    # 🔧 Normalización básica de columnas
    # ---------------------------------------------------------------------------------
    col_counts = Counter(df.columns)
    cols_final = []
    seen = Counter()

    for c in df.columns:
        seen[c] += 1
        # Si es duplicada y estamos en la primera aparición → saltar
        if col_counts[c] > 1 and seen[c] == 1:
            continue
        cols_final.append(c)

    df = df[cols_final]

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
        "MPPlanta": "MateriaPrimaPlanta",
    }, inplace=True)

    # ---------------------------------------------------------------------------------
    # 🎨 Combinar colores (Color1–Color5)
    # ---------------------------------------------------------------------------------
    color_cols = [c for c in df.columns if c.startswith("Color")]
    df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1) if color_cols else ""

    # ---------------------------------------------------------------------------------
    # 🧠 Solo procesos PENDIENTES
    # ---------------------------------------------------------------------------------
    def to_bool_series(colnames):
        """Devuelve una serie booleana True/False si existe la columna pendiente"""
        for c in colnames:
            if c in df.columns:
                return df[c].astype(str).str.strip().str.lower().isin(
                    ["verdadero", "true", "si", "sí", "1", "x"]
                )
        return pd.Series(False, index=df.index)

    df["_PEN_Guillotina"]   = to_bool_series(["GuillotinadoSNDpd"])
    df["_PEN_Barnizado"]    = to_bool_series(["Barnizado.1"])
    df["_PEN_Encapado"]     = to_bool_series(["EncapadoSNDpd", "EncapadoSND"])
    df["_PEN_OPP"]          = to_bool_series(["OPPSNDpd", "OPPSND"])
    df["_PEN_Troquelado"]   = to_bool_series(["TroqueladoSNDpd", "TroqueladoSND"])
    df["_PEN_Descartonado"] = to_bool_series(["DescartonadoSNDpd", "DescartonadoSND"])
    df["_PEN_Ventana"]      = to_bool_series(["PegadoVSNDpd", "PegadoVSND"])
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])

    # ---------------------------------------------------------------------------------
    # 🖨️ Clasificación especial de Impresión (Flexo u Offset)
    # ---------------------------------------------------------------------------------
    if "ImpresionSNDpd" in df.columns:
        impresion_pend = df["ImpresionSNDpd"].astype(str).str.strip().str.lower().isin(
            ["verdadero", "true", "si", "sí", "1", "x"]
        )
    else:
        impresion_pend = pd.Series(False, index=df.index)

    materia = df.get("MateriaPrima", "").astype(str).str.lower()
    df["_PEN_ImpresionFlexo"]  = impresion_pend & materia.str.contains("micro", na=False)
    df["_PEN_ImpresionOffset"] = impresion_pend & materia.str.contains("cartulina", na=False)

    # (opcional: mantener una bandera general)
    df["_PEN_Impresion"] = df["_PEN_ImpresionFlexo"] | df["_PEN_ImpresionOffset"]

    # ---------------------------------------------------------------------------------
    # 🧩 Columna de troquel preferida
    # ---------------------------------------------------------------------------------
    for c in ["CodigoTroquelTapa", "CodigoTroquelCuerpo", "CodTroTapa", "CodTroCuerpo"]:
        if c in df.columns:
            df["CodigoTroquel"] = df[c]
            break

    # ---------------------------------------------------------------------------------
    # ✅ Verificación mínima
    # ---------------------------------------------------------------------------------
    if "CantidadPliegos" not in df.columns:
        st.error("⚠️ No se encontró la columna 'CANT/DDP' o 'CantidadPliegos' en el Excel.")
        st.stop()
    if "FechaEntrega" not in df.columns:
        st.error("⚠️ No se encontró la columna de fecha ('FECH/ENT.').")
        st.stop()

    st.success("✅ Columnas estandarizadas correctamente.")

    # ---------------------------------------------------------------------------------
    # 🧮 Ejecutar programación
    # ---------------------------------------------------------------------------------
    st.info("🧠 Generando programa...")
    schedule = programar(df, cfg, start=date.today())

    st.success("✅ Programa generado correctamente")
    st.dataframe(schedule, use_container_width=True)

    # ---------------------------------------------------------------------------------
    # 💾 Exportar resultado
    # ---------------------------------------------------------------------------------
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        schedule.to_excel(writer, index=False, sheet_name="Programa")
    buf.seek(0)

    st.download_button(
        "⬇️ Descargar programa",
        data=buf,
        file_name="Programa_Produccion.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
