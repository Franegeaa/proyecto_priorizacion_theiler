import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def verify_machine_delay():
    print("=== Verifying Machine Delay Logic ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["M1", "M2"],
            "Proceso": ["P1", "P2"],
            "Capacidad_pliegos_hora": [1000, 1000], 
            "Setup_base_min": [0, 0],
            "Setup_menor_min": [0, 0]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["P1", "P2"],
        "horas_laborales": 24, # Work 24h to simplify
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [24.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(0, 0)
    
    # 2. Create Test Data
    # OT1: Due today.
    # P1 (M1): Takes 10 hours. Finish 10:00. (Safe)
    # P2 (M2): Takes 20 hours. Start 10:00. Finish 30:00 (Tomorrow 06:00). (Late)
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "LateOT", "Subcodigo": "A", 
            "CantidadProductos": 1000, "CantidadPliegos": 10000, "CantidadPliegosNetos": 10000,
            "Proceso": "P2", "Urgente": "No", "FechaEntrega": today, # Due Today
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_P1": "Si", "_PEN_P2": "Si"
        }
    ])
    
    # Update CFG logic for duration
    # P1: 10000 sheets / 1000 cph = 10h
    # P2: 10000 sheets / 1000 cph = 10h
    # Total flow: Start 00:00 -> M1 (10h) -> 10:00 -> M2 (10h) -> 20:00.
    # Wait, 20:00 is same day. DueDate includes time? usually 18:00 cutoff in code.
    # Let's make it take longer.
    # P2 taking 20 hours: 20000 sheets?
    
    df_ordenes.loc[0, "CantidadPliegos"] = 20000 # 20h per process
    # M1: 00:00 -> 20:00. (Late vs 18:00? Maybe)
    # M2: 20:00 -> +20h -> 40:00 (Day+1 16:00). Definitely Late.
    
    # Run Scheduler
    schedule, carga_md, resumen_ot, detalle_maquina = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    print("\nSchedule Columns:", schedule.columns.tolist())
    try:
        print(schedule[["Maquina", "Inicio", "Fin", "DueDate"]])
    except KeyError as e:
        print(f"Error printing schedule subset: {e}")
    
    # Check if 'Atraso_h' exists in schedule (Plan Goal)
    if "Atraso_h" in schedule.columns:
        print("\n'Atraso_h' column found in schedule!")
        print(schedule[["Maquina", "Fin", "DueDate", "Atraso_h"]])
    else:
        print("\n'Atraso_h' NOT found in schedule (Current Behavior).")
        
    # Check resumen_ot
    print("\nResumen OT:")
    print(resumen_ot[["OT_id", "Atraso_h", "EnRiesgo"]])

if __name__ == "__main__":
    verify_machine_delay()
