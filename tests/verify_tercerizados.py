import pandas as pd
from datetime import datetime, time, date
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar
from modules.utils.config_loader import cargar_config

def verify_tercerizados():
    print("=== Verifying Tercerizados Delay Logic ===")
    
    cfg = {
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [8]}),
        "feriados": set(),
        "orden_std": ["Impresión Flexo", "Plastificado", "Troquelado"], 
        "maquinas": pd.DataFrame({
            "Maquina": ["Flexo", "Troqueladora", "TERCERIZADO"],
            "Proceso": ["Impresión Flexo", "Troquelado", "Plastificado"],
            "Capacidad_pliegos_hora": [1000, 1000, 1000], 
            "Setup_base_min": [0, 0, 0],
            "Setup_menor_min": [0, 0, 0]
        }),
        "downtimes": [],
        "horas_laborales": 8
    }
    
    today = datetime(2026, 3, 27, 7, 0).date() # Friday
    start_time = time(7, 0)
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "Test_Plastif", "Subcodigo": "A", 
            "CantidadProductos": 1000, "CantidadPliegos": 1000, "CantidadPliegosNetos": 1000,
            "Proceso": "Impresión Flexo", "Urgente": "No", "FechaEntrega": today, 
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_ImpresionFlexo": "Si", "_PEN_Plastificado": "Si", "_PEN_Troquelado": "Si"
        }
    ])
    
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("ERROR: Schedule is empty!")
        sys.exit(1)

    print(schedule[["Maquina", "Proceso", "Inicio", "Fin", "Duracion_h"]])
    
    troq_start = schedule[schedule["Proceso"] == "Troquelado"]["Inicio"].iloc[0]
    plas_end = schedule[schedule["Proceso"] == "Plastificado"]["Fin"].iloc[0]
    
    start_fmt = troq_start.strftime('%Y-%m-%d %H:%M')
    end_fmt = plas_end.strftime('%Y-%m-%d %H:%M')
    print(f"\nPlastificado Fin: {end_fmt}")
    print(f"Troquelado Inicio: {start_fmt}")
    
    if troq_start >= plas_end:
        print("SUCCESS: Troquelado correctly waits for Plastificado.")
    else:
        print("FAILURE: Troquelado started before Plastificado finished!")

if __name__ == "__main__":
    verify_tercerizados()
