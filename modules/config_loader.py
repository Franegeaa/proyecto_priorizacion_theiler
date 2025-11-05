import pandas as pd
from datetime import date, datetime, time, timedelta
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
    df_abbr = pd.read_excel(path, sheet_name="Abreviaturas")
    mapa = pd.Series(
            df_abbr["NombreProceso"].values, 
            index=df_abbr["Abbr"]
        ).to_dict()
    cfg["mapa_abreviaturas"] = mapa
    return cfg

def horas_por_dia(cfg):
    j = cfg["jornada"]
    base = j.loc[j["Parametro"]=="Horas_base_por_dia","Valor"].iloc[0] if (j["Parametro"]=="Horas_base_por_dia").any() else 8.5
    extra = float(j.loc[j["Parametro"]=="Horas_extra_por_dia","Valor"].iloc[0]) if (j["Parametro"]=="Horas_extra_por_dia").any() else 0.0
    return base + extra

def es_feriado(d, cfg):
    # d puede ser un objeto 'date' o 'datetime'
    fecha_obj = d.date() if isinstance(d, datetime) else d
    
    # Ahora comparamos un objeto 'date' con un set de 'date'
    if fecha_obj in cfg["feriados"]:
        print("Es feriado:", fecha_obj) # Tu debug (ahora sí debería funcionar)
        return True
    return False

def proximo_dia_habil(d, cfg):
    while d.weekday() == 5 or d.weekday() == 6 or es_feriado(d, cfg):
        d += timedelta(days=1)
    return d

def es_dia_habil(d, cfg):
    # 'd' debe ser un objeto date o datetime
    # 1. Chequea fin de semana (5 = Sábado, 6 = Domingo)
    if d.weekday() >= 5:
        return False
        
    # 2. Chequea feriados (usa la función que ya tenías)
    if es_feriado(d, cfg):
        return False
        
    return True


def construir_calendario(cfg, start=None, start_time=None):
    # 1. Establecer la fecha y hora base
    fecha_base = start if start else date.today()
    hora_base = start_time if start_time else time(7, 0) # Tu original usaba 7:00

    # 2. Validar que el DÍA de inicio sea hábil
    fecha_inicio_real = fecha_base
    if not es_dia_habil(fecha_base, cfg):
        # Si el día seleccionado es feriado/finde, saltar al próximo hábil
        # (Tu proximo_dia_habil ya avanza 1 día, así que está bien)
        fecha_inicio_real = proximo_dia_habil(fecha_base, cfg)
        # Al saltar de día, forzamos el inicio a la mañana
        hora_base = time(7, 0) 
    
    h_dia = horas_por_dia(cfg)
    
    # 3. Calcular horas restantes
    # (Ajusta el '7' si tu jornada empieza a otra hora, ej. 8)
    inicio_jornada_h = 7 
    horas_usadas = (hora_base.hour - inicio_jornada_h) + (hora_base.minute / 60.0)
    resto_horas_inicial = max(0, h_dia - horas_usadas)

    # 4. Crear agenda para cada máquina
    agenda = {}
    for m in cfg["maquinas"]["Maquina"].unique():
        agenda[m] = {
            "fecha": fecha_inicio_real, 
            "hora": hora_base, 
            "resto_horas": resto_horas_inicial
        }

    # 5. --- AÑADIR ESTA CLAVE "GENERAL" ---
    # Esta es la clave que faltaba y que causa el error
    agenda["General"] = {
        "fecha": fecha_inicio_real,
        "hora": hora_base,
        "resto_horas": resto_horas_inicial
    }
    # --- FIN DE LA MODIFICACIÓN ---

    return agenda