import pandas as pd
import streamlit as st # Potentially needed for caching parsing if we wanted, but mainly for display if we print warnings? Actually better to return issues.

def parse_spanish_date(date_str):
    if pd.isna(date_str) or str(date_str).strip() == "":
        return pd.NaT
    
    s = str(date_str).lower().strip()
    # Mapa de meses abreviados español
    meses = {
        "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
        "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12"
    }
    
    try:
        # Intento formato '12-dic-25' o '12-dic-2025'
        for mes_name, mes_num in meses.items():
            if mes_name in s:
                s = s.replace(mes_name, mes_num)
                break
        
        # Reemplazar separadores comunes
        s = s.replace("-", "/").replace(".", "/")
        
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.NaT

def process_uploaded_dataframe(df):
    """
    Applies all transformations, renames, and calculated columns to the raw dataframe.
    """
    # --- RENOMBRADO ---
    df.rename(columns={
        "ORDEN": "CodigoProducto",
        "Ped.": "Subcodigo",
        "CLIENTE": "Cliente",
        "ART/DDP": "Cliente-articulo",
        "Razon Social": "RazonSocial",
        "CANT/DDP": "CantidadPliegos",
        "FECH/ENT.": "FechaEntrega",
        "Mat/Prim1": "MateriaPrima",
        "MPPlanta": "MateriaPrimaPlanta",
        "CodTroTapa": "CodigoTroquelTapa",
        "CodTroCuerpo": "CodigoTroquelCuerpo",
        "FechaChaDpv": "FechaLlegadaChapas", # Corrección aplicada en paso anterior
        "FechaTroDpv": "FechaLlegadaTroquel",
        "Pli Anc": "PliAnc",
        "Pli Lar": "PliLar",
    }, inplace=True)

    # --- COLORES COMBINADOS ---
    color_cols = [c for c in df.columns if str(c).startswith("Color")]
    df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1) if color_cols else ""

    # --- PARSEO DE FECHAS (CUSTOM ESPAÑOL) ---
    if "FechaLlegadaChapas" in df.columns:
        df["FechaLlegadaChapas"] = df["FechaLlegadaChapas"].apply(parse_spanish_date)
    
    if "FechaLlegadaTroquel" in df.columns:
        df["FechaLlegadaTroquel"] = df["FechaLlegadaTroquel"].apply(parse_spanish_date)

    # --- FLAGS SOLO PENDIENTES ---
    def to_bool_series(names):
        for c in names:
            if c in df.columns:
                return df[c].astype(str).str.strip().str.lower().isin(["verdadero", "true", "si", "sí", "1", "x"])
        return pd.Series(False, index=df.index)

    df["_PEN_Corte_Bobina"] = to_bool_series(["CorteSNDdp"])
    df["_PEN_Guillotina"]   = to_bool_series(["GuillotinadoSNDpd"])
    df["_PEN_Barnizado"]    = to_bool_series(["Barniz"])
    df["_PEN_Encapado"]     = to_bool_series(["Encapa", "EncapadoSND"])
    df["_PEN_Cuño"]         = to_bool_series(["Cuño", "CuñoSND"])
    df["_PEN_Plastificado"]  = to_bool_series(["Plastifica", "PlastificadoSND"]) 
    df["_PEN_Stamping"]     = to_bool_series(["StampSNDdp", "StampingSND"])
    df["_PEN_OPP"]          = to_bool_series(["OPPSNDpd", "OPPSND"])
    df["_PEN_Troquelado"]   = to_bool_series(["TroqueladoSNDpd", "TroqueladoSND"])
    df["_PEN_Descartonado"] = to_bool_series(["DescartonadoSNDpd", "DescartonadoSND"])
    df["_PEN_Ventana"]      = to_bool_series(["PegadoVSNDpd", "PegadoVSND"])
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])
    df["_IMP_Dorso"]      = to_bool_series(["Dorso"])      # Flexo → doble pasada
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])
    df["_IMP_Dorso"]      = to_bool_series(["Dorso"])      # Flexo → doble pasada
    df["_IMP_FreyDorDpd"] = to_bool_series(["FreyDorDpd"])    # Offset → doble pasada
    
    # --- FLAGO DE REORDENAMIENTO (TROQUEL ANTES DE IMPRESION) ---
    df["_TroqAntes"] = to_bool_series(["TroqAntes", "TroquelAntes", "TroqueladoAntes"])

    # --- TROQUEL PREFERIDO ---
    for c in ["CodigoTroquel", "CodigoTroquelTapa", "CodigoTroquelCuerpo", "CodTroTapa", "CodTroCuerpo"]:
        if c in df.columns:
            df["CodigoTroquel"] = df[c]
            break

    # --- IMPRESIÓN: SEPARAR OFFSET/FLEXO ---
    mat = df.get("MateriaPrima", "").astype(str).str.lower()
    imp_pend = to_bool_series(["ImpresionSNDpd", "ImpresionSND"])
    df["_PEN_ImpresionFlexo"]  = imp_pend & (mat.str.contains("micro", na=False) )
    df["_PEN_ImpresionOffset"] = imp_pend & (mat.str.contains("cartulina", na=False) | mat.str.contains("carton", na=False) | mat.str.contains("papel", na=False) )

    # --- OT_ID ---
    if "OT_id" not in df.columns:
        df["OT_id"] = (
           df["CodigoProducto"].astype(str).str.strip() + "-" + df["Subcodigo"].astype(str).str.strip() 
        )
    
    return df
