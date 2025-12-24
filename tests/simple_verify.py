import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.scheduler import programar

def check_simple():
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["M1"],
            "Proceso": ["P1"],
            "Capacidad_pliegos_hora": [1000], 
            "Setup_base_min": [0], "Setup_menor_min": [0]
        }),
        "downtimes": [], "feriados": set(), "orden_std": ["P1"],
        "horas_laborales": 24,
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [24.0]})
    }
    
    df = pd.DataFrame([{
        "CodigoProducto": "T1", "Subcodigo": "A", "CantidadProductos": 1000, 
        "Proceso": "P1", "Urgente": "No", "FechaEntrega": date.today(),
        "MateriaPrima": "X", "Cliente": "C", "Poses": 1, 
        "CantidadPliegos": 50000, # 50 hours -> Late
        "_PEN_P1": "Si"
    }])
    
    s, _, _, _ = programar(df, cfg, start=date.today(), start_time=time(0,0))
    
    print("Columns:", s.columns.tolist())
    if "Atraso_h" in s.columns:
        print("Atraso_h found!")
        print(s[["Atraso_h"]].head())
    else:
        print("Atraso_h MISSING")

if __name__ == "__main__":
    check_simple()
