import pandas as pd
from modules.config_loader import cargar_config, es_si

# =========================================================
# Capacidad y setups
# =========================================================

def capacidad_pliegos_h(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    if fila.empty:
        return None
    return float(fila["Capacidad_pliegos_hora"].iloc[0])

def setup_base_min(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    return float(fila["Setup_base_min"].iloc[0]) if not fila.empty else 0.0

def setup_menor_min(proceso, maquina, cfg):
    fila = cfg["maquinas"].query("Proceso==@proceso and Maquina==@maquina")
    return float(fila["Setup_menor_min"].iloc[0]) if not fila.empty else 0.0


# =========================================================
# Reglas para setup menor
# =========================================================

def usa_setup_menor(prev, curr, proceso):
    """Define si puede aplicarse setup menor según similitud entre órdenes."""
    if prev is None:
        return False

    proceso_lower = proceso.lower()

    # 🔹 Troquelado: mismo código de troquel
    if "troquel" in proceso_lower:
        if str(prev.get("CodigoTroquel", "")).strip().lower() == str(curr.get("CodigoTroquel", "")).strip().lower():
            return True

    # 🔹 Impresión: mismo cliente y colores o tamaño
    if "impres" in proceso_lower:
        mismo_cliente = str(prev.get("Cliente", "")).lower() == str(curr.get("Cliente", "")).lower()
        mismos_colores = str(prev.get("Colores", "")).lower() == str(curr.get("Colores", "")).lower()
        mismo_tamano = (
            str(prev.get("PliAnc", "")).lower() == str(curr.get("PliAnc", "")).lower()
            and str(prev.get("PliLar", "")).lower() == str(curr.get("PliLar", "")).lower()
        )
        if mismo_cliente and (mismos_colores or mismo_tamano):
            return True

    # 🔹 Pegado: mismo tipo de pegado y material
    if "peg" in proceso_lower:
        mismo_tipo = str(prev.get("PegadoTipo", "")).lower() == str(curr.get("PegadoTipo", "")).lower()
        mismo_mat = str(prev.get("MateriaPrima", "")).lower() == str(curr.get("MateriaPrima", "")).lower()
        if mismo_tipo and mismo_mat:
            return True

    return False


# =========================================================
# Tiempo de operación
# =========================================================

def tiempo_operacion_h(orden, proceso, maquina, cfg):
    """Devuelve (setup_h, proc_h) con soporte para dorso, barnizado y encapado."""
    cap = capacidad_pliegos_h(proceso, maquina, cfg)

    # Caso especial: encapado tercerizado → demora fija de 3 días
    if proceso.lower() == "encapado":
        proc_h = 72.0  # 72 horas = 3 días
        return (0.0, proc_h)

    # Si no hay capacidad definida, saltar
    if not cap or cap <= 0:
        return (0.0, 0.0)

    # Pliegos base
    pliegos = float(orden.get("CantidadPliegos", 0))
    proc_h = pliegos / cap

    # Si es impresión con dorso, duplicar tiempo
    if proceso in ("Impresión Offset Dorso", "Impresión Flexo Dorso"):
        proc_h *= 1.0  # ya se agregó como proceso separado
    elif proceso in ("Impresión Offset", "Impresión Flexo"):
        # Si el dorso está marcado en la OT, multiplicamos por 2
        frey = str(orden.get("FreyDorDpd", "")).lower() in ("sí", "true", "1")
        dorso = str(orden.get("Dorso", "")).lower() in ("sí", "true", "1")
        if frey or dorso:
            proc_h *= 2.0

    # Barnizado: usa menor capacidad si no está definida
    if proceso.lower() == "barnizado":
        if not cap or cap > 12000:
            cap = 10000
        proc_h = pliegos / cap

    return (0.0, proc_h)