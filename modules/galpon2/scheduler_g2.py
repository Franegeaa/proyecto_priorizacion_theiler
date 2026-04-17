"""
Scheduler del Galpón 2 (Cartonaje).

Wrapper del scheduler principal que:
1. Filtra solo órdenes de clientes CARTONAJE
2. Usa la configuración de máquinas del Galpón 2
3. Maneja la asignación de prensas por número de bandeja
4. Flujo: Guillotina → Troquelado → Prensado
"""

import pandas as pd
from datetime import date

from modules.scheduler import programar as _programar_base


# Nombres canónicos de las prensas del G2
PRENSAS_G2 = {
    "12-bandejaN2",
    "15-bandejaN1",
    "18-bandeja-n3",
    "19-bandeja-n4",
    "20-bandeja-n5",
}

# Prensas manuales vs automáticas
PRENSAS_MANUALES_G2 = {"12-bandejaN2", "15-bandejaN1"}
PRENSAS_AUTO_G2 = {"18-bandeja-n3", "19-bandeja-n4", "20-bandeja-n5"}


def _filtrar_solo_cartonaje(df: pd.DataFrame) -> pd.DataFrame:
    """Retorna solo las filas cuyo cliente contiene 'cartonaje'."""
    if "Cliente" not in df.columns:
        return df
    mask = df["Cliente"].astype(str).str.lower().str.contains("cartonaje", na=False)
    return df[mask].copy()


def _asignar_prensa_por_bandeja(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lee el campo 'TienePrensado' (ej: "CARTONAJE - BANDEJA Nº1") y
    extrae el número de bandeja para asignar la máquina correcta.

    Mapeo:
        Nº2  → 12-bandejaN2
        Nº1  → 15-bandejaN1
        Nº3  → 18-bandeja-n3
        Nº4  → 19-bandeja-n4
        Nº5  → 20-bandeja-n5

    El resultado se guarda en la columna '_Prensa_Asignada' para
    que el scheduler pueda usarla.
    """
    if "TienePrensado" not in df.columns:
        df["_Prensa_Asignada"] = None
        return df

    def _extraer_prensa(val):
        if pd.isna(val) or str(val).strip() == "":
            return None
        s = str(val).lower()

        # Extraemos el número de bandeja buscando "nº<n>" o "n<n>" o "nro<n>"
        import re
        # Buscar patrones como "nº1", "nro1", "n1", "n°1", "bandeja1", "bandeja 1"
        match = re.search(r'n[ºo°]?\s*(\d+)', s)
        if not match:
            # fallback: buscar dígito solo si dice "bandeja"
            match = re.search(r'bandeja\s*(\d+)', s)
        if match:
            num = int(match.group(1))
            mapa = {
                2: "12-bandejaN2",
                1: "15-bandejaN1",
                3: "18-bandeja-n3",
                4: "19-bandeja-n4",
                5: "20-bandeja-n5",
            }
            return mapa.get(num)
        return None

    df = df.copy()
    df["_Prensa_Asignada"] = df["TienePrensado"].apply(_extraer_prensa)
    return df


def programar_galpon2(df_ordenes: pd.DataFrame, cfg_g2: dict,
                      start=None, start_time=None, debug=False):
    """
    Planifica las órdenes de Cartonaje usando la config del Galpón 2.

    Parámetros:
        df_ordenes: DataFrame completo de órdenes (se filtran las de Cartonaje)
        cfg_g2: Config del Galpón 2 (resultado de cargar_config_galpon2())
        start: Fecha de inicio del plan
        start_time: Hora de inicio del plan

    Retorna:
        (schedule, carga_md, resumen_ot, detalle_maquina) — igual que el scheduler base
    """
    if start is None:
        start = date.today()

    # 1. Filtrar solo Cartonaje
    df_cartonaje = _filtrar_solo_cartonaje(df_ordenes)
    if df_cartonaje.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # 2. Asignar prensa por número de bandeja (agrega columna _Prensa_Asignada)
    df_cartonaje = _asignar_prensa_por_bandeja(df_cartonaje)

    # 3. Inyectar asignaciones de prensa como locked_assignments en cfg
    #    Para que el scheduler respete la prensa asignada por número de bandeja
    locked = cfg_g2.get("locked_assignments", {})

    # Crear asignaciones de prensa para filas que tienen _Prensa_Asignada
    mask_prensa = df_cartonaje["_Prensa_Asignada"].notna()
    for _, row in df_cartonaje[mask_prensa].iterrows():
        ot_id = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        prensa = row["_Prensa_Asignada"]
        if prensa:
            locked[(ot_id, "Prensado")] = prensa

    cfg_g2["locked_assignments"] = locked

    # 4. El scheduler base maneja el resto.
    # NOTA: El filtro de Cartonaje en scheduler.py excluye a Cartonaje del G1,
    # pero aquí ya venimos con un df que SOLO tiene Cartonaje, por lo que
    # necesitamos deshabilitar ese filtro pasando cfg con un flag.
    cfg_g2["_galpon"] = 2  # señal para saltear el filtro de Cartonaje en scheduler.py

    return _programar_base(df_cartonaje, cfg_g2, start=start, start_time=start_time, debug=debug)
