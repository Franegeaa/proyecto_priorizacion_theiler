import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_lunch_break():
    print("=== Testing Lunch Break Logic ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["M1"],
            "Proceso": ["Impresión Flexo"],
            "Capacidad_pliegos_hora": [100], # Slow machine to force multi-day
            "Setup_base_min": [0],
            "Setup_menor_min": [0]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Impresión Flexo"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Task that takes 16 hours.
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "LongTask", "Subcodigo": "1", "CantidadProductos": 1600, 
            "Proceso": "Impresión Flexo", "Urgente": "No", "FechaEntrega": today + timedelta(days=5),
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "CantidadPliegos": 1600, "_PEN_ImpresionFlexo": "Si"
        }
    ])
    
    # Run Scheduler
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("Error: Schedule is empty!")
        return

    print("\nGenerated Schedule:")
    print(schedule[["OT_id", "Maquina", "Proceso", "Inicio", "Fin"]])
    
    task = schedule.iloc[0]
    end_time = task["Fin"]
    
    print(f"\nTask End Time: {end_time}")
    
    # Expected: Day 2 at 15:00.
    # If bug: Day 2 at 14:30.
    
    expected_time = datetime.combine(today + timedelta(days=1), time(15, 0))
    buggy_time = datetime.combine(today + timedelta(days=1), time(14, 30))
    
    if end_time == expected_time:
        print("SUCCESS: Lunch break respected on Day 2.")
    elif end_time == buggy_time:
        print("FAILURE: Lunch break ignored on Day 2.")
    else:
        print(f"FAILURE: Unexpected end time. Expected {expected_time}, got {end_time}")

if __name__ == "__main__":
    try:
        test_lunch_break()
    except Exception as e:
        import traceback
        traceback.print_exc()
