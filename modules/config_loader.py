import pandas as pd
from datetime import date, time, timedelta
import numpy as np

def es_si(x):
    """Interpreta distintos formatos como 'sí' o verdadero."""

    # Si es una Serie o DataFrame (por error), devolvemos False
    if isinstance(x, (pd.Series, pd.DataFrame, np.ndarray)):
        return False

    if pd.isna(x):
        return False

    s = str(x).strip().lower()
    return s in {"si", "sí", "s", "true", "1", "x", "ok", "offset", "flexo", "pegado", "verdadero"}

def cargar_config(path="config/Config_Priorizacion_Theiler.xlsx"):
    cfg = {}
    cfg["jornada"] = pd.read_excel(path, sheet_name="Jornada")
    cfg["feriados"] = set(pd.read_excel(path, sheet_name="Feriados")["Fecha"].dropna().astype(str))
    cfg["orden_std"] = pd.read_excel(path, sheet_name="OrdenEstandar").sort_values("Secuencia")["Proceso"].tolist() # Lista ordenada de procesos estándar
    cfg["maquinas"] = pd.read_excel(path, sheet_name="Maquinas")
    cfg["reglas"] = pd.read_excel(path, sheet_name="ReglasCambio")
    return cfg

def horas_por_dia(cfg):
    j = cfg["jornada"]
    base = j.loc[j["Parametro"]=="Horas_base_por_dia","Valor"].iloc[0] if (j["Parametro"]=="Horas_base_por_dia").any() else 8.5
    extra = float(j.loc[j["Parametro"]=="Horas_extra_por_dia","Valor"].iloc[0]) if (j["Parametro"]=="Horas_extra_por_dia").any() else 0.0
    return base + extra

def es_feriado(d, cfg):
    return d.strftime("%Y-%m-%d") in cfg["feriados"]

def proximo_dia_habil(d, cfg):
    while d.weekday() >= 5 or es_feriado(d, cfg):
        d += timedelta(days=1)
    return d

def construir_calendario(cfg, start=None):
    if start is None:
        start = date.today()
    start = proximo_dia_habil(start, cfg)
    h_dia = horas_por_dia(cfg)
    inicio_hora = time(8, 0)
    agenda = {}
    for m in cfg["maquinas"]["Maquina"].unique():
        agenda[m] = {"fecha": start, "hora": inicio_hora, "resto_horas": h_dia}
    return agenda
    