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
        # print("Es feriado:", fecha_obj) 
        return True
    return False

def es_dia_habil(d, cfg, maquina=None):
    # 'd' debe ser un objeto date o datetime
    fecha_obj = d.date() if isinstance(d, datetime) else d
    
    # 0. Chequeo de HORAS EXTRAS (Prioridad Suprema)
    # Si el usuario definió horas extras para este día, ES HÁBIL, sin importar si es finde o feriado.
    horas_extras_general = cfg.get("horas_extras", {})
    
    # Si se especificó máquina, buscamos sus extras. Si no, asumimos que no hay extras (o lógica global si existiera)
    if maquina:
        extras_maquina = horas_extras_general.get(maquina, {})
        if fecha_obj in extras_maquina and extras_maquina[fecha_obj] > 0:
            return True

    # 1. Chequea fin de semana (5 = Sábado, 6 = Domingo)
    if fecha_obj.weekday() >= 5:
        return False
        
    # 2. Chequea feriados
    if es_feriado(fecha_obj, cfg):
        return False
        
    return True

def get_horas_totales_dia(d, cfg, maquina=None):
    """
    Devuelve la cantidad total de horas disponibles para trabajar en la fecha 'd'.
    Total = Base (si es día hábil normal) + Extras (si las hay).
    """
    fecha_obj = d.date() if isinstance(d, datetime) else d
    
    # 1. Horas Base
    es_finde = fecha_obj.weekday() >= 5
    es_feriado_dia = es_feriado(fecha_obj, cfg)
    
    if es_finde or es_feriado_dia:
        horas_base = 0.0
    else:
        # Es un día de semana normal
        horas_base = horas_por_dia(cfg)
    
    # 2. Horas Extra (inyectadas por el usuario específicamente para ESTE día)
    horas_extra_usuario = 0.0
    
    if maquina:
        horas_extras_general = cfg.get("horas_extras", {})
        extras_maquina = horas_extras_general.get(maquina, {})
        horas_extra_usuario = extras_maquina.get(fecha_obj, 0.0)
    
    return horas_base + horas_extra_usuario

def proximo_dia_habil(d, cfg, maquina=None):
    while not es_dia_habil(d, cfg, maquina=maquina):
        d += timedelta(days=1)
    return d

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
            "nombre": m,
            "fecha": fecha_inicio_real, 
            "hora": hora_base, 
            "resto_horas": resto_horas_inicial
        }

    agenda["General"] = {
        "nombre": "General",
        "fecha": fecha_inicio_real,
        "hora": hora_base,
        "resto_horas": resto_horas_inicial
    }

    return agenda

def sumar_horas_habiles(inicio: datetime, horas: float, cfg: dict) -> datetime:
    """
    Suma 'horas' a una fecha 'inicio' saltando días no hábiles (fines de semana y feriados).
    Asume que los días hábiles son de 24 horas para estos procesos (tercerizados).
    """
    tiempo_restante = timedelta(hours=horas)
    cursor = inicio

    while tiempo_restante.total_seconds() > 0:
        # Fin del día actual (23:59:59...)
        fin_dia = datetime.combine(cursor.date(), time.max)
        
        # Tiempo disponible hoy hasta fin del día
        disponible_hoy = fin_dia - cursor
        
        # Si entra todo hoy, listo
        if tiempo_restante <= disponible_hoy:
            return cursor + tiempo_restante
        
        # Si no entra, consumimos lo que queda del día
        tiempo_restante -= (disponible_hoy + timedelta(microseconds=1)) # +1us para saltar al dia sig
        
        # Avanzamos al inicio del siguiente día hábil
        siguiente_dia = cursor.date() + timedelta(days=1)
        # NOTA: Aqui hay un tema, tercerizados no tienen "maquina" especifica definida en el nombre de proceso
        # normalmente asumen calendario general.
        siguiente_dia = proximo_dia_habil(siguiente_dia, cfg)
        cursor = datetime.combine(siguiente_dia, time.min)
        
    return cursor