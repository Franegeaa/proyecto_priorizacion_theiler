
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.schedulers.tasks import _expandir_tareas
from modules.utils.config_loader import cargar_config

def debug_expansion():
    data = [
        {
            "CodigoProducto": "TEST1", "Subcodigo": "01", 
            "FechaLlegadaChapas": pd.Timestamp("2025-12-12"),
            "PeliculaArt": "Si"
        },
        {
            "CodigoProducto": "TEST2", "Subcodigo": "01", "Cliente": "C2", "FechaEntrega": "20/12/2025",
            "CantidadPliegos": 5000, 
            "_PEN_Troquelado": "Si",
            "TroquelArt": "Si",
            "FechaLlegadaTroquel": pd.Timestamp("2025-12-15"),
            "MateriaPrima": "Cartulina"
        }
    ]
    df = pd.DataFrame(data)
    
    # Mock Config
    cfg = {"maquinas": pd.DataFrame(), "orden_std": []} 
    
    # Need to mock 'maquinas' config to prevent errors?
    # _expandir_tareas calls elegir_maquina which uses cfg
    # Let's load real config just in case
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    tasks = _expandir_tareas(df, cfg)
    
    print("Tasks Columns:", tasks.columns)
    if not tasks.empty:
        row = tasks.iloc[0]
        print("Task 0 TroquelArt:", row.get("TroquelArt"))
        print("Task 0 FechaLlegadaTroquel:", row.get("FechaLlegadaTroquel"))
        
        if row.get("TroquelArt") == "Si" and row.get("FechaLlegadaTroquel") == pd.Timestamp("2025-12-15"):
            print("PASS: Data correctly expanded.")
        else:
            print("FAIL: Data missing or incorrect.")

if __name__ == "__main__":
    debug_expansion()
