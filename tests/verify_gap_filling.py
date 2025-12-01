import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar
from modules.config_loader import horas_por_dia

def test_gap_filling():
    print("=== Testing Gap Filling Logic ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["Imp_Offset", "Troqueladora"],
            "Proceso": ["Impresión Offset", "Troquelado"],
            "Capacidad_pliegos_hora": [1000, 1000],
            "Setup_base_min": [30, 30],
            "Setup_menor_min": [10, 10]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Impresión Offset", "Troquelado"],
        "horas_laborales": 9, # 7:00 to 16:00
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    # Mock helper functions in config_loader if needed, but we are importing real ones.
    # We rely on the fact that scheduler imports them from modules.config_loader
    
    # 2. Create Test Data
    # Scenario:
    # Task A (High Priority): Needs Offset -> Troquelado. Offset finishes late.
    # Task B (Low Priority): Needs Troquelado only (or Offset is already done). Ready immediately.
    # Expected: Troqueladora should pick Task B while waiting for Task A's Offset.
    
    today = date.today()
    start_time = time(7, 0)
    
    # Task A: 5000 sheets. Offset takes 5 hours. Troquelado takes 5 hours.
    # Task B: 1000 sheets. Troquelado takes 1 hour. Ready NOW.
    
    # We simulate this by setting up the input DataFrame
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "A", "Subcodigo": "1", "CantidadProductos": 5000, 
            "Proceso": "Impresión Offset", "Urgente": "Si", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "ClientA", "Poses": 1, "BocasTroquel": 1,
            "_PEN_ImpresionOffset": "Si", "_PEN_Troquelado": "Si"
        },
        {
            "CodigoProducto": "B", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Troquelado", "Urgente": "No", "FechaEntrega": today + timedelta(days=1),
            "MateriaPrima": "Papel", "Cliente": "ClientB", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Troquelado": "Si" # Only Troquelado pending (or ready)
        }
    ])
    
    # We need to ensure Task A's Offset takes time.
    # In our mock, we can't easily force duration without mocking tiempo_operacion_h.
    # But we can rely on standard calculation. 5000 sheets @ 1000/h = 5 hours.
    
    # Run Scheduler
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("Error: Schedule is empty!")
        return

    print("\nGenerated Schedule:")
    print(schedule[["OT_id", "Maquina", "Proceso", "Inicio", "Fin", "Motivo"]])
    
    # Analyze Results
    troquel_tasks = schedule[schedule["Maquina"] == "Troqueladora"].sort_values("Inicio")
    
    if troquel_tasks.empty:
        print("Error: No tasks scheduled on Troqueladora.")
        return

    first_task = troquel_tasks.iloc[0]
    second_task = troquel_tasks.iloc[1] if len(troquel_tasks) > 1 else None
    
    print(f"\nFirst task on Troqueladora: {first_task['OT_id']} ({first_task['Proceso']}) at {first_task['Inicio']}")
    
    # Verification Logic
    # Task A (Offset) starts at 7:00, ends approx 12:00 (5h).
    # Task A (Troquel) becomes available at 12:00.
    # Task B (Troquel) is available at 7:00.
    
    # Without gap filling: Troqueladora waits for A (Urgente) until 12:00. Idle 7:00-12:00.
    # With gap filling: Troqueladora sees A is not ready, picks B at 7:00.
    
    if first_task['OT_id'] == "B-1":
        print("SUCCESS: Gap filling worked! Task B was scheduled first.")
        if second_task is not None and second_task['OT_id'] == "A-1":
             print("SUCCESS: Task A followed after Task B.")
        else:
             print("WARNING: Task A was not scheduled second (or at all).")
    else:
        print(f"FAILURE: Gap filling failed. Task {first_task['OT_id']} was scheduled first.")
        # Check if there was a gap
        if first_task['Inicio'].time() > time(7, 0):
             print(f"       And there was a gap! First task started at {first_task['Inicio']}")
        else:
             print("       Task A started immediately? Check dependencies.")

if __name__ == "__main__":
    try:
        test_gap_filling()
    except Exception as e:
        import traceback
        traceback.print_exc()
