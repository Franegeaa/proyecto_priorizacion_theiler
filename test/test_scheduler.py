import pandas as pd
from datetime import date
from modules.scheduler import programar
from modules.config_loader import cargar_config

cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

# === TEST 1: Agrupamiento por código de troquel ===
def test_agrupamiento_por_troquel():
    data = [
        {"CodigoProducto": 1, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 5000, "CodigoTroquel": "TR-100"},
        {"CodigoProducto": 2, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 3000, "CodigoTroquel": "TR-100"},
        {"CodigoProducto": 3, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 4000, "CodigoTroquel": "TR-200"},
    ]
    df = pd.DataFrame(data)
    schedule = programar(df, cfg, start=date(2025, 10, 13))

    # Verificar que las dos primeras órdenes (TR-100) estén consecutivas
    troqueles = schedule.get("CodigoTroquel", pd.Series(dtype=str)).dropna().tolist()
    assert troqueles.count("TR-100") == 2
    i1 = troqueles.index("TR-100")
    assert troqueles[i1 + 1] == "TR-100"

# === TEST 2: Priorización por fecha de entrega ===
def test_priorizacion_por_fecha():
    data = [
        {"CodigoProducto": 1, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 10), "CantidadPliegos": 1000},
        {"CodigoProducto": 2, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 15), "CantidadPliegos": 5000},
    ]
    df = pd.DataFrame(data)
    schedule = programar(df, cfg, start=date(2025, 10, 1))
    assert schedule.iloc[0]["CodigoProducto"] == 1

# === TEST 3: Priorización por cantidad de pliegos cuando la fecha es igual ===
def test_priorizacion_por_pliegos():
    data = [
        {"CodigoProducto": 1, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 2000},
        {"CodigoProducto": 2, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 6000},
    ]
    df = pd.DataFrame(data)
    schedule = programar(df, cfg, start=date(2025, 10, 10))
    assert schedule.iloc[0]["CodigoProducto"] == 2

# === TEST 4: Considera FechaEntregaAjustada si existe ===
def test_fecha_ajustada_prioritaria():
    data = [
        {"CodigoProducto": 1, "Subcodigo": "A", "FechaEntregaAjustada": date(2025, 10, 15), "FechaEntrega": date(2025, 10, 10), "CantidadPliegos": 1000},
        {"CodigoProducto": 2, "Subcodigo": "A", "FechaEntregaAjustada": date(2025, 10, 12), "FechaEntrega": date(2025, 10, 10), "CantidadPliegos": 2000},
    ]
    df = pd.DataFrame(data)
    schedule = programar(df, cfg, start=date(2025, 10, 10))
    assert schedule.iloc[0]["CodigoProducto"] == 2

# === TEST 5: Que no rompa si falta CodigoTroquel ===
def test_sin_columna_troquel():
    data = [
        {"CodigoProducto": 1, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 20), "CantidadPliegos": 1000},
        {"CodigoProducto": 2, "Subcodigo": "A", "FechaEntrega": date(2025, 10, 21), "CantidadPliegos": 2000},
    ]
    df = pd.DataFrame(data)
    schedule = programar(df, cfg, start=date(2025, 10, 10))
    assert not schedule.empty
