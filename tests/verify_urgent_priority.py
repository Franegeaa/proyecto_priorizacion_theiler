import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_urgent_priority():
    print("=== Testing Urgent Task Strict Priority ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["M0", "M1"],
            "Proceso": ["Pre-Proceso", "Proceso Final"],
            "Capacidad_pliegos_hora": [1000, 1000], 
            "Setup_base_min": [0, 0],
            "Setup_menor_min": [0, 0]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Pre-Proceso", "Proceso Final"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Task A (Urgent): Needs Impresión Flexo (3h) -> Ready at 10:00. Duration on M1 (Troquelado): 1h.
    # Task B (Normal): No Impresión Flexo -> Ready at 07:00. Duration on M1 (Troquelado): 5h.
    
    df_ordenes = pd.DataFrame([
        {
            "CodigoProducto": "UrgentTask", "Subcodigo": "A", "CantidadProductos": 1000, 
            "Proceso": "Troquelado", "Urgente": "Si", "FechaEntrega": today + timedelta(days=5),
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "CantidadPliegos": 1000, 
            "_PEN_ImpresionFlexo": "Si", "_PEN_Troquelado": "Si" # Needs Flexo first
        },
        {
            "CodigoProducto": "NormalTask", "Subcodigo": "B", "CantidadProductos": 5000, 
            "Proceso": "Troquelado", "Urgente": "No", "FechaEntrega": today + timedelta(days=5),
            "MateriaPrima": "Papel", "Cliente": "C2", "Poses": 1, "BocasTroquel": 1,
            "CantidadPliegos": 5000,
            "_PEN_ImpresionFlexo": "No", "_PEN_Troquelado": "Si" # Ready for Troquelado immediately
        }
    ])
    
    # Update CFG to match these processes
    cfg["maquinas"] = pd.DataFrame({
        "Maquina": ["M0", "M1"],
        "Proceso": ["Impresión Flexo", "Troquelado"],
        "Capacidad_pliegos_hora": [1000, 1000], 
        "Setup_base_min": [0, 0],
        "Setup_menor_min": [0, 0]
    })
    cfg["orden_std"] = ["Impresión Flexo", "Troquelado"]
    
    # Run Scheduler
    schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if schedule.empty:
        print("Error: Schedule is empty!")
        return

    print("\nGenerated Schedule for M1:")
    m1_schedule = schedule[schedule["Maquina"] == "M1"].sort_values("Inicio")
    print(m1_schedule[["OT_id", "Inicio", "Fin", "Motivo"]])
    
    if m1_schedule.empty:
        print("Error: No tasks scheduled on M1")
        return

    first_task = m1_schedule.iloc[0]
    second_task = m1_schedule.iloc[1] if len(m1_schedule) > 1 else None
    
    print(f"\nFirst Task on M1: {first_task['OT_id']} at {first_task['Inicio']}")
    
    # Check if UrgentTask is first
    if "UrgentTask" in first_task["OT_id"]:
        print("SUCCESS: Urgent Task was prioritized (Machine waited).")
    else:
        print("FAILURE: Normal Task ran first (Urgent Task delayed).")
        # Check delay
        urgent_row = m1_schedule[m1_schedule["OT_id"].str.contains("UrgentTask")]
        if not urgent_row.empty:
            print(f"Urgent Task started at: {urgent_row.iloc[0]['Inicio']}")

if __name__ == "__main__":
    try:
        test_urgent_priority()
    except Exception as e:
        import traceback
        traceback.print_exc()
