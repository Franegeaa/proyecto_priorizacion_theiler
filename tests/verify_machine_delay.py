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
            "Proceso": ["Impresión Flexo", "Troquelado"],
            "Capacidad_pliegos_hora": [1000, 1000], 
            "Setup_base_min": [0, 0],
            "Setup_menor_min": [0, 0]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Impresión Flexo", "Troquelado"],
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
    # P1 (Flexo): Takes 10 hours. Finish 10:00.
    # P2 (Troquel): Takes 20 hours. Start 10:00. Finish +20 = 30:00 (Tomorrow 06:00).
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "LateOT", "Subcodigo": "A", 
            "CantidadProductos": 1000, "CantidadPliegos": 10000, "CantidadPliegosNetos": 10000,
            "Proceso": "Impresión Flexo", "Urgente": "No", "FechaEntrega": today, # Due Today
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_ImpresionFlexo": "Si", "_PEN_Troquelado": "Si"
        }
    ])
    
    # Increase load to ensure it goes late
    df_ordenes.loc[0, "CantidadPliegos"] = 20000 # 20h per process
    # M1: 00:00 -> 20:00.
    # M2: 20:00 -> +20h -> 40:00 (Day+1 16:00).
    
    # Run Scheduler
    schedule, carga_md, resumen_ot, detalle_maquina = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    print("\nSchedule Columns:", schedule.columns.tolist())
    
    if schedule.empty:
        print("ERROR: Schedule is empty!")
        sys.exit(1)

    try:
        print(schedule[["Maquina", "Inicio", "Fin", "DueDate"]])
    except KeyError as e:
        print(f"Error printing schedule subset: {e}")
    
    # Check if 'Atraso_h' exists in schedule (Plan Goal)
    if "Atraso_h" in schedule.columns:
        print("\n'Atraso_h' column found in schedule! (FAILURE: Should have been removed)")
        print(schedule[["Maquina", "Fin", "DueDate", "Atraso_h"]])
    else:
        print("\n'Atraso_h' NOT found in schedule (SUCCESS: Logic removed).")
        
    # Check resumen_ot (should still have delays calculated)
    print("\nResumen OT:")
    if not resumen_ot.empty:
        print(resumen_ot[["OT_id", "Atraso_h", "EnRiesgo"]])
    else:
        print("Resumen OT is empty")

if __name__ == "__main__":
    verify_machine_delay()
