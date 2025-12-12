import pandas as pd
from modules.config_loader import cargar_config, es_si

# Duraciones fijas para procesos tercerizados sin cola (horas)
TERCERIZADOS_DURACION_FIJA_H = {
    "encapado": 72.0,
    "stamping": 72.0,
    "plastificado": 72.0,
    "cuño": 72.0,
}

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
    """Define si puede aplicarse setup menor. Robusta a tipos de datos."""
    if prev is None:
        return False

    proceso_lower = proceso.lower().strip()

    # ---------------------------------------------------------
    # 1. TROQUELADO (Mismo código)
    # ---------------------------------------------------------
    if "troquel" in proceso_lower:
        t_prev = str(prev.get("CodigoTroquel", "")).strip().lower()
        t_curr = str(curr.get("CodigoTroquel", "")).strip().lower()
        # Evitar coincidencia de vacíos
        if t_prev and t_curr and t_prev == t_curr:
            return True

    # ---------------------------------------------------------
    # 2. IMPRESIÓN (Mismo Cliente + (Mismo Color O Mismo Tamaño))
    # ---------------------------------------------------------
    if "impres" in proceso_lower:
        # Comparación de Cliente (Texto)
        c_prev = str(prev.get("Cliente", "")).strip().lower()
        c_curr = str(curr.get("Cliente", "")).strip().lower()
        mismo_cliente = (c_prev == c_curr) and (c_prev != "")

        if not mismo_cliente:
            return False

        # Comparación de Colores (Texto)
        col_prev = str(prev.get("Colores", "")).strip().lower()
        col_curr = str(curr.get("Colores", "")).strip().lower()
        mismos_colores = (col_prev == col_curr) and (col_prev != "")

        # Comparación de Tamaño (Numérica para evitar "80" vs "80.0")
        try:
            anc_prev = float(prev.get("PliAnc", 0) or 0)
            anc_curr = float(curr.get("PliAnc", 0) or 0)
            lar_prev = float(prev.get("PliLar", 0) or 0)
            lar_curr = float(curr.get("PliLar", 0) or 0)
            
            # Tolerancia pequeña por si hay decimales flotantes
            mismo_tamano = (abs(anc_prev - anc_curr) < 0.1) and (abs(lar_prev - lar_curr) < 0.1)
            # Asegurar que no sean cero (tamaños vacíos)
            if anc_prev == 0 or lar_prev == 0:
                mismo_tamano = False
                
        except (ValueError, TypeError):
            mismo_tamano = False

        if mismos_colores or mismo_tamano:
            return True

    # ---------------------------------------------------------
    # 3. PEGADO (Tipo + Material)
    # ---------------------------------------------------------
    if "peg" in proceso_lower:
        tipo_prev = str(prev.get("PegadoTipo", "")).strip().lower()
        tipo_curr = str(curr.get("PegadoTipo", "")).strip().lower()
        
        mat_prev = str(prev.get("MateriaPrima", "")).strip().lower()
        mat_curr = str(curr.get("MateriaPrima", "")).strip().lower()

        if (tipo_prev == tipo_curr) and (mat_prev == mat_curr) and tipo_prev:
            return True


    # ---------------------------------------------------------
    # 4. BOBINA (Misma Materia Prima)
    # ---------------------------------------------------------
    if "bobina" in proceso_lower:
        mp_prev = str(prev.get("MateriaPrima", "")).strip().lower()
        mp_curr = str(curr.get("MateriaPrima", "")).strip().lower()

        if mp_prev and mp_curr and mp_prev == mp_curr:
            return True

    return False

# =========================================================
# Tiempo de operación
# =========================================================

def tiempo_operacion_h(orden, proceso, maquina, cfg):
    """Devuelve (setup_h, proc_h) con soporte para dorso, barnizado y procesos tercerizados."""
    proceso_lower = proceso.lower().strip()

    if proceso_lower in TERCERIZADOS_DURACION_FIJA_H:
        return (0.0, TERCERIZADOS_DURACION_FIJA_H[proceso_lower])

    cap = capacidad_pliegos_h(proceso, maquina, cfg)

    # Si no hay capacidad definida, saltar
    if not cap or cap <= 0:
        return (0.0, 0.0)

    # Pliegos base
    pliegos = float(orden.get("CantidadPliegos", 0))
    proc_h = pliegos / cap

    # Si es impresión con dorso, duplicar tiempo

    if proceso in ("Impresión Offset", "Impresión Flexo"):
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