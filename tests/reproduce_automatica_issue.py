import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_reproduce_issue():
    print("=== Reproducing Automatica Assignment Issue ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["Automatica", "Manual 1"],
            "Proceso": ["Troquelado", "Troquelado"],
            "Capacidad_pliegos_hora": [1000, 500],
            "Setup_base_min": [30, 30],
            "Setup_menor_min": [10, 10]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Troquelado"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Two orders with SAME CodigoTroquel.
    # Order 1: 40x40 (Valid for Automatica)
    # Order 2: 37x40 (Invalid for Automatica, Valid for Manual)
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "VALID", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Troquelado", "Urgente": "No", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Troquelado": "Si", "CodigoTroquel": "T1",
            "PliAnc": 40, "PliLar": 40, "CantidadPliegos": 2000
        },
        {
            "CodigoProducto": "INVALID", "Subcodigo": "1", "CantidadProductos": 2000, 
            "Proceso": "Troquelado", "Urgente": "No", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Troquelado": "Si", "CodigoTroquel": "T1",
            "PliAnc": 37, "PliLar": 40, "CantidadPliegos": 2000
        }
    ])
    
    # Run Scheduler
    # The "Reasignación Troquelado" logic runs BEFORE the main loop and assigns the machine.
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("Error: Schedule is empty!")
        return

    print("\nGenerated Schedule:")
    print(schedule[["OT_id", "Maquina", "Proceso", "PliAnc", "PliLar"]])
    
    # Check assignments
    invalid_task = schedule[schedule["OT_id"] == "INVALID-1"].iloc[0]
    valid_task = schedule[schedule["OT_id"] == "VALID-1"].iloc[0]
    
    print(f"\nTask INVALID-1 assigned to: {invalid_task['Maquina']}")
    print(f"Task VALID-1 assigned to: {valid_task['Maquina']}")
    
    if "autom" in str(invalid_task['Maquina']).lower():
        print("FAILURE: INVALID-1 (Width 37) was assigned to Automatica!")
    else:
        print("SUCCESS: INVALID-1 was NOT assigned to Automatica.")

if __name__ == "__main__":
    try:
        test_reproduce_issue()
    except Exception as e:
        import traceback
        traceback.print_exc()
