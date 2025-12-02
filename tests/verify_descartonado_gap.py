import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_descartonado_gap():
    print("=== Testing Descartonado Gap Filling ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["00_Imp_Offset", "ZZ_Descartonadora"],
            "Proceso": ["Impresión Offset", "Descartonado"],
            "Capacidad_pliegos_hora": [1000, 1000],
            "Setup_base_min": [30, 30],
            "Setup_menor_min": [10, 10]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Impresión Offset", "Descartonado"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Task A: Needs Offset -> Descartonado. Offset takes 5 hours.
    # Task B: Needs Descartonado only (or Offset done). Ready immediately.
    # Both go to POOL_DESCARTONADO.
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "A", "Subcodigo": "1", "CantidadProductos": 5000, 
            "Proceso": "Impresión Offset", "Urgente": "Si", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "ClientA", "Poses": 1, "BocasTroquel": 1,
            "_PEN_ImpresionOffset": "Si", "_PEN_Descartonado": "Si"
        },
        {
            "CodigoProducto": "B", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today + timedelta(days=1),
            "MateriaPrima": "Papel", "Cliente": "ClientB", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si"
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
    
    # Task A (Offset) ends at 12:00.
    # Task B is ready at 07:00.
    # If gap filling works, B should be first.
    # If not, A might be first (if it was first in the pool) and cause a wait.
    
    if first_task['OT_id'] == "B-1":
        print("SUCCESS: Gap filling worked! Task B was scheduled first.")
    else:
        print(f"FAILURE: Task {first_task['OT_id']} was scheduled first.")
        if first_task['Inicio'].time() > time(7, 0):
             print(f"       And there was a gap! First task started at {first_task['Inicio']}")

if __name__ == "__main__":
    try:
        test_descartonado_gap()
    except Exception as e:
        import traceback
        traceback.print_exc()
