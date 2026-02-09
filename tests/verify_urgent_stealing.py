import pandas as pd
from datetime import datetime, time
from modules.scheduler import programar
from modules.utils.config_loader import cargar_config

def test_urgent_stealing():
    print("=== Testing Urgent Task Stealing (Strict Priority) ===")
    
    cfg = cargar_config()
    
    # Setup:
    # 1. Urgent Task A: Needs Troquelado. Assigned to Manual (e.g., by size/default). Future (waiting for Flexo).
    # 2. Normal Task B: Needs Troquelado. Assigned to Manual. Ready NOW.
    # 3. Auto Troqueladora: Empty.
    # Expected: Auto should WAIT for Task A, not steal Task B.
    
    # Data
    data = [
        # Urgent Task A (Waiting for Flexo)
        {
            "CodigoProducto": "UrgentTask", "Subcodigo": "A", "Cliente": "ClientA",
            "CantidadPliegos": 50000, "Proceso": "Impresion Flexo", "Maquina": "Flexo 1",
            "Urgente": "Si", "DueDate": "2025-12-10", "FechaEntrega": "2025-12-10", "MateriaPrimaPlanta": "Si",
            "PliAnc": 50, "PliLar": 50, # Fits Auto
            "_PEN_Troquelado": "Si"
        },
        {
            "CodigoProducto": "UrgentTask", "Subcodigo": "A", "Cliente": "ClientA",
            "CantidadPliegos": 5000, "Proceso": "Troquelado", "Maquina": "Manual 1", # Assigned to Manual initially
            "Urgente": "Si", "DueDate": "2025-12-10", "FechaEntrega": "2025-12-10", "MateriaPrimaPlanta": "Si",
            "PliAnc": 50, "PliLar": 50,
            "_PEN_Troquelado": "No"
        },
        # Normal Task B (Ready Now)
        {
            "CodigoProducto": "NormalTask", "Subcodigo": "B", "Cliente": "ClientB",
            "CantidadPliegos": 5000, "Proceso": "Troquelado", "Maquina": "Manual 1",
            "Urgente": "No", "DueDate": "2025-12-15", "FechaEntrega": "2025-12-15", "MateriaPrimaPlanta": "Si",
            "PliAnc": 50, "PliLar": 50,
            "_PEN_Troquelado": "No"
        }
    ]
    
    df = pd.DataFrame(data)
    
    # Force Flexo to take time so Urgent Task is future
    # We can mock this by setting start time
    start_dt = datetime(2025, 12, 3, 7, 0)
    
    # Run Scheduler
    schedule, _, _, _ = programar(df, cfg, start=start_dt.date(), start_time=start_dt.time())
    
    # Analyze Auto Troqueladora
    auto_sched = schedule[schedule["Maquina"].str.contains("Autom", case=False)].sort_values("Inicio")
    
    print("\nGenerated Schedule for Auto:")
    print(auto_sched[["OT_id", "Inicio", "Fin", "Motivo"]])
    
    if auto_sched.empty:
        print("FAILURE: Auto machine did not steal any task.")
        exit(1)
        
    first_task = auto_sched.iloc[0]
    print(f"\nFirst Task on Auto: {first_task['OT_id']} at {first_task['Inicio']}")
    
    # Check if Urgent Task A is first
    if "UrgentTask-A" in first_task["OT_id"]:
        # Check if it waited (Flexo takes time, so start should be > 07:00)
        if first_task["Inicio"].time() > time(7, 0):
            print("SUCCESS: Auto waited for Urgent Task A.")
        else:
            print("WARNING: Auto took Urgent Task A but immediately (Flexo time might be 0?).")
    else:
        print("FAILURE: Auto stole Normal Task B instead of waiting for Urgent Task A.")
        exit(1)

if __name__ == "__main__":
    test_urgent_stealing()
