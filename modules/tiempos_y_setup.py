import pandas as pd
from modules.config_loader import es_si

def capacidad_pliegos_h(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    if fila.empty: return None
    return float(fila["Capacidad_pliegos_hora"].iloc[0])

def setup_base_min(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    return float(fila["Setup_base_min"].iloc[0]) if not fila.empty else 0.0

def setup_menor_min(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    return float(fila["Setup_menor_min"].iloc[0]) if not fila.empty else 0.0

def usa_setup_menor(prev, curr, proceso):
    if prev is None:
        return False
    if proceso == "Troquelado":
        if str(prev.get("CodigoTroquel","")).strip() == str(curr.get("CodigoTroquel","")).strip():
            return True
    if proceso == "Impresión":
        mismo_cliente = str(prev.get("Cliente","")).lower() == str(curr.get("Cliente","")).lower()
        mismos_colores = str(prev.get("Colores","")).lower() == str(curr.get("Colores","")).lower()
        mismo_tamano  = str(prev.get("Tamano","")).lower()  == str(curr.get("Tamano","")).lower()
        if mismo_cliente and (mismos_colores or mismo_tamano):
            return True
    if proceso == "Pegado":
        mismo_tipo = str(prev.get("PegadoTipo","")).lower() == str(curr.get("PegadoTipo","")).lower()
        mismo_mat  = str(prev.get("MateriaPrima","")).lower() == str(curr.get("MateriaPrima","")).lower()
        if mismo_tipo and mismo_mat:
            return True
    return False

def tiempo_operacion_h(orden, proceso, maquina, cfg):
    cap = capacidad_pliegos_h(proceso, maquina, cfg)
    if not cap or cap <= 0:
        return (0.0, 0.0)
    proc_h = float(orden.get("CantidadPliegos", 0)) / cap
    return (0.0, proc_h)
