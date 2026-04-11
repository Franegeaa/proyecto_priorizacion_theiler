"""
Configuración del Galpón 2 – Planificación de Cartonaje.

Define las máquinas, velocidades y flujo de procesos del Galpón 2.
El flujo estándar es: Guillotina → Troquelado → Prensado

Máquinas:
  - Guillotina G2
  - Troqueladoras manuales: Y-TroqNº2, Z-TroqNº1
  - Troqueladoras automáticas: Iberica G2, Duyan 2
  - Prensas manuales: 12-bandejaN2, 15-bandejaN1
  - Prensas automáticas: 18-bandeja-n3, 19-bandeja-n4, 20-bandeja-n5
"""

import pandas as pd
import copy
from modules.utils.config_loader import cargar_config


# ---------------------------------------------------------------
# VELOCIDADES (pliegos/hora) — basadas en industry standards y
# equivalencias con Galpón 1 donde corresponde
# ---------------------------------------------------------------
VELOCIDADES_G2 = {
    # Guillotina: igual que la del Galpón 1
    "Guillotina G2": 500,

    # Troqueladoras manuales: sin restricción de tamaño, misma vel. que manuales G1
    "Y-TroqNº2": 800,
    "Z-TroqNº1": 800,

    # Troqueladoras automáticas: mismas características que G1
    "Iberica G2": 2500,
    "Duyan 2": 3000,

    # Prensas manuales: ~1800-2000 piezas/hora (semiautomáticas de formación de bandeja)
    "12-bandejaN2": 1800,
    "15-bandejaN1": 1800,

    # Prensas automáticas: ~5000-7000 piezas/hora
    "18-bandeja-n3": 5000,
    "19-bandeja-n4": 5000,
    "20-bandeja-n5": 5000,
}

# Setup base (minutos): tiempo de cambio de trabajo completo
SETUP_BASE_G2 = {
    "Guillotina G2": 10,
    "Y-TroqNº2": 30,
    "Z-TroqNº1": 30,
    "Iberica G2": 45,
    "Duyan 2": 45,
    "12-bandejaN2": 20,
    "15-bandejaN1": 20,
    "18-bandeja-n3": 30,
    "19-bandeja-n4": 30,
    "20-bandeja-n5": 30,
}

# Setup menor (minutos): cambio de lote del mismo tipo
SETUP_MENOR_G2 = {
    "Guillotina G2": 5,
    "Y-TroqNº2": 10,
    "Z-TroqNº1": 10,
    "Iberica G2": 15,
    "Duyan 2": 15,
    "12-bandejaN2": 8,
    "15-bandejaN1": 8,
    "18-bandeja-n3": 10,
    "19-bandeja-n4": 10,
    "20-bandeja-n5": 10,
}

# Procesos de cada máquina
PROCESO_G2 = {
    "Guillotina G2": "Guillotina",
    "Y-TroqNº2": "Troquelado",
    "Z-TroqNº1": "Troquelado",
    "Iberica G2": "Troquelado",
    "Duyan 2": "Troquelado",
    "12-bandejaN2": "Prensado",
    "15-bandejaN1": "Prensado",
    "18-bandeja-n3": "Prensado",
    "19-bandeja-n4": "Prensado",
    "20-bandeja-n5": "Prensado",
}

# Tipo (manual/automatica) — para lógica de balanceo
TIPO_G2 = {
    "Guillotina G2": "manual",
    "Y-TroqNº2": "manual",
    "Z-TroqNº1": "manual",
    "Iberica G2": "automatica",
    "Duyan 2": "automatica",
    "12-bandejaN2": "manual",
    "15-bandejaN1": "manual",
    "18-bandeja-n3": "automatica",
    "19-bandeja-n4": "automatica",
    "20-bandeja-n5": "automatica",
}

# Flujo estándar del Galpón 2
ORDEN_STD_G2 = ["Guillotina", "Troquelado", "Prensado"]

# Nombre de identificación para las prensas en el excel
# El campo "TienePrensado" en el excel contiene "bandejaN<numero>",
# e.g. "CARTONAJE - BANDEJA Nº1" → va a "15-bandejaN1"
# Se hace matching por número de bandeja.


def construir_maquinas_g2_df():
    """Construye un DataFrame de máquinas compatible con el scheduler."""
    filas = []
    for maq, proceso in PROCESO_G2.items():
        filas.append({
            "Maquina": maq,
            "Proceso": proceso,
            "Capacidad_pliegos_hora": VELOCIDADES_G2[maq],
            "Setup_base_min": SETUP_BASE_G2[maq],
            "Setup_menor_min": SETUP_MENOR_G2[maq],
            "TipoMaquina": TIPO_G2[maq],
            "_IsCustom": False,
            "PliMaxAnc": None,
            "PliMaxLar": None,
            "PliMinAnc": None,
            "PliMinLar": None,
            "TipoTroquel": None,
        })
    return pd.DataFrame(filas)


def cargar_config_galpon2(path_config="config/Config_Priorizacion_Theiler.xlsx"):
    """
    Carga la configuración base del Excel y la adapta para el Galpón 2:
    - Reemplaza las máquinas por las del G2
    - Establece el flujo de procesos del G2
    - Preserva jornada, feriados, reglas, etc.
    """
    cfg_base = cargar_config(path_config)

    # Crear config G2 como copia independiente
    cfg_g2 = {
        "jornada": cfg_base["jornada"].copy(),
        "feriados": copy.copy(cfg_base["feriados"]),
        "orden_std": ORDEN_STD_G2.copy(),
        "maquinas": construir_maquinas_g2_df(),
        "reglas": cfg_base["reglas"].copy(),
        "mapa_abreviaturas": dict(cfg_base.get("mapa_abreviaturas", {})),
        "troquel_preferences": {},
        # No hay procesos tercerizados en G2 por ahora
        "_procesos_terc_sin_cola": set(),
        "_galpon": 2,
    }

    # Guardar copia base de máquinas para reset (igual que en G1)
    cfg_g2["_maquinas_base"] = cfg_g2["maquinas"].copy()

    return cfg_g2
