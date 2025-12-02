import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_descartonado_priority():
    print("=== Testing Descartonado Successor Priority ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["ZZ_Descartonadora", "Descartonadora 2", "Pegadora 1"],
            "Proceso": ["Descartonado", "Descartonado", "Pegado"],
            "Capacidad_pliegos_hora": [1000, 1000, 1000],
            "Setup_base_min": [30, 30, 30],
            "Setup_menor_min": [10, 10, 10]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Descartonado", "Pegado"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Task A: Descartonado -> Pegado. Ready now.
    # Task B: Descartonado (Final step). Ready now.
    # Both go to POOL_DESCARTONADO.
    # We want Task A to be picked first because it unblocks Pegado.
    
    # To ensure Task B is "naturally" first, we give it an earlier DueDate or just list it first.
    # Let's list it first and give it same urgency.
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "B", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today - timedelta(days=1), # Earlier due date
            "MateriaPrima": "Papel", "Cliente": "ClientB", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si" # No Pegado pending
        },
        {
            "CodigoProducto": "A", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "ClientA", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si", "_PEN_Pegado": "Si" # Has Pegado pending
        }
    ])
    
    # Run Scheduler
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("Error: Schedule is empty!")
        return

    print("\nGenerated Schedule:")
    print(schedule[["OT_id", "Maquina", "Proceso", "Inicio", "Fin"]])
    
    # Analyze Results
    desc_tasks = schedule[schedule["Maquina"] == "ZZ_Descartonadora"].sort_values("Inicio")
    
    if desc_tasks.empty:
        print("Error: No tasks scheduled on ZZ_Descartonadora.")
        return

    first_task = desc_tasks.iloc[0]
    
    print(f"\nFirst task on ZZ_Descartonadora: {first_task['OT_id']} at {first_task['Inicio']}")
    
    if first_task['OT_id'] == "A-1":
        print("SUCCESS: Task A (with successor) was scheduled first.")
    else:
        print(f"FAILURE: Task {first_task['OT_id']} was scheduled first. Expected A-1.")

if __name__ == "__main__":
    try:
        test_descartonado_priority()
    except Exception as e:
        import traceback
        traceback.print_exc()
